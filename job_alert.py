import json
import os
import smtplib
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

JOB_SEARCHES = [
    # (keyword, location, location_label)
    # Buffalo, NY
    ("data analyst", "Buffalo, New York, United States", "Buffalo, NY"),
    ("people analyst", "Buffalo, New York, United States", "Buffalo, NY"),
    ("product manager", "Buffalo, New York, United States", "Buffalo, NY"),
    ("business analytics", "Buffalo, New York, United States", "Buffalo, NY"),
    ("data analyst intern", "Buffalo, New York, United States", "Buffalo, NY"),

    # Rochester, NY
    ("data analyst", "Rochester, New York, United States", "Rochester, NY"),
    ("people analyst", "Rochester, New York, United States", "Rochester, NY"),
    ("product manager", "Rochester, New York, United States", "Rochester, NY"),
    ("business analytics", "Rochester, New York, United States", "Rochester, NY"),
    ("data analyst intern", "Rochester, New York, United States", "Rochester, NY"),

    # Atlanta, GA
    ("data analyst", "Atlanta, Georgia, United States", "Atlanta, GA"),
    ("people analyst", "Atlanta, Georgia, United States", "Atlanta, GA"),
    ("product manager", "Atlanta, Georgia, United States", "Atlanta, GA"),
    ("business analytics", "Atlanta, Georgia, United States", "Atlanta, GA"),
    ("data analyst intern", "Atlanta, Georgia, United States", "Atlanta, GA"),

    # San Diego, CA
    ("data analyst", "San Diego, California, United States", "San Diego, CA"),
    ("people analyst", "San Diego, California, United States", "San Diego, CA"),
    ("product manager", "San Diego, California, United States", "San Diego, CA"),
    ("business analytics", "San Diego, California, United States", "San Diego, CA"),
    ("data analyst intern", "San Diego, California, United States", "San Diego, CA"),

    # Puerto Rico
    ("data analyst", "Puerto Rico", "Puerto Rico"),
    ("people analyst", "Puerto Rico", "Puerto Rico"),
    ("product manager", "Puerto Rico", "Puerto Rico"),
    ("business analytics", "Puerto Rico", "Puerto Rico"),
    ("data analyst intern", "Puerto Rico", "Puerto Rico"),

    # Washington DC
    ("data analyst", "Washington DC, United States", "Washington DC"),
    ("people analyst", "Washington DC, United States", "Washington DC"),
    ("product manager", "Washington DC, United States", "Washington DC"),
    ("business analytics", "Washington DC, United States", "Washington DC"),
    ("data analyst intern", "Washington DC, United States", "Washington DC"),
]

SEEN_JOBS_FILE = "seen_jobs.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def job_id(title, company, location):
    unique_str = f"{title}-{company}-{location}"
    return hashlib.md5(unique_str.encode()).hexdigest()

def load_seen_jobs():
    if Path(SEEN_JOBS_FILE).exists():
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)

# ─────────────────────────────────────────────
# JOB FETCHING
# ─────────────────────────────────────────────

def fetch_jobs_for_search(keyword, location, location_label, seen_jobs):
    new_jobs = []
    keyword_encoded = keyword.replace(" ", "%20")
    location_encoded = location.replace(" ", "%20").replace(",", "%2C")

    url = (
        f"https://www.linkedin.com/jobs/search?"
        f"keywords={keyword_encoded}"
        f"&location={location_encoded}"
        f"&f_TPR=r3600"
        f"&sortBy=DD"
        f"&position=1&pageNum=0"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] Status {resp.status_code} for '{keyword}' in {location_label}")
            return new_jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        job_cards = soup.find_all("div", class_="base-card")

        if not job_cards:
            # Try alternate card class
            job_cards = soup.find_all("li", class_="jobs-search__results-list")

        for card in job_cards[:10]:
            try:
                title_el = card.find("h3") or card.find("span", class_="sr-only")
                company_el = card.find("h4") or card.find("a", {"data-tracking-control-name": "public_jobs_jserp-result_job-search-card-subtitle"})
                link_el = card.find("a", href=True)

                title = title_el.get_text(strip=True) if title_el else "Unknown Title"
                company = company_el.get_text(strip=True) if company_el else "Unknown Company"
                link = link_el["href"] if link_el else "#"

                # Clean link
                if "?" in link:
                    link = link.split("?")[0]

                jid = job_id(title, company, location_label)
                if jid not in seen_jobs:
                    new_jobs.append({
                        "id": jid,
                        "title": title,
                        "company": company,
                        "location": location_label,
                        "link": link,
                        "keyword": keyword,
                    })
                    seen_jobs.add(jid)
            except Exception as e:
                print(f"[WARN] Error parsing card: {e}")

    except Exception as e:
        print(f"[WARN] Failed to fetch '{keyword}' in {location_label}: {e}")

    return new_jobs


def fetch_new_jobs(seen_jobs):
    all_new = []
    for keyword, location, location_label in JOB_SEARCHES:
        jobs = fetch_jobs_for_search(keyword, location, location_label, seen_jobs)
        if jobs:
            print(f"[INFO] Found {len(jobs)} new jobs for '{keyword}' in {location_label}")
        all_new.extend(jobs)
        time.sleep(2)  # polite delay between requests
    return all_new

# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def build_email_html(jobs):
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
              <div style="font-size:13px;color:#555;margin-bottom:10px;">{job['company']} &nbsp;·&nbsp; {job['location']}</div>
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
    <!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#fff;">
      <div style="max-width:680px;margin:0 auto;padding:32px 24px;">
        <div style="background:#0077b5;color:#fff;padding:24px 28px;border-radius:8px 8px 0 0;">
          <div style="font-size:22px;font-weight:800;">🔔 LinkedIn Job Alert</div>
          <div style="font-size:13px;opacity:0.85;margin-top:4px;">{now} · {len(jobs)} new listing{"s" if len(jobs)!=1 else ""}</div>
        </div>
        <div style="background:#e8f4fb;padding:12px 20px;font-size:13px;color:#005f8a;margin-bottom:28px;">
          🎯 <strong>Data Analyst · People Analyst · Product Manager · Business Analytics · Internships</strong><br>
          📌 Buffalo · Rochester · Atlanta · San Diego · Puerto Rico · Washington DC
        </div>
        {sections}
        <div style="border-top:1px solid #e5e5e5;padding-top:18px;font-size:12px;color:#aaa;text-align:center;">
          Auto-generated · Runs every 15 minutes · Powered by GitHub Actions
        </div>
      </div>
    </body></html>
    """

def send_email(jobs):
    sender    = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password  = os.environ["EMAIL_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    subject = f"🔔 {len(jobs)} New LinkedIn Job{'s' if len(jobs)!=1 else ''} — {datetime.now().strftime('%b %d, %I:%M %p')}"
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
    print(f"[INFO] {len(new_jobs)} new jobs found")

    if new_jobs:
        send_email(new_jobs)
        save_seen_jobs(seen_jobs)
    else:
        print("[INFO] No new jobs — no email sent")

    print("[DONE]")

if __name__ == "__main__":
    main()
