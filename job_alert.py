import json
import os
import smtplib
import hashlib
import time
import requests
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

ADZUNA_COUNTRY = "us"

LOCATIONS = [
    "Buffalo, NY",
    "Rochester, NY",
    "Atlanta, GA",
    "San Diego, CA",
    "Washington, DC",
    "Puerto Rico",
]

KEYWORDS = [
    "data analyst",
    "people analyst",
    "product manager",
    "business analytics",
    "data analyst intern",
    "product management intern",
]

SEEN_JOBS_FILE = "seen_jobs.json"
MAX_SEEN_JOBS = 3000
LOOKBACK_HOURS = 25

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def job_id(title, company, location):
    unique_str = f"{title.lower().strip()}-{company.lower().strip()}-{location.lower()}"
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
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen_list, f)
    print(f"[INFO] Cache saved: {len(seen_list)} entries")

def is_recent(created_str, hours=LOOKBACK_HOURS):
    if not created_str:
        return True
    try:
        created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - created < timedelta(hours=hours)
    except Exception:
        return True

# ─────────────────────────────────────────────
# ADZUNA FETCHER
# ─────────────────────────────────────────────

def fetch_adzuna_jobs(keyword, location, app_id, app_key, seen_jobs):
    new_jobs = []
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": keyword,
        "where": location,
        "sort_by": "date",
        "max_days_old": 1,
        "content-type": "application/json",
    }
    url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] Adzuna {resp.status_code} for '{keyword}' in {location}")
            return new_jobs
        data = resp.json()
        for job in data.get("results", []):
            title = job.get("title", "Unknown Title")
            company = job.get("company", {}).get("display_name", "Unknown Company")
            link = job.get("redirect_url", "#")
            created = job.get("created", "")
            loc_display = job.get("location", {}).get("display_name", location)
            if not is_recent(created):
                continue
            jid = job_id(title, company, location)
            if jid not in seen_jobs:
                new_jobs.append({
                    "id": jid, "title": title, "company": company,
                    "location": location, "loc_display": loc_display,
                    "link": link, "created": created,
                })
                seen_jobs.add(jid)
    except Exception as e:
        print(f"[WARN] Adzuna error for '{keyword}' in {location}: {e}")
    return new_jobs

# ─────────────────────────────────────────────
# FETCH ALL
# ─────────────────────────────────────────────

def fetch_new_jobs(seen_jobs):
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_APP_KEY"]
    all_new = []
    for location in LOCATIONS:
        for keyword in KEYWORDS:
            jobs = fetch_adzuna_jobs(keyword, location, app_id, app_key, seen_jobs)
            if jobs:
                print(f"[INFO] {len(jobs)} new: '{keyword}' in {location}")
            all_new.extend(jobs)
            time.sleep(0.3)
    return all_new

# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def build_email_html(jobs):
    by_location = {}
    for job in jobs:
        by_location.setdefault(job["location"], []).append(job)
    now = datetime.now().strftime("%B %d, %Y · %I:%M %p")
    sections = ""
    for location, loc_jobs in sorted(by_location.items()):
        rows = ""
        for job in loc_jobs:
            rows += f"""
<div style="padding:18px 0;border-bottom:1px solid #e8e4de;">
  <div style="margin-bottom:6px;">
    <span style="font-size:15px;font-weight:500;color:#1a1916;">{job['title']}</span>
  </div>
  <div style="font-size:13px;color:#8c877e;margin-bottom:4px;">{job['company']}</div>
  <div style="font-size:12px;color:#b5b0a8;margin-bottom:10px;">{job['loc_display']}</div>
  <a href="{job['link']}" style="font-size:12px;font-weight:500;color:#c17f3e;text-decoration:none;border-bottom:1px solid #e8c99a;">View listing →</a>
</div>"""
        sections += f"""
<div style="margin-bottom:36px;">
  <div style="font-size:18px;font-weight:500;color:#1a1916;padding-bottom:10px;border-bottom:2px solid #1a1916;">
    {location} <span style="font-size:12px;color:#8c877e;margin-left:10px;">{len(loc_jobs)} new</span>
  </div>
  {rows}
</div>"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#faf9f6;">
<div style="max-width:600px;margin:0 auto;background:#faf9f6;">
  <div style="padding:40px 40px 24px;border-bottom:1px solid #e8e4de;">
    <div style="font-size:11px;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;color:#c17f3e;margin-bottom:16px;">JobPing by Swavna</div>
    <div style="font-family:'Playfair Display',Georgia,serif;font-size:32px;font-weight:400;color:#1a1916;line-height:1.15;margin-bottom:8px;">
      {len(jobs)} new listing{"s" if len(jobs) != 1 else ""}<br>
      <em style="font-style:italic;color:#c17f3e;">just dropped.</em>
    </div>
    <div style="font-size:12px;color:#b5b0a8;margin-top:12px;">{now}</div>
  </div>
  <div style="padding:14px 40px;background:#f3f1ec;border-bottom:1px solid #e8e4de;">
    <span style="font-size:11px;color:#8c877e;">
      Data Analyst &nbsp;·&nbsp; People Analyst &nbsp;·&nbsp; Product Manager &nbsp;·&nbsp; Business Analytics &nbsp;·&nbsp; Internships
    </span>
  </div>
  <div style="padding:32px 40px;">{sections}</div>
  <div style="padding:24px 40px;border-top:1px solid #e8e4de;font-size:11px;color:#b5b0a8;">
    Runs every 30 min · Powered by Adzuna · Built by Swavna Sahoo
  </div>
</div>
</body></html>"""

def send_email(jobs):
    sender = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password = os.environ["EMAIL_PASSWORD"]
    subject = f"JobPing: {len(jobs)} new listing{'s' if len(jobs) != 1 else ''} — {datetime.now().strftime('%b %d, %I:%M %p')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(build_email_html(jobs), "html"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"[OK] Email sent: {len(jobs)} jobs → {recipient}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print(f"[START] {datetime.now().isoformat()}")
    seen_jobs = load_seen_jobs()
    new_jobs = fetch_new_jobs(seen_jobs)
    print(f"[INFO] {len(new_jobs)} new jobs found total")
    if new_jobs:
        send_email(new_jobs)
    else:
        print("[INFO] No new jobs — no email sent")
    save_seen_jobs(seen_jobs)
    print("[DONE]")

if __name__ == "__main__":
    main()
