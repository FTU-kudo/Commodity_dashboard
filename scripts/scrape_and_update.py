"""
scripts/scrape_and_update.py
=============================
Runs inside GitHub Actions every weekday.
  1. Reads existing docs/data/commodities.json (finds last scraped date)
  2. Scrapes only NEW days from sunsirs.com
  3. Merges new records into the JSON
  4. Writes updated JSON back to docs/data/commodities.json
  5. GitHub Actions commits and pushes automatically
"""

import json
import time
import random
import requests
from pathlib import Path
from datetime import date, timedelta
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────
SERIES_START = date(2024, 1, 1)          # earliest date to ever scrape
TODAY        = date.today()
BASE_URL     = "https://sunsirs.com/uk/sdetail-day-{yyyy}-{mmdd}.html"
JSON_PATH    = Path("docs/data/commodities.json")
DELAY_MIN    = 1.5                        # seconds between requests
DELAY_MAX    = 3.0
MAX_RETRIES  = 3

# ── HTTP session ───────────────────────────────────────────────────────────────
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sunsirs.com/uk/",
})

# ── Load existing JSON ─────────────────────────────────────────────────────────
def load_existing() -> dict:
    if not JSON_PATH.exists():
        print("No existing data — will scrape full series from scratch.")
        return {"meta": {}, "commodities": [], "sectors": {}, "series": {}}
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    n_comms = len(data.get("commodities", []))
    period  = f"{data['meta'].get('period_from','')} → {data['meta'].get('period_to','')}"
    print(f"Loaded existing data: {n_comms} commodities · {period}")
    return data

# ── Find last scraped date ─────────────────────────────────────────────────────
def get_last_date(data: dict) -> date | None:
    all_dates = []
    for s in data.get("series", {}).values():
        all_dates.extend(s.get("dates", []))
    if not all_dates:
        return None
    return date.fromisoformat(max(all_dates))

# ── URL builder ────────────────────────────────────────────────────────────────
def build_url(d: date) -> str:
    return BASE_URL.format(yyyy=d.strftime("%Y"), mmdd=d.strftime("%m%d"))

# ── Fetch a page with retries ──────────────────────────────────────────────────
def fetch_page(url: str) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=20)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} (attempt {attempt}): {url}")
        except requests.RequestException as e:
            print(f"  Request error (attempt {attempt}): {e}")
        if attempt < MAX_RETRIES:
            time.sleep(5)
    return None

# ── Parse one day's HTML table ─────────────────────────────────────────────────
def parse_day(html: str, d: date) -> list[dict]:
    soup  = BeautifulSoup(html, "lxml")
    table = (
        soup.find("table", class_=lambda c: c and "com" in c.lower())
        or soup.find("table")
    )
    if not table:
        return []

    rows = table.find_all("tr")
    headers, data_rows = [], []
    for row in rows:
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True) for c in cells]
        if not texts:
            continue
        if not headers and row.find("th"):
            headers = texts
        else:
            data_rows.append(texts)

    if not headers and data_rows:
        headers = data_rows.pop(0)

    if len(headers) < 4:
        return []

    headers[2] = "Previous day price"
    headers[3] = "Current day price"

    records = []
    for row in data_rows:
        if not any(row):
            continue
        row = row[:len(headers)] + [""] * max(0, len(headers) - len(row))
        rec = {h: v for h, v in zip(headers, row)}
        rec["date"] = d.isoformat()
        records.append(rec)
    return records

# ── Date range generator ───────────────────────────────────────────────────────
def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)

