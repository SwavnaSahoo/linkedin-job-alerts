# 🔔 LinkedIn Job Alert — GitHub Actions

Automatically checks LinkedIn for new job postings every **30 minutes** and sends you an email when new listings appear.

## What It Tracks

**Roles:** Data Analyst · People Analyst · Product Manager · Business Analytics · Data Analyst Intern

**Locations:** Buffalo NY · Rochester NY · Atlanta GA · San Diego CA · Puerto Rico

---

## Setup (One-Time, ~10 Minutes)

### Step 1 — Create a GitHub Repo

1. Go to [github.com](https://github.com) and click **New Repository**
2. Name it something like `linkedin-job-alerts`
3. Set it to **Private** (recommended)
4. Click **Create repository**

### Step 2 — Upload These Files

Upload the following files to your repo (drag & drop on GitHub or use Git):

```
linkedin-job-alerts/
├── job_alert.py
├── requirements.txt
└── .github/
    └── workflows/
        └── job_alert.yml
```

> ⚠️ The `.github/workflows/` folder structure is important — GitHub Actions needs it exactly like this.

### Step 3 — Set Up a Gmail App Password

Gmail requires an **App Password** (not your regular password) for scripts.

1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** if not already on
3. Go to **Security → App passwords**
4. Select app: **Mail**, device: **Other** → name it "LinkedIn Alert"
5. Copy the 16-character password shown (e.g. `abcd efgh ijkl mnop`)

### Step 4 — Add GitHub Secrets

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add these three:

| Secret Name | Value |
|---|---|
| `EMAIL_SENDER` | Your Gmail address (e.g. `you@gmail.com`) |
| `EMAIL_RECIPIENT` | Where alerts go (can be same address) |
| `EMAIL_PASSWORD` | The 16-char App Password from Step 3 |

### Step 5 — Enable GitHub Actions

1. Go to the **Actions** tab in your repo
2. Click **"I understand my workflows, go ahead and enable them"**
3. Click on **LinkedIn Job Alert** → **Run workflow** to test it manually

---

## How It Works

- Runs automatically every **30 minutes** via GitHub Actions cron
- Fetches LinkedIn's RSS job feeds for each keyword + location combo
- Tracks which jobs you've already seen (deduplication via cache)
- If new jobs are found → sends a formatted HTML email
- If no new jobs → does nothing (no spam)

## Customizing

### Change how often it runs
Edit `.github/workflows/job_alert.yml`:
```yaml
- cron: "*/30 * * * *"   # every 30 min
- cron: "*/15 * * * *"   # every 15 min
- cron: "0 * * * *"      # every hour
```

### Add more keywords or locations
Edit `job_alert.py` — the `JOB_SEARCHES` list at the top:
```python
JOB_SEARCHES = [
    ("your keyword", "location_id", "Location Label"),
    ...
]
```

**Common LinkedIn Location IDs:**
| City | ID |
|---|---|
| Buffalo, NY | 103783015 |
| Rochester, NY | 104377157 |
| Atlanta, GA | 103516136 |
| San Diego, CA | 104577020 |
| Puerto Rico | 104746898 |
| New York City | 102571732 |
| Chicago, IL | 103112676 |
| Austin, TX | 103988087 |
| Remote | 90000070 |

---

## Troubleshooting

**No emails received?**
- Check the Actions tab — click the latest run to see logs
- Make sure your Gmail App Password is correct (no spaces)
- Check your spam folder

**"Authentication failed" error?**
- Re-generate your Gmail App Password
- Make sure 2-Step Verification is enabled on your Google account

**GitHub Actions not running?**
- GitHub may pause scheduled workflows on repos with no recent commits
- Just push a small change or manually trigger via the Actions tab

---

## Notes

- This uses LinkedIn's **public RSS feeds** — no API key or LinkedIn account required
- GitHub Actions free tier gives you **2,000 minutes/month** — more than enough for 30-min checks
- The `seen_jobs.json` cache is stored via GitHub Actions cache — it persists between runs
