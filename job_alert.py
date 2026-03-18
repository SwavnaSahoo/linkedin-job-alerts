import json
import os
import smtplib
import hashlib
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

EXPERIENCE_LEVELS = [
    ("1", "Internship"),
    ("2", "Entry Level"),
    ("3", "Associate"),
    ("4", "Mid-Senior"),
]

JOB_SEARCHES = [
    # (keyword, linkedin_location, indeed_location, location_label)
    ("data analyst", "Buffalo, New York, United States", "Buffalo, NY", "Buffalo, NY"),
    ("people analyst", "Buffalo, New York, United States", "Buffalo, NY", "Buffalo, NY"),
    ("product manager", "Buffalo, New York, United States", "Buffalo, NY", "Buffalo, NY"),
    ("business analytics", "Buffalo, New York, United States", "Buffalo, NY", "Buffalo, NY"),
    ("data analyst intern", "Buffalo, New York, United States", "Buffalo, NY", "Buffalo, NY"),

    ("data analyst", "Rochester, New York, United States", "Rochester, NY", "Rochester, NY"),
    ("people analyst", "Rochester, New York, United States", "Rochester, NY", "Rochester, NY"),
    ("product manager", "Rochester, New York, United States", "Rochester, NY", "Rochester, NY"),
    ("business analytics", "Rochester, New York, United States", "Rochester, NY", "Rochester, NY"),
    ("data analyst intern", "Rochester, New York, United States", "Rochester, NY", "Rochester, NY"),

    ("data analyst", "Atlanta, Georgia, United States", "Atlanta, GA", "Atlanta, GA"),
    ("people analyst", "Atlanta, Georgia, United States", "Atlanta, GA", "Atlanta, GA"),
    ("product manager", "Atlanta, Georgia, United States", "Atlanta, GA", "Atlanta, GA"),
    ("business analytics", "Atlanta, Georgia, United States", "Atlanta, GA", "Atlanta, GA"),
    ("data analyst intern", "Atlanta, Georgia, United States", "Atlanta, GA", "Atlanta, GA"),

    ("data analyst", "San Diego, California, United States", "San Diego, CA", "San Diego, CA"),
    ("people analyst", "San Diego, California, United States", "San Diego, CA", "San Diego, CA"),
    ("product manager", "San Diego, California, United States", "San Diego, CA", "San Diego, CA"),
    ("business analytics", "San Diego, California, United States", "San Diego, CA", "San Diego, CA"),
    ("data analyst intern", "San Diego, California, United States", "San Diego, CA", "San Diego, CA"),

    ("data analyst", "Puerto Rico", "Puerto Rico", "Puerto Rico"),
    ("people analyst", "Puerto Rico", "Puerto Rico", "Puerto Rico"),
    ("product manager", "Puerto Rico", "Puerto Rico", "Puerto Rico"),
    ("business analytics", "Puerto Rico", "Puerto Rico", "Puerto Rico"),
    ("data analyst intern", "Puerto Rico", "Puerto Rico", "Puerto Rico"),

    ("data analyst", "Washington DC, United States", "Washington, DC", "Washington DC"),
    ("people analyst", "Washington DC, United States", "Washington, DC", "Washington DC"),
    ("product manager", "Washington DC, United States", "Washington, DC", "Washington DC"),
    ("business analytics", "Washington DC, United States", "Washington, DC", "Washington DC"),
    ("data analyst intern", "Washington DC, United States", "Washington, DC", "Washington DC"),
]

SEEN_JOBS_FILE = "seen_jobs.json"
MAX_SEEN_JOBS = 2000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

LEVEL_COLORS = {
    "Internship":  {"bg": "#e8f4fb", "text": "#005f8a"},
    "Entry Level": {"bg": "#e6f9ee", "text": "#1a6e3c"},
    "Associate":   {"bg": "#fff8e1", "text": "#7d5a00"},
    "Mid-Senior":  {"bg": "#fce8f3", "text": "#8b1a5c"},
}

SOURCE_COLORS = {
    "LinkedIn":    {"bg": "#e8f4fb", "text": "#0077b5"},
    "Indeed":      {"bg": "#fff3e0", "text": "#c8401a"},
    "ZipRecruiter": {"bg": "#f0e8fb", "text": "#6b2fa0"},
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def job_id(title, company, location, source):
    unique_str = f"{title}-{company}-{location}-{source}"
    return hashlib.md5(unique_str.encode()).hexdigest()

def load_seen_jobs():
    if Path(SEEN_JOBS_FILE).exists():
        with open(SEEN_JOBS_FILE, "r") as f:
            data = json.load(f)
            print(f"[INFO] Cache size: {len(data)} entries")
            return set(data)
    return set()

def save_seen_jobs(seen):
    seen_list = list(seen)
    if len(seen_list) > MAX_SEEN_JOBS:
        seen_list = seen_list[-MAX_SEEN_JOBS:]
        print(f"[INFO] Cache trimmed to {MAX_SEEN_JOBS} entries")
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen_list, f)

