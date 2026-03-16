import feedparser
import json
import os
import smtplib
import hashlib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

JOB_SEARCHES = [
    # (keyword, location_id, location_label)
    # Buffalo, NY
    ("data analyst", "103783015", "Buffalo, NY"),
    ("marketing analytics intern" , "103783015", "Buffalo, NY"),
    ("people analyst", "103783015", "Buffalo, NY"),
    ("product manager", "103783015", "Buffalo, NY"),
    ("pproduct management intern", "103783015", "Buffalo, NY"),
    ("business analytics", "103783015", "Buffalo, NY"),
    ("data analyst intern", "103783015", "Buffalo, NY"),

    # Rochester, NY
    ("data analyst", "104377157", "Rochester, NY"),
    ("marketing analytics intern" , "104377157", "Rochester, NY"),
    ("people analyst", "104377157", "Rochester, NY"),
    ("product manager", "104377157", "Rochester, NY"),
    ("business analytics", "104377157", "Rochester, NY"),
    ("data analyst intern", "104377157", "Rochester, NY"),

    # Atlanta, GA
    ("data analyst", "103516136", "Atlanta, GA"),
    ("marketing analytics intern" ,  "103516136", "Atlanta, GA"),
    ("people analyst", "103516136", "Atlanta, GA"),
    ("product manager", "103516136", "Atlanta, GA"),
    ("product management intern", "103516136", "Atlanta, GA"),
    ("business analytics", "103516136", "Atlanta, GA"),
    ("data analyst intern", "103516136", "Atlanta, GA"),

    # San Diego, CA
    ("data analyst", "104577020", "San Diego, CA"),
    ("marketing analytics intern" ,"104577020", "San Diego, CA"),
    ("people analyst", "104577020", "San Diego, CA"),
    ("product manager", "104577020", "San Diego, CA"),
    ("product management intern", "104577020", "San Diego, CA"),
    ("business analytics", "104577020", "San Diego, CA"),
    ("data analyst intern", "104577020", "San Diego, CA"),

    # Puerto Rico
    ("data analyst", "104746898", "Puerto Rico"),
    ("marketing analytics intern" , "104746898", "Puerto Rico"),
    ("people analyst", "104746898", "Puerto Rico"),
    ("product manager", "104746898", "Puerto Rico"),
    ("product management intern", "104746898", "Puerto Rico"),
    ("business analytics", "104746898", "Puerto Rico"),
    ("data analyst intern", "104746898", "Puerto Rico"),

    # Washington DC
    ("data analyst", "103977233", "Washington DC"),
    ("marketing analytics intern" , "103977233", "Washington DC"),
    ("people analyst", "103977233", "Washington DC"),
    ("product manager", "103977233", "Washington DC"),
    ("product management intern", "103977233", "Washington DC"),
    ("business analytics", "103977233", "Washington DC"),
    ("data analyst intern", "103977233", "Washington DC"),
]

SEEN_JOBS_FILE = "seen_jobs.json"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def build_rss_url(keyword: str, location_id: str) -> str:
    """Build LinkedIn Jobs RSS URL for a keyword + location."""
    keyword_encoded = keyword.replace(" ", "%20")
    return (
        f"https://www.linkedin.com/jobs/search/?keywords={keyword_encoded}"
        f"&location={location_id}&f_TPR=r3600&sortBy=DD"
        f"&trk=public_jobs_jobs-search-bar_search-submit"
    )

def build_rss_feed_url(keyword: str, location_id: str) -> str:
    """LinkedIn RSS feed format."""
    keyword_encoded = keyword.replace(" ", "%20")
    return (
        f"https://www.linkedin.com/jobs/search.rss?keywords={keyword_encoded}"
        f"&location={location_id}&f_TPR=r3600&sortBy=DD"
    )

def job_id(entry) -> str:
    """Create a unique hash for a job entry."""
    unique_str = f"{entry.get('title','')}-{entry.get('link','')}"
    return hashlib.md5(unique_str.encode()).hexdigest()

def load_seen_jobs() -> set:
    if Path(SEEN_JOBS_FILE).exists():
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen: set):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)

# ─────────────────────────────────────────────
# JOB FETCHING
# ─────────────────────────────────────────────

