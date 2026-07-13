"""
Ambrose Quarterly CBRE Report Checker (v2)
Fixes vs. v1:
  1. NASHVILLE FIX: CBRE's Nashville slug has always included "-report-"
     (nashville-industrial-figures-report-qX-YYYY). v1 checked the wrong
     URL and reported "Not Yet" forever. v2 tries multiple slug variants
     per market, in order, and reports the first one that exists.
  2. MIAMI/ANY-MARKET RESILIENCE: CBRE occasionally inserts "-report-"
     into other markets' slugs (e.g., miami-office-figures-report-q1-2026).
     Every market now gets both variants checked automatically.
  3. QUARTER LABELING FIX: the email header previously said "Q3 2026"
     while checking Q2 reports (off-by-one: it used the CURRENT calendar
     quarter instead of the most recently COMPLETED quarter). last_completed_quarter()
     below returns the just-ended quarter, which is what CBRE publishes.
  4. SOFT-404 DETECTION: CBRE returns HTTP 200 with a generic page for
     some bad slugs. We verify the page title/body actually mentions the
     target quarter before calling it "Available."

Run quarterly via GitHub Actions on Jan/Apr/Jul/Oct 10 (CBRE market-level
Industrial Figures have been publishing ~8-9 days after quarter close:
Q1 2026 published Apr 9; Cincinnati Q2 2026 published ~Jul 9).
If some markets show "Not Yet" on the 10th, re-run daily until all clear -
publication is staggered across a few days.
"""

import datetime
import sys
import urllib.request

BASE = "https://www.cbre.com/insights/figures/"

# Slug templates per market, tried IN ORDER. {q}=q2, {y}=2026.
# First template = the pattern used most recently by CBRE.
MARKETS = {
    "Indianapolis, IN": [
        "indianapolis-industrial-figures-{q}-{y}",
        "indianapolis-industrial-figures-report-{q}-{y}",
    ],
    "Denver, CO": [
        "denver-industrial-figures-{q}-{y}",
        "denver-industrial-figures-report-{q}-{y}",
    ],
    "Orlando / Central FL": [
        "orlando-industrial-figures-{q}-{y}",
        "orlando-industrial-figures-report-{q}-{y}",
    ],
    "Miami-Dade, FL": [
        "miami-industrial-figures-{q}-{y}",
        "miami-industrial-figures-report-{q}-{y}",
    ],
    "Broward, FL": [
        "broward-industrial-figures-{q}-{y}",
        "broward-industrial-figures-report-{q}-{y}",
    ],
    "Chicago, IL": [
        "chicago-industrial-figures-{q}-{y}",
        "chicago-industrial-figures-report-{q}-{y}",
    ],
    "Phoenix, AZ": [
        "phoenix-industrial-figures-{q}-{y}",
        "phoenix-industrial-figures-report-{q}-{y}",
    ],
    # NOTE: CBRE does not reliably publish a quarterly Columbus Industrial
    # Figures report (last one was Q4 2025). Keep checking, but treat a
    # persistent "Not Yet" here as expected, not an error. Columbus page on
    # the site is sourced from Colliers/Newmark/C&W instead.
    "Columbus / Central OH": [
        "columbus-industrial-figures-{q}-{y}",
        "columbus-industrial-figures-report-{q}-{y}",
    ],
    "Cleveland / NE Ohio": [
        "cleveland-industrial-figures-{q}-{y}",
        "cleveland-industrial-figures-report-{q}-{y}",
    ],
    "Cincinnati, OH": [
        "cincinnati-industrial-figures-{q}-{y}",
        "cincinnati-industrial-figures-report-{q}-{y}",
    ],
    "Louisville, KY": [
        "louisville-industrial-figures-{q}-{y}",
        "louisville-industrial-figures-report-{q}-{y}",
    ],
    # FIX: "-report-" variant FIRST for Nashville - it's the only pattern
    # CBRE has ever used for this market (verified back to Q4 2022).
    "Nashville, TN": [
        "nashville-industrial-figures-report-{q}-{y}",
        "nashville-industrial-figures-{q}-{y}",
    ],
}

HEADERS = {
    # A browser-like UA avoids bot-blocking on cbre.com
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def last_completed_quarter(today=None):
    """Return (quarter_label, year) for the most recently COMPLETED quarter.
    Jul 10, 2026 -> ('q2', 2026). Jan 10, 2026 -> ('q4', 2025)."""
    today = today or datetime.date.today()
    q_now = (today.month - 1) // 3 + 1  # current calendar quarter 1-4
    if q_now == 1:
        return "q4", today.year - 1
    return f"q{q_now - 1}", today.year


def page_exists_for_quarter(url, quarter, year, timeout=20):
    """True only if the URL loads AND the page content references the target
    quarter (guards against CBRE soft-404s that return HTTP 200)."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read(200_000).decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    q_num = quarter[1]
    needles = (f"{quarter} {year}", f"q{q_num} {year}", f"q{q_num}&nbsp;{year}")
    return any(n in body for n in needles)


def check_all(quarter=None, year=None):
    if quarter is None or year is None:
        quarter, year = last_completed_quarter()
    results = {}
    for market, templates in MARKETS.items():
        found_url = None
        for tpl in templates:
            url = BASE + tpl.format(q=quarter, y=year)
            if page_exists_for_quarter(url, quarter, year):
                found_url = url
                break
        results[market] = found_url
    return quarter, year, results


if __name__ == "__main__":
    quarter, year, results = check_all()
    label = f"{quarter.upper()} {year}"
    available = {m: u for m, u in results.items() if u}
    pending = [m for m, u in results.items() if not u]

    print(f"CBRE Industrial Figures status - {label}")
    print(f"Available: {len(available)}/{len(MARKETS)}\n")
    for market, url in results.items():
        status = f"AVAILABLE  {url}" if url else "NOT YET"
        print(f"  {market:<26} {status}")

    if pending:
        print("\nPending markets (re-run tomorrow):", ", ".join(pending))
        # Exit code 1 lets a GitHub Action re-schedule / notify accordingly
        sys.exit(1)