# ─────────────────────────────────────────────
# LINKEDIN FETCHING
# ─────────────────────────────────────────────

def fetch_linkedin_jobs(keyword, linkedin_location, location_label, exp_code, exp_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "%20")
    location_encoded = linkedin_location.replace(" ", "%20").replace(",", "%2C")

    url = (
        f"https://www.linkedin.com/jobs/search?"
        f"keywords={keyword_encoded}"
        f"&location={location_encoded}"
        f"&f_TPR=r3600"
        f"&f_E={exp_code}"
        f"&sortBy=DD"
        f"&position=1&pageNum=0"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return new_jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        job_cards = soup.find_all("div", class_="base-card")

        for card in job_cards[:8]:
            try:
                title_el   = card.find("h3")
                company_el = card.find("h4")
                link_el    = card.find("a", href=True)

                title   = title_el.get_text(strip=True)   if title_el   else "Unknown Title"
                company = company_el.get_text(strip=True) if company_el else "Unknown Company"
                link    = link_el["href"]                 if link_el    else "#"
                if "?" in link:
                    link = link.split("?")[0]

                jid = job_id(title, company, location_label, "LinkedIn")
                if jid not in seen_jobs:
                    new_jobs.append({
                        "id": jid, "title": title, "company": company,
                        "location": location_label, "exp_level": exp_label,
                        "link": link, "source": "LinkedIn",
                    })
                    seen_jobs.add(jid)
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] LinkedIn failed for '{keyword}' in {location_label}: {e}")

    return new_jobs

# ─────────────────────────────────────────────
# INDEED FETCHING (RSS)
# ─────────────────────────────────────────────

def fetch_indeed_jobs(keyword, indeed_location, location_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "+")
    location_encoded = indeed_location.replace(" ", "+").replace(",", "%2C")

    url = (
        f"https://www.indeed.com/rss?q={keyword_encoded}"
        f"&l={location_encoded}"
        f"&sort=date"
        f"&fromage=1"
    )

    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            title   = entry.get("title", "Unknown Title")
            company = entry.get("author", entry.get("source", {}).get("title", "Unknown Company"))
            link    = entry.get("link", "#")

            jid = job_id(title, company, location_label, "Indeed")
            if jid not in seen_jobs:
                new_jobs.append({
                    "id": jid, "title": title, "company": company,
                    "location": location_label, "exp_level": "",
                    "link": link, "source": "Indeed",
                })
                seen_jobs.add(jid)
    except Exception as e:
        print(f"[WARN] Indeed failed for '{keyword}' in {location_label}: {e}")

    return new_jobs

# ─────────────────────────────────────────────
# ZIPRECRUITER FETCHING (RSS)
# ─────────────────────────────────────────────

def fetch_ziprecruiter_jobs(keyword, indeed_location, location_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "+")
    location_encoded = indeed_location.replace(" ", "+").replace(",", "%2C")

    url = (
        f"https://www.ziprecruiter.com/jobs-search/feed?"
        f"search={keyword_encoded}"
        f"&location={location_encoded}"
        f"&days=1"
    )

    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            title   = entry.get("title", "Unknown Title")
            company = entry.get("author", "Unknown Company")
            link    = entry.get("link", "#")

            jid = job_id(title, company, location_label, "ZipRecruiter")
            if jid not in seen_jobs:
                new_jobs.append({
                    "id": jid, "title": title, "company": company,
                    "location": location_label, "exp_level": "",
                    "link": link, "source": "ZipRecruiter",
                })
                seen_jobs.add(jid)
    except Exception as e:
        print(f"[WARN] ZipRecruiter failed for '{keyword}' in {location_label}: {e}")

    return new_jobs

# ─────────────────────────────────────────────
# FETCH ALL
# ─────────────────────────────────────────────

