"""
CBRE Industrial Market Report Checker
--------------------------------------
Runs quarterly via GitHub Actions.
- Checks CBRE for new Industrial Figures reports across all 11 markets
- If new reports are found, sends an email alert via Microsoft 365 (Outlook)
- Updates the "Last updated" line in index.html automatically

Setup required (one time):
  In your GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
    OUTLOOK_EMAIL   = your work email (e.g. zeke@yourfirm.com)
    OUTLOOK_PASSWORD = your email password or app password
    NOTIFY_EMAILS   = comma-separated list of recipients (e.g. zeke@yourfirm.com,boss@yourfirm.com)
"""

import urllib.request
import smtplib
import ssl
import os
import json
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── MARKET DEFINITIONS ──────────────────────────────────────────────────────
# Each entry: (display_name, cbre_url_slug)
MARKETS = [
    ("Indianapolis, IN",        "indianapolis-industrial-figures"),
    ("Denver, CO",              "denver-industrial-figures"),
    ("Orlando / Central FL",    "orlando-industrial-figures"),
    ("Miami-Dade, FL",          "miami-dade-industrial-figures"),
    ("Broward County, FL",      "broward-industrial-figures"),
    ("Chicago, IL",             "chicago-industrial-figures"),
    ("Phoenix, AZ",             "phoenix-industrial-figures"),
    ("Columbus / Central OH",   "columbus-industrial-figures"),
    ("Cleveland / NE Ohio",     "cleveland-industrial-figures"),
    ("Cincinnati, OH",          "cincinnati-industrial-figures"),
    ("Louisville, KY",          "louisville-industrial-figures"),
    ("Nashville, TN",           "nashville-industrial-figures"),
]

# Quarters to check — script tries current and next quarter
def get_quarters_to_check():
    now = datetime.now()
    year = now.year
    month = now.month
    current_q = (month - 1) // 3 + 1
    quarters = []
    # Check last 2 quarters and current
    for offset in [-1, 0]:
        q = current_q + offset
        y = year
        if q < 1:
            q += 4
            y -= 1
        if q > 4:
            q -= 4
            y += 1
        quarters.append((q, y))
    return quarters

def check_url_exists(url):
    """Return True if the URL returns a 200 response."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MarketReportChecker/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False

def check_all_markets():
    """Check all markets for new reports. Returns list of (market_name, url, quarter_label)."""
    found = []
    quarters = get_quarters_to_check()

    for market_name, slug in MARKETS:
        for q_num, year in quarters:
            url = f"https://www.cbre.com/insights/figures/{slug}-q{q_num}-{year}"
            quarter_label = f"Q{q_num} {year}"
            print(f"  Checking {market_name} {quarter_label}... ", end="")
            if check_url_exists(url):
                print(f"✓ FOUND")
                found.append((market_name, url, quarter_label))
            else:
                print(f"not yet")

    return found

def load_previous_results():
    """Load previously found reports to avoid duplicate emails."""
    path = "found_reports.json"
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()

def save_results(found):
    """Save found report URLs so we don't re-alert on next run."""
    path = "found_reports.json"
    existing = load_previous_results()
    all_urls = existing | {url for _, url, _ in found}
    with open(path, "w") as f:
        json.dump(list(all_urls), f, indent=2)

def update_website(found):
    """Update the Last Updated timestamp in index.html."""
    path = "index.html"
    if not os.path.exists(path):
        print("  index.html not found, skipping website update")
        return

    with open(path) as f:
        content = f.read()

    now = datetime.now()
    # Find the most recent quarter in found reports
    if found:
        latest_label = found[-1][2]  # e.g. "Q2 2026"
    else:
        latest_label = f"Q{(now.month-1)//3+1} {now.year}"

    updated_date = now.strftime("%B %Y")

    # Update sidebar "Last updated" line
    content = re.sub(
        r'Last updated: <span id="last-updated">[^<]*</span>',
        f'Last updated: <span id="last-updated">{updated_date}</span>',
        content
    )

    # Update the quarter label in sidebar
    content = re.sub(
        r'<div class="quarter" id="sb-quarter">[^<]*</div>',
        f'<div class="quarter" id="sb-quarter">{latest_label}</div>',
        content
    )

    with open(path, "w") as f:
        f.write(content)

    print(f"  Website updated: Last updated → {updated_date}")