# ── Clean a price string to float ─────────────────────────────────────────────
def clean_price(s: str) -> float | None:
    if not s:
        return None
    cleaned = "".join(c for c in s if c.isdigit() or c == ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None

# ── Merge new records into the existing data structure ─────────────────────────
def merge_records(data: dict, new_records: list[dict]) -> dict:
    series  = data.setdefault("series", {})
    sectors = data.setdefault("sectors", {})

    # Group by commodity
    by_comm: dict[str, list[dict]] = {}
    for rec in new_records:
        comm = rec.get("Commodity", "").strip()
        if not comm:
            continue
        by_comm.setdefault(comm, []).append(rec)
        sector = rec.get("Sectors", "").strip()
        if sector:
            sectors[comm] = sector

    for comm, records in by_comm.items():
        if comm not in series:
            series[comm] = {
                "dates": [], "current_price": [],
                "previous_price": [], "sector": ""
            }

        existing_dates = set(series[comm]["dates"])

        for rec in sorted(records, key=lambda r: r["date"]):
            d  = rec["date"]
            if d in existing_dates:
                continue
            cp = clean_price(rec.get("Current day price", ""))
            pp = clean_price(rec.get("Previous day price", ""))
            if cp is None:
                continue
            series[comm]["dates"].append(d)
            series[comm]["current_price"].append(cp)
            series[comm]["previous_price"].append(pp)
            series[comm]["sector"] = sectors.get(comm, "")

        # Keep sorted by date
        triples = sorted(zip(
            series[comm]["dates"],
            series[comm]["current_price"],
            series[comm]["previous_price"],
        ))
        if triples:
            series[comm]["dates"]          = [t[0] for t in triples]
            series[comm]["current_price"]  = [t[1] for t in triples]
            series[comm]["previous_price"] = [t[2] for t in triples]

    data["series"]      = series
    data["sectors"]     = sectors
    data["commodities"] = sorted(series.keys())
    return data

# ── Write updated JSON ─────────────────────────────────────────────────────────
def write_json(data: dict):
    all_dates = [d for s in data["series"].values() for d in s["dates"]]

    data["meta"] = {
        "last_updated"      : TODAY.isoformat(),
        "source"            : "sunsirs.com/uk",
        "period_from"       : min(all_dates) if all_dates else "",
        "period_to"         : max(all_dates) if all_dates else "",
        "total_commodities" : len(data["commodities"]),
    }

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = JSON_PATH.stat().st_size / 1024 / 1024
    print(f"\n✅  JSON written → {JSON_PATH}  ({size_mb:.1f} MB)")
    print(f"    Period    : {data['meta']['period_from']} → {data['meta']['period_to']}")
    print(f"    Commodities: {len(data['commodities'])}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  SunSirs Daily Updater")
    print(f"  Today: {TODAY}")
    print("=" * 55)

    data      = load_existing()
    last_date = get_last_date(data)

    if last_date is None:
        scrape_from = SERIES_START
        print(f"\nStarting fresh — scraping from {SERIES_START}")
    else:
        scrape_from = last_date + timedelta(days=1)
        print(f"\nLast saved date : {last_date}")
        print(f"Scraping from   : {scrape_from} → {TODAY}")

    # Only weekdays (SunSirs publishes Mon–Fri)
    dates_to_scrape = [
        d for d in date_range(scrape_from, TODAY)
        if d.weekday() < 5
    ]

    if not dates_to_scrape:
        print("\n✅  Already up to date — nothing to scrape!")
        write_json(data)    # still write to refresh meta.last_updated
        return

    print(f"\nScraping {len(dates_to_scrape)} new day(s)…\n")

    all_new_records = []
    empty_days      = []
    failed_days     = []

    for i, d in enumerate(dates_to_scrape):
        url  = build_url(d)
        html = fetch_page(url)

        if html is None:
            failed_days.append(str(d))
            print(f"  FAIL  {d}")
        else:
            records = parse_day(html, d)
            if records:
                all_new_records.extend(records)
                print(f"  OK    {d}  ({len(records)} commodities)")
            else:
                empty_days.append(str(d))
                print(f"  EMPTY {d}  (holiday or no data)")

        if i < len(dates_to_scrape) - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Merge and persist
    if all_new_records:
        print(f"\nMerging {len(all_new_records):,} new rows…")
        data = merge_records(data, all_new_records)

    write_json(data)

    # Summary
    if empty_days:
        print(f"\n  No-data days  : {len(empty_days)}")
    if failed_days:
        print(f"\n  ⚠ Failed days : {', '.join(failed_days)}")
        # Do NOT sys.exit(1) — partial data is better than a broken action


if __name__ == "__main__":
    main()