def fetch_new_jobs(seen_jobs):
    all_new = []

    # LinkedIn (with experience level filters)
    print("[INFO] Fetching from LinkedIn...")
    for keyword, linkedin_loc, indeed_loc, location_label in JOB_SEARCHES:
        for exp_code, exp_label in EXPERIENCE_LEVELS:
            jobs = fetch_linkedin_jobs(keyword, linkedin_loc, location_label, exp_code, exp_label, seen_jobs)
            if jobs:
                print(f"[INFO] LinkedIn: {len(jobs)} new '{exp_label}' '{keyword}' in {location_label}")
            all_new.extend(jobs)
            time.sleep(2)

    # Indeed (RSS)
    print("[INFO] Fetching from Indeed...")
    seen_indeed = set()
    for keyword, linkedin_loc, indeed_loc, location_label in JOB_SEARCHES:
        key = f"{keyword}-{location_label}"
        if key not in seen_indeed:
            jobs = fetch_indeed_jobs(keyword, indeed_loc, location_label, seen_jobs)
            if jobs:
                print(f"[INFO] Indeed: {len(jobs)} new '{keyword}' in {location_label}")
            all_new.extend(jobs)
            seen_indeed.add(key)
            time.sleep(1)

    # ZipRecruiter (RSS)
    print("[INFO] Fetching from ZipRecruiter...")
    seen_zip = set()
    for keyword, linkedin_loc, indeed_loc, location_label in JOB_SEARCHES:
        key = f"{keyword}-{location_label}"
        if key not in seen_zip:
            jobs = fetch_ziprecruiter_jobs(keyword, indeed_loc, location_label, seen_jobs)
            if jobs:
                print(f"[INFO] ZipRecruiter: {len(jobs)} new '{keyword}' in {location_label}")
            all_new.extend(jobs)
            seen_zip.add(key)
            time.sleep(1)

    return all_new

# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def exp_badge(exp_level):
    if not exp_level:
        return ""
    colors = LEVEL_COLORS.get(exp_level, {"bg": "#f0ede7", "text": "#8c877e"})
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:2px;'
        f'background:{colors["bg"]};color:{colors["text"]};'
        f'font-size:10px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;margin-left:8px;vertical-align:middle;">'
        f'{exp_level}</span>'
    )

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

    # Count by source
    sources = {}
    for job in jobs:
        s = job.get("source", "Unknown")
        sources[s] = sources.get(s, 0) + 1
    source_summary = " · ".join([f"{v} from {k}" for k, v in sources.items()])

    sections = ""
    for location, loc_jobs in sorted(by_location.items()):
        job_rows = ""
        for job in loc_jobs:
            badge = exp_badge(job.get("exp_level", ""))
            sbadge = source_badge(job.get("source", ""))
            job_rows += f"""
            <div style="padding:18px 0;border-bottom:1px solid #e8e4de;">
              <div style="margin-bottom:6px;">
                <span style="font-size:15px;font-weight:500;color:#1a1916;">{job['title']}</span>{badge}{sbadge}
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
        {len(jobs)} new listing{"s" if len(jobs)!=1 else ""}<br><em style="font-style:italic;color:#c17f3e;">just dropped.</em>
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
        Runs every 15 minutes · Built by Swavna Sahoo<br>
        Sources: LinkedIn · Indeed · ZipRecruiter<br>
        <a href="https://swavnasahoo.github.io/linkedin-job-alerts" style="color:#c17f3e;text-decoration:none;border-bottom:1px solid #e8c99a;">Visit JobPing →</a>
      </div>
      <div style="margin-top:14px;padding-top:14px;border-top:1px solid #f0ede7;">
        <a href="mailto:jobsandalotmore@gmail.com?subject=Unsubscribe me&body=Please remove me from JobPing alerts." style="font-size:11px;color:#c17f3e;text-decoration:none;border-bottom:1px solid #e8c99a;padding-bottom:1px;letter-spacing:0.04em;">Unsubscribe</a>
        <span style="font-size:11px;color:#e8e4de;margin:0 8px;">·</span>
        <span style="font-size:11px;color:#b5b0a8;font-weight:300;">You're receiving this because you signed up at JobPing.</span>
      </div>
    </div>

  </div>
</body></html>"""

def send_email(jobs):
    sender    = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password  = os.environ["EMAIL_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    subject_lines = [
        f"Freshly brewed opportunities — {datetime.now().strftime('%b %d')}",
        f"Your next chapter might be in here — {datetime.now().strftime('%b %d')}",
        f"Hot off the feed — {datetime.now().strftime('%b %d')}",
        f"Curated. Just for you. — {datetime.now().strftime('%b %d')}",
        f"New doors, just opened — {datetime.now().strftime('%b %d')}",
        f"The search continues, beautifully — {datetime.now().strftime('%b %d')}",
        f"Something good this way comes — {datetime.now().strftime('%b %d')}",
        f"Don't sleep on these — {datetime.now().strftime('%b %d')}",
    ]
    interval = (datetime.now().hour * 60 + datetime.now().minute) // 15
    subject = subject_lines[interval % len(subject_lines)]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(build_email_html(jobs), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print(f"[OK] Email sent: {len(jobs)} new jobs")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print(f"[START] Job alert run at {datetime.now().isoformat()}")
    seen_jobs = load_seen_jobs()
    print(f"[INFO] {len(seen_jobs)} previously seen jobs loaded")

    new_jobs = fetch_new_jobs(seen_jobs)
    print(f"[INFO] {len(new_jobs)} new jobs found total")

    if new_jobs:
        send_email(new_jobs)
        save_seen_jobs(seen_jobs)
    else:
        print("[INFO] No new jobs — no email sent")

    print("[DONE]")

if __name__ == "__main__":
    main()
