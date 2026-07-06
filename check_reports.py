"""
CBRE Industrial Market Report Checker
--------------------------------------
Runs 4 times per year on January 10, April 10, July 10, and October 10.
Checks all 11 markets at once and sends ONE summary email.
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

MARKETS = [
    ("Indianapolis, IN",        "indianapolis-industrial-figures"),
    ("Denver, CO",              "denver-industrial-figures"),
    ("Orlando / Central FL",    "orlando-industrial-figures"),
    ("Miami-Dade, FL",          "miami-dade-industrial-figures"),
    ("Chicago, IL",             "chicago-industrial-figures"),
    ("Phoenix, AZ",             "phoenix-industrial-figures"),
    ("Columbus / Central OH",   "columbus-industrial-figures"),
    ("Cleveland / NE Ohio",     "cleveland-industrial-figures"),
    ("Cincinnati, OH",          "cincinnati-industrial-figures"),
    ("Louisville, KY",          "louisville-industrial-figures"),
    ("Nashville, TN",           "nashville-industrial-figures"),
]

def get_quarters_to_check():
    now = datetime.now()
    year = now.year
    month = now.month
    current_q = (month - 1) // 3 + 1
    quarters = []
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
                break  # found latest, stop checking older quarters
            else:
                print(f"not yet")
    return found

def load_previous_results():
    path = "found_reports.json"
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()

def save_results(found):
    path = "found_reports.json"
    existing = load_previous_results()
    all_urls = existing | {url for _, url, _ in found}
    with open(path, "w") as f:
        json.dump(list(all_urls), f, indent=2)

def update_website(found):
    path = "index.html"
    if not os.path.exists(path):
        print("  index.html not found, skipping website update")
        return
    with open(path) as f:
        content = f.read()
    now = datetime.now()
    updated_date = now.strftime("%B %Y")
    content = re.sub(
        r'Last updated: <span id="last-updated">[^<]*</span>',
        f'Last updated: <span id="last-updated">{updated_date}</span>',
        content
    )
    with open(path, "w") as f:
        f.write(content)
    print(f"  Website timestamp updated → {updated_date}")

def send_email_alert(new_reports, all_found):
    sender = os.environ.get("OUTLOOK_EMAIL")
    password = os.environ.get("OUTLOOK_PASSWORD")
    recipients_raw = os.environ.get("NOTIFY_EMAILS", sender)
    recipients = [r.strip() for r in recipients_raw.split(",")]

    if not sender or not password:
        print("  No email credentials — skipping email")
        return

    now_dt = datetime.now()
    q_num = (now_dt.month - 1) // 3 + 1
    q_month = {1: "January", 2: "April", 3: "July", 4: "October"}[q_num]

    total = len(all_found)
    new = len(new_reports)

    # Build market status rows
    found_names = {name for name, _, _ in all_found}
    all_market_names = [m[0] for m in MARKETS]

    rows_html = ""
    for name in all_market_names:
        if name in found_names:
            match = next((r for r in all_found if r[0] == name), None)
            quarter = match[2] if match else ""
            is_new = name in {r[0] for r in new_reports}
            badge = '<span style="background:#D1FAE5;color:#065F46;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">NEW</span>' if is_new else '<span style="background:#F1F5F9;color:#64748B;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;">Available</span>'
            rows_html += f"<tr><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0D2240'>{name}</td><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#374151;text-align:center'>{quarter}</td><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:center'>{badge}</td></tr>"
        else:
            rows_html += f"<tr><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#6B7280'>{name}</td><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#9CA3AF;text-align:center'>—</td><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:center'><span style='background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;'>Not Yet</span></td></tr>"

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#374151;max-width:620px;margin:0 auto;padding:0">
      <div style="background:#0D2240;padding:32px 40px;border-radius:4px 4px 0 0">
        <div style="color:#7EC8E3;font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:10px">Ambrose Industrial · Quarterly Report Alert</div>
        <div style="color:white;font-size:26px;font-weight:800;line-height:1.2">Q{q_num} {now_dt.year} CBRE Reports — {total} of {len(MARKETS)} Available</div>
        <div style="color:#94A3B8;font-size:13px;margin-top:8px;font-weight:300">Checked {now_dt.strftime("%B %d, %Y")} &nbsp;·&nbsp; {new} new since last check</div>
      </div>
      <div style="background:white;border:1px solid #E2E8F0;border-top:none;padding:32px 40px">
        <p style="margin:0 0 20px;font-size:14px;line-height:1.7;color:#374151">
          Here is the full status of Q{q_num} {now_dt.year} CBRE Industrial Figures reports across all 11 Ambrose markets.
          Once you are ready, update the website using the quarterly update prompt in your handoff guide.
        </p>
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:24px">
          <thead>
            <tr style="background:#F4F7FC">
              <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Market</th>
              <th style="padding:8px 12px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Quarter</th>
              <th style="padding:8px 12px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6B7280">Status</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        <div style="text-align:center;margin:28px 0">
          <a href="https://ambrosequarterly.github.io/industrial-report"
             style="background:#0D2240;color:white;text-decoration:none;padding:14px 32px;font-size:14px;font-weight:700;border-radius:4px;display:inline-block">
            View the Report →
          </a>
        </div>
        <div style="background:#F4F7FC;border-radius:4px;padding:14px 18px;font-size:12px;color:#6B7280;line-height:1.7">
          <strong style="color:#0D2240">Next step:</strong> If all or most markets show "Available," run the quarterly Claude update prompt to refresh the website with new data. If some markets still show "Not Yet," you may want to wait a few more days before updating.
        </div>
      </div>
      <div style="padding:16px 40px;font-size:11px;color:#94A3B8;text-align:center">
        Sent automatically on the 10th of January, April, July & October · <a href="https://ambrosequarterly.github.io/industrial-report" style="color:#94A3B8">ambrosequarterly.github.io/industrial-report</a>
      </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Ambrose Quarterly Report Available - {q_month} {now_dt.year}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.office365.com", 587) as server:
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"  Email sent to: {', '.join(recipients)}")
    except Exception as e:
        print(f"  Email failed: {e}")

def main():
    print(f"\n{'='*60}")
    print(f"CBRE Report Checker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    print("Checking all 11 markets...\n")
    all_found = check_all_markets()

    previous = load_previous_results()
    new_reports = [(name, url, quarter) for name, url, quarter in all_found if url not in previous]

    print(f"\nTotal reports found: {len(all_found)}/11")
    print(f"New since last check: {len(new_reports)}")

    print("\nSending quarterly summary email...")
    send_email_alert(new_reports, all_found)

    print("\nUpdating website timestamp...")
    update_website(all_found)

    print("\nSaving results...")
    save_results(all_found)

    print(f"\n{'='*60}")
    print("Check complete.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