def fetch_new_jobs(seen_jobs: set) -> list:
    new_jobs = []

    for keyword, location_id, location_label in JOB_SEARCHES:
        url = build_rss_feed_url(keyword, location_id)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                jid = job_id(entry)
                if jid not in seen_jobs:
                    new_jobs.append({
                        "id": jid,
                        "title": entry.get("title", "Unknown Title"),
                        "company": entry.get("author", "Unknown Company"),
                        "location": location_label,
                        "link": entry.get("link", "#"),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", "")[:300],
                        "keyword": keyword,
                    })
                    seen_jobs.add(jid)
        except Exception as e:
            print(f"[WARN] Failed to fetch feed for '{keyword}' in {location_label}: {e}")

    return new_jobs

# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def build_email_html(jobs: list) -> str:
    by_location = {}
    for job in jobs:
        loc = job["location"]
        by_location.setdefault(loc, []).append(job)

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    sections = ""
    for location, loc_jobs in sorted(by_location.items()):
        job_cards = ""
        for job in loc_jobs:
            job_cards += f"""
            <div style="background:#f9f9f9;border-left:4px solid #0077b5;padding:14px 16px;margin-bottom:12px;border-radius:4px;">
              <div style="font-size:16px;font-weight:700;color:#1a1a1a;margin-bottom:2px;">{job['title']}</div>
              <div style="font-size:13px;color:#555;margin-bottom:8px;">{job['company']} &nbsp;·&nbsp; {job['location']}</div>
              <div style="font-size:12px;color:#777;margin-bottom:10px;">{job['summary'][:200]}{'...' if len(job['summary']) > 200 else ''}</div>
              <a href="{job['link']}" style="display:inline-block;background:#0077b5;color:#fff;text-decoration:none;padding:7px 16px;border-radius:4px;font-size:13px;font-weight:600;">View Job →</a>
            </div>
            """
        sections += f"""
        <div style="margin-bottom:30px;">
          <h2 style="font-size:18px;color:#0077b5;border-bottom:2px solid #0077b5;padding-bottom:6px;margin-bottom:14px;">📍 {location} ({len(loc_jobs)} new)</h2>
          {job_cards}
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#ffffff;">
      <div style="max-width:680px;margin:0 auto;padding:32px 24px;">

        <!-- Header -->
        <div style="background:#0077b5;color:#fff;padding:24px 28px;border-radius:8px 8px 0 0;margin-bottom:0;">
          <div style="font-size:22px;font-weight:800;letter-spacing:-0.5px;">🔔 LinkedIn Job Alert</div>
          <div style="font-size:13px;opacity:0.85;margin-top:4px;">{now} &nbsp;·&nbsp; {len(jobs)} new listing{"s" if len(jobs) != 1 else ""} found</div>
        </div>

        <!-- Roles banner -->
        <div style="background:#e8f4fb;padding:12px 20px;font-size:13px;color:#005f8a;border-left:none;border-right:none;margin-bottom:28px;">
          🎯 Tracking: <strong>Data Analyst · People Analyst · Product Manager · Business Analytics · Internships</strong>
          <br>📌 Locations: Buffalo · Rochester · Atlanta · San Diego · Puerto Rico
        </div>

        <!-- Job sections -->
        {sections}

        <!-- Footer -->
        <div style="border-top:1px solid #e5e5e5;padding-top:18px;font-size:12px;color:#aaa;text-align:center;">
          This alert was generated automatically via GitHub Actions.<br>
          Runs every 30 minutes · Powered by LinkedIn RSS feeds
        </div>

      </div>
    </body>
    </html>
    """

def send_email(jobs: list):
    sender = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password = os.environ["EMAIL_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    subject = f"🔔 {len(jobs)} New LinkedIn Job{'s' if len(jobs) != 1 else ''} — {datetime.now().strftime('%b %d, %I:%M %p')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    html_body = build_email_html(jobs)
    msg.attach(MIMEText(html_body, "html"))

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
    print(f"[INFO] {len(new_jobs)} new jobs found")

    if new_jobs:
        send_email(new_jobs)
        save_seen_jobs(seen_jobs)
    else:
        print("[INFO] No new jobs — no email sent")

    print("[DONE]")

if __name__ == "__main__":
    main()
