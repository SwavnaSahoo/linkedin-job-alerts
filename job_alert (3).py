import json
import os
import smtplib
import hashlib
import time
import calendar
import feedparser
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# LinkedIn location GeoIDs (used in RSS URL)
LINKEDIN_LOCATION_IDS = {
    "Buffalo, NY":    "103783015",
    "Rochester, NY":  "104377157",
    "Atlanta, GA":    "103516136",
    "San Diego, CA":  "104577020",
    "Puerto Rico":    "104746898",
    "Washington DC":  "103644278",
}

KEYWORDS = [
    "data analyst",
    "people analyst",
    "product manager",
    "business analytics",
    "data analyst intern",
    "product management intern",
]

JOB_SEARCHES = [
    # (keyword, location_label, indeed_location)
    (kw, loc, loc)
    for loc in LINKEDIN_LOCATION_IDS
    for kw in KEYWORDS
]

SEEN_JOBS_FILE = "seen_jobs.json"
MAX_SEEN_JOBS = 3000
LOOKBACK_HOURS = 25  # fetch jobs posted in last 25 hours (buffer for timezone drift)

LEVEL_COLORS = {
    "Internship":  {"bg": "#e8f4fb", "text": "#005f8a"},
    "Entry Level": {"bg": "#e6f9ee", "text": "#1a6e3c"},
    "Associate":   {"bg": "#fff8e1", "text": "#7d5a00"},
    "Mid-Senior":  {"bg": "#fce8f3", "text": "#8b1a5c"},
}

SOURCE_COLORS = {
    "LinkedIn":     {"bg": "#e8f4fb", "text": "#0077b5"},
    "Indeed":       {"bg": "#fff3e0", "text": "#c8401a"},
    "ZipRecruiter": {"bg": "#f0e8fb", "text": "#6b2fa0"},
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def job_id(title, company, location, source):
    unique_str = f"{title.lower().strip()}-{company.lower().strip()}-{location}-{source}"
    return hashlib.md5(unique_str.encode()).hexdigest()


def load_seen_jobs():
    if Path(SEEN_JOBS_FILE).exists():
        with open(SEEN_JOBS_FILE, "r") as f:
            data = json.load(f)
        print(f"[INFO] Cache loaded: {len(data)} seen jobs")
        return set(data)
    print("[INFO] No cache found — starting fresh")
    return set()


def save_seen_jobs(seen):
    seen_list = list(seen)
    if len(seen_list) > MAX_SEEN_JOBS:
        seen_list = seen_list[-MAX_SEEN_JOBS:]
        print(f"[INFO] Cache trimmed to {MAX_SEEN_JOBS} entries")
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen_list, f)
    print(f"[INFO] Cache saved: {len(seen_list)} entries")


def is_recent(entry, hours=LOOKBACK_HOURS):
    """Return True if entry was published within the last `hours` hours."""
    published = entry.get("published_parsed")
    if not published:
        return True  # include if no date info
    try:
        pub_dt = datetime.fromtimestamp(calendar.timegm(published), tz=timezone.utc)
        return datetime.now(timezone.utc) - pub_dt < timedelta(hours=hours)
    except Exception:
        return True