def send_email_alert(new_reports):
    """Send an Outlook/Microsoft 365 email alert listing new reports found."""
    sender = os.environ.get("OUTLOOK_EMAIL")
    password = os.environ.get("OUTLOOK_PASSWORD")
    recipients_raw = os.environ.get("NOTIFY_EMAILS", sender)
    recipients = [r.strip() for r in recipients_raw.split(",")]

    if not sender or not password:
        print("  No email credentials found — skipping email (set OUTLOOK_EMAIL and OUTLOOK_PASSWORD secrets)")
        return

    # Build email body
    report_lines_html = "".join([
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0D2240'>{name}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#374151'>{quarter}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #E2E8F0'><a href='{url}' style='color:#1F5C99'>View Report →</a></td></tr>"
        for name, url, quarter in new_reports
    ])

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#374151;max-width:600px;margin:0 auto">
      <div style="background:#0D2240;padding:24px 32px;border-radius:4px 4px 0 0">
        <div style="color:#7EC8E3;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">Industrial Submarket Report · Auto-Alert</div>
        <div style="color:white;font-size:22px;font-weight:800">New CBRE Reports Available</div>
        <div style="color:#94A3B8;font-size:13px;margin-top:4px">{len(new_reports)} new report{"s" if len(new_reports) > 1 else ""} detected · {datetime.now().strftime("%B %d, %Y")}</div>
      </div>
      <div style="background:white;border:1px solid #E2E8F0;border-top:none;padding:24px 32px">
        <p style="margin:0 0 16px">The following new CBRE Industrial Figures reports have been published and are now available:</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#F4F7FC">
              <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Market</th>
              <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Quarter</th>
              <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Link</th>
            </tr>
          </thead>
          <tbody>{report_lines_html}</tbody>
        </table>
        <div style="margin-top:24px;padding:16px;background:#EFF6FF;border-left:4px solid #1F5C99;border-radius:0 4px 4px 0;font-size:12px;color:#1E3A5F">
          <strong>Next step:</strong> Review each new report and update the website data at
          <a href="https://zekerichardson22.github.io/industrial-report" style="color:#1F5C99">zekerichardson22.github.io/industrial-report</a>
          with the latest figures.
        </div>
      </div>
      <div style="padding:16px 32px;font-size:11px;color:#94A3B8;border-top:1px solid #E2E8F0">
        This alert was sent automatically by your GitHub Actions workflow · To unsubscribe, update NOTIFY_EMAILS in your GitHub repository secrets.
      </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏭 {len(new_reports)} New CBRE Industrial Report{'s' if len(new_reports) > 1 else ''} Available — {datetime.now().strftime('%B %Y')}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    # Microsoft 365 SMTP settings
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.office365.com", 587) as server:
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"  Email sent to: {', '.join(recipients)}")
    except Exception as e:
        print(f"  Email failed: {e}")
        print("  Tip: Make sure OUTLOOK_EMAIL and OUTLOOK_PASSWORD secrets are set correctly in GitHub.")

def main():
    print(f"\n{'='*60}")
    print(f"CBRE Report Checker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    print("Checking all markets for new CBRE reports...\n")
    all_found = check_all_markets()

    print(f"\nTotal reports found: {len(all_found)}")

    # Filter to only NEW reports (not previously emailed)
    previous = load_previous_results()
    new_reports = [(name, url, quarter) for name, url, quarter in all_found if url not in previous]

    print(f"New reports (not previously alerted): {len(new_reports)}")

    if new_reports:
        print("\nNew reports found:")
        for name, url, quarter in new_reports:
            print(f"  • {name} {quarter}: {url}")

        print("\nUpdating website...")
        update_website(new_reports)

        print("\nSending email alert...")
        send_email_alert(new_reports)

        print("\nSaving results...")
        save_results(all_found)
    else:
        print("\nNo new reports since last check — no email sent.")
        # Still update the timestamp
        update_website([])

    print(f"\n{'='*60}")
    print("Check complete.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