def parse_feed_safe(url):
    """Parse an RSS feed with a browser-like user-agent."""
    try:
        feed = feedparser.parse(
            url,
            agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
        return feed
    except Exception as e:
        print(f"[WARN] Feed parse error for {url}: {e}")
        return None


# ─────────────────────────────────────────────
# LINKEDIN — RSS (no scraping, no API key)
# ─────────────────────────────────────────────

def fetch_linkedin_jobs(keyword, location_label, seen_jobs):
    """
    LinkedIn exposes a public RSS feed for job searches.
    Format: /jobs/search/rss?keywords=...&location=...&geoId=...&f_TPR=r86400&sortBy=DD
    f_TPR=r86400 = posted in last 24 hours
    """
    new_jobs = []
    geo_id = LINKEDIN_LOCATION_IDS.get(location_label, "")
    if not geo_id:
        return new_jobs

    keyword_encoded = keyword.replace(" ", "%20")
    location_encoded = location_label.replace(" ", "%20").replace(",", "%2C")

    url = (
        f"https://www.linkedin.com/jobs/search/rss?"
        f"keywords={keyword_encoded}"
        f"&location={location_encoded}"
        f"&geoId={geo_id}"
        f"&f_TPR=r86400"
        f"&sortBy=DD"
    )

    feed = parse_feed_safe(url)
    if not feed or not feed.entries:
        return new_jobs

    for entry in feed.entries[:10]:
        if not is_recent(entry):
            continue
        title = entry.get("title", "Unknown Title")
        # LinkedIn RSS puts "Company · Location" in subtitle or author
        company = entry.get("author", "")
        if not company:
            # Try to extract from title like "Title at Company"
            if " at " in title:
                parts = title.split(" at ", 1)
                title = parts[0].strip()
                company = parts[1].strip()
            else:
                company = "Unknown Company"
        link = entry.get("link", "#")
        # Clean tracking params
        if "?" in link:
            link = link.split("?")[0]

        jid = job_id(title, company, location_label, "LinkedIn")
        if jid not in seen_jobs:
            new_jobs.append({
                "id": jid, "title": title, "company": company,
                "location": location_label, "exp_level": "",
                "link": link, "source": "LinkedIn",
            })
            seen_jobs.add(jid)

    return new_jobs


# ─────────────────────────────────────────────
# INDEED — RSS
# ─────────────────────────────────────────────

def fetch_indeed_jobs(keyword, location_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "+")
    location_encoded = location_label.replace(" ", "+").replace(",", "%2C")

    # fromage=1 = posted today; sort=date = newest first
    url = (
        f"https://www.indeed.com/rss?q={keyword_encoded}"
        f"&l={location_encoded}"
        f"&sort=date"
        f"&fromage=1"
    )

    feed = parse_feed_safe(url)
    if not feed or not feed.entries:
        return new_jobs

    for entry in feed.entries[:10]:
        if not is_recent(entry):
            continue
        title = entry.get("title", "Unknown Title")
        # Indeed RSS puts company in author or source title
        company = entry.get("author", "")
        if not company:
            source_info = entry.get("source", {})
            company = source_info.get("title", "Unknown Company") if isinstance(source_info, dict) else "Unknown Company"
        link = entry.get("link", "#")

        jid = job_id(title, company, location_label, "Indeed")
        if jid not in seen_jobs:
            new_jobs.append({
                "id": jid, "title": title, "company": company,
                "location": location_label, "exp_level": "",
                "link": link, "source": "Indeed",
            })
            seen_jobs.add(jid)

    return new_jobs


# ─────────────────────────────────────────────
# ZIPRECRUITER — RSS
# ─────────────────────────────────────────────

def fetch_ziprecruiter_jobs(keyword, location_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "+")
    location_encoded = location_label.replace(" ", "+").replace(",", "%2C")

    url = (
        f"https://www.ziprecruiter.com/jobs-search/feed?"
        f"search={keyword_encoded}"
        f"&location={location_encoded}"
        f"&days=1"
    )

    feed = parse_feed_safe(url)
    if not feed or not feed.entries:
        return new_jobs

    for entry in feed.entries[:10]:
        if not is_recent(entry):
            continue
        title = entry.get("title", "Unknown Title")
        company = entry.get("author", "Unknown Company")
        link = entry.get("link", "#")

        jid = job_id(title, company, location_label, "ZipRecruiter")
        if jid not in seen_jobs:
            new_jobs.append({
                "id": jid, "title": title, "company": company,
                "location": location_label, "exp_level": "",
                "link": link, "source": "ZipRecruiter",
            })
            seen_jobs.add(jid)

    return new_jobs


# ─────────────────────────────────────────────
# FETCH ALL
# ─────────────────────────────────────────────

def fetch_new_jobs(seen_jobs):
    all_new = []
    seen_combos = set()

    for keyword, location_label, _ in JOB_SEARCHES:
        combo = f"{keyword}-{location_label}"
        if combo in seen_combos:
            continue
        seen_combos.add(combo)

        # LinkedIn
        jobs = fetch_linkedin_jobs(keyword, location_label, seen_jobs)
        if jobs:
            print(f"[INFO] LinkedIn: {len(jobs)} new '{keyword}' in {location_label}")
        all_new.extend(jobs)
        time.sleep(1.5)

        # Indeed
        jobs = fetch_indeed_jobs(keyword, location_label, seen_jobs)
        if jobs:
            print(f"[INFO] Indeed: {len(jobs)} new '{keyword}' in {location_label}")
        all_new.extend(jobs)
        time.sleep(1)

        # ZipRecruiter
        jobs = fetch_ziprecruiter_jobs(keyword, location_label, seen_jobs)
        if jobs:
            print(f"[INFO] ZipRecruiter: {len(jobs)} new '{keyword}' in {location_label}")
        all_new.extend(jobs)
        time.sleep(1)

    return all_new


# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def source_badge(source):
    colors = SOURCE_COLORS.get(source, {"bg": "#f0ede7", "text": "#8c877e"})
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:2px;'
        f'background:{colors["bg"]};color:{colors["text"]};'
        f'font-size:10px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;margin-left:8px;vertical-align:middle;">'
        f'{source}</span>'
    )


def build_email_html(jobs):
    by_location = {}
    for job in jobs:
        loc = job["location"]
        by_location.setdefault(loc, []).append(job)

    now = datetime.now().strftime("%B %d, %Y")
    time_str = datetime.now().strftime("%I:%M %p")

    sources = {}
    for job in jobs:
        s = job.get("source", "Unknown")
        sources[s] = sources.get(s, 0) + 1
    source_summary = " · ".join([f"{v} from {k}" for k, v in sources.items()])

    sections = ""
    for location, loc_jobs in sorted(by_location.items()):
        job_rows = ""
        for job in loc_jobs:
            sbadge = source_badge(job.get("source", ""))
            job_rows += f"""
<div style="padding:18px 0;border-bottom:1px solid #e8e4de;">
  <div style="margin-bottom:6px;">
    <span style="font-size:15px;font-weight:500;color:#1a1916;">{job['title']}</span>{sbadge}
  </div>
  <div style="font-size:13px;color:#8c877e;margin-bottom:10px;">{job['company']}</div>
  <a href="{job['link']}" style="display:inline-block;font-size:12px;font-weight:500;color:#c17f3e;text-decoration:none;letter-spacing:0.04em;border-bottom:1px solid #e8c99a;padding-bottom:1px;">View listing →</a>
</div>
"""

        sections += f"""
<div style="margin-bottom:36px;">
  <div style="margin-bottom:4px;">
    <span style="font-size:10px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#b5b0a8;">location</span>
  </div>
  <div style="font-size:18px;font-weight:500;color:#1a1916;padding-bottom:10px;border-bottom:2px solid #1a1916;margin-bottom:0;">
    {location}
    <span style="font-size:12px;font-weight:400;color:#8c877e;margin-left:10px;">{len(loc_jobs)} new</span>
  </div>
  {job_rows}
</div>
"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#faf9f6;">
<div style="max-width:600px;margin:0 auto;padding:0;background:#faf9f6;">
  <div style="padding:40px 40px 24px;border-bottom:1px solid #e8e4de;">
    <div style="font-size:11px;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;color:#c17f3e;margin-bottom:16px;">JobPing by Swavna</div>
    <div style="font-family:'Playfair Display',Georgia,serif;font-size:32px;font-weight:400;color:#1a1916;line-height:1.15;margin-bottom:8px;">
      {len(jobs)} new listing{"s" if len(jobs) != 1 else ""}<br><em style="font-style:italic;color:#c17f3e;">just dropped.</em>
    </div>
    <div style="font-size:12px;color:#b5b0a8;font-weight:300;margin-top:12px;">{now} · {time_str}</div>
    <div style="font-size:11px;color:#b5b0a8;font-weight:300;margin-top:6px;">{source_summary}</div>
  </div>
  <div style="padding:14px 40px;background:#f3f1ec;border-bottom:1px solid #e8e4de;">
    <span style="font-size:11px;color:#8c877e;font-weight:400;letter-spacing:0.02em;">
      Data Analyst &nbsp;·&nbsp; People Analyst &nbsp;·&nbsp; Product Manager &nbsp;·&nbsp; Business Analytics &nbsp;·&nbsp; Internships
    </span>
  </div>
  <div style="padding:32px 40px;">
    {sections}
  </div>
  <div style="padding:24px 40px;border-top:1px solid #e8e4de;">
    <div style="font-family:'Playfair Display',Georgia,serif;font-size:14px;font-style:italic;color:#b5b0a8;margin-bottom:6px;">JobPing</div>
    <div style="font-size:11px;color:#b5b0a8;font-weight:300;line-height:1.7;">
      Runs every 30 minutes · Built by Swavna Sahoo<br>
      Sources: LinkedIn · Indeed · ZipRecruiter
    </div>
  </div>
</div>
</body></html>"""


def send_email(jobs):
    sender = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password = os.environ["EMAIL_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    subject = f"JobPing: {len(jobs)} new listing{'s' if len(jobs) != 1 else ''} — {datetime.now().strftime('%b %d, %I:%M %p')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(build_email_html(jobs), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print(f"[OK] Email sent: {len(jobs)} new jobs → {recipient}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print(f"[START] Job alert run at {datetime.now().isoformat()}")

    seen_jobs = load_seen_jobs()
    new_jobs = fetch_new_jobs(seen_jobs)

    print(f"[INFO] {len(new_jobs)} new jobs found total")

    if new_jobs:
        send_email(new_jobs)
        save_seen_jobs(seen_jobs)
    else:
        print("[INFO] No new jobs — no email sent")
        # Still save cache so we don't re-alert on stale jobs if feeds come back
        save_seen_jobs(seen_jobs)

    print("[DONE]")


if __name__ == "__main__":
    main()
