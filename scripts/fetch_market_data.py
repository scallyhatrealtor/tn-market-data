#!/usr/bin/env python3
"""
Pulls Redfin's free public city-level housing market data, filters it down
to a specific list of East Tennessee service-area cities, and writes a
compact JSON file the website can fetch directly (via raw.githubusercontent.com).

Source: Redfin Data Center (city_market_tracker), refreshed monthly by Redfin
around the third Friday of each month.
https://www.redfin.com/news/data-center/

Run monthly via the GitHub Actions workflow in
.github/workflows/update-market-data.yml
"""

import gzip
import io
import json
import sys
from datetime import datetime, timezone

import urllib.request

REDFIN_CITY_TRACKER_URL = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/city_market_tracker.tsv000.gz"
)

# The exact "city, state" strings as they appear in Redfin's data.

# Redfin's CITY field is typically just the city name; STATE_CODE is the

# 2-letter code. We match on (city name, state code) pairs.

SERVICE_AREAS = [
    "Knoxville", "Farragut", "Maryville", "Alcoa", "Oak Ridge",
    "Lenoir City", "Loudon", "Seymour", "Sevierville", "Gatlinburg",
    "Pigeon Forge", "Powell", "Clinton", "Kingston", "Jefferson City",
    "Kodak", "Strawberry Plains", "Louisville", "Friendsville",
    "Greenback", "Mascot", "Rutledge", "Blaine", "Norris", "Rockford",
    "Walland", "Townsend", "Tellico Village",
]
STATE_CODE = "TN"

# Property type filter — Redfin's file has a row per (city, property_type,

# month). "All Residential" is the aggregate across single family, condo,

# and townhouse, which is the closest match to a general "market dashboard".

PROPERTY_TYPE = "All Residential"

# How many trailing months to keep for the trend charts.

TREND_MONTHS = 10

# Columns we actually need, keyed by the canonical Redfin field name.

# NOTE: Redfin has occasionally renamed columns across schema versions.

# If a run fails with a "missing column" error, check the printed header

# list in the Action log and update this mapping.

COLUMN_MAP = {
    "period_end": '"PERIOD_END"',
    "region_type": '"REGION_TYPE"',
    "city": '"CITY"',
    "state_code": '"STATE_CODE"',
    "property_type": '"PROPERTY_TYPE"',
    "median_sale_price": '"MEDIAN_SALE_PRICE"',
    "median_sale_price_yoy": '"MEDIAN_SALE_PRICE_YOY"',
    "median_ppsf": '"MEDIAN_PPSF"',
    "median_ppsf_yoy": '"MEDIAN_PPSF_YOY"',
    "median_dom": '"MEDIAN_DOM"',
    "median_dom_yoy": '"MEDIAN_DOM_YOY"',
    "homes_sold": '"HOMES_SOLD"',
    "homes_sold_yoy": '"HOMES_SOLD_YOY"',
    "new_listings": '"NEW_LISTINGS"',
    "new_listings_yoy": '"NEW_LISTINGS_YOY"',
    "inventory": '"INVENTORY"',
    "inventory_yoy": '"INVENTORY_YOY"',
    "price_drops": '"PRICE_DROPS"',
    "price_drops_yoy": '"PRICE_DROPS_YOY"',
    # pending_sales is NOT reliably present in the monthly city tracker file.
    # We leave it out of REQUIRED fields and only include it in the output
    # if the column exists — see build_row() below.
}

REQUIRED_FIELDS = [
    "period_end", "region_type", "city", "state_code", "property_type",
    "median_sale_price", "median_dom", "homes_sold", "new_listings",
    "inventory", "median_ppsf",
]

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

def download_and_open() -> io.TextIOWrapper:
    log(f"Downloading {REDFIN_CITY_TRACKER_URL} ...")
    req = urllib.request.Request(
        REDFIN_CITY_TRACKER_URL,
        headers={"User-Agent": "tn-market-data-fetcher/1.0"},
    )
    resp = urllib.request.urlopen(req, timeout=300)
    gz = gzip.GzipFile(fileobj=io.BytesIO(resp.read()))
    return io.TextIOWrapper(gz, encoding="utf-8", errors="replace")

def to_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None

def build_row(header, fields, col_index):
    def get(name):
        idx = col_index.get(name)
        if idx is None or idx >= len(fields):
            return None
        return fields[idx]

    return {
        "period_end": get("period_end"),
        "city": get("city"),
        "state_code": get("state_code"),
        "property_type": get("property_type"),
        "median_sale_price": to_float(get("median_sale_price")),
        "median_sale_price_yoy": to_float(get("median_sale_price_yoy")),
        "median_ppsf": to_float(get("median_ppsf")),
        "median_ppsf_yoy": to_float(get("median_ppsf_yoy")),
        "median_dom": to_float(get("median_dom")),
        "median_dom_yoy": to_float(get("median_dom_yoy")),
        "homes_sold": to_float(get("homes_sold")),
        "homes_sold_yoy": to_float(get("homes_sold_yoy")),
        "new_listings": to_float(get("new_listings")),
        "new_listings_yoy": to_float(get("new_listings_yoy")),
        "inventory": to_float(get("inventory")),
        "inventory_yoy": to_float(get("inventory_yoy")),
        "price_drops": to_float(get("price_drops")),
        "price_drops_yoy": to_float(get("price_drops_yoy")),
    }

def main():
    service_area_lookup = {name.lower() for name in SERVICE_AREAS}

    fh = download_and_open()
    header_line = fh.readline().rstrip("\n")
    header = header_line.split("\t")
    col_index = {
        canonical: i
        for i, name in enumerate(header)
        for canonical, redfin_name in COLUMN_MAP.items()
        if name == redfin_name
    }

    missing = [c for c in REQUIRED_FIELDS if c not in col_index]
    if missing:
        log(f"WARNING: expected columns not found in Redfin file: {missing}")
        log(f"Actual header columns: {header}")
        # Don't hard-fail — Redfin does occasionally tweak column names.
        # A partial run with whatever fields ARE present is still useful,
        # and the log above tells you exactly what to fix in COLUMN_MAP.

    by_city = {}  # city name -> list of monthly rows (unsorted)
    rows_scanned = 0
    rows_matched = 0

    for line in fh:
        rows_scanned += 1
        fields = line.rstrip("\n").split("\t")

        city_idx = col_index.get("city")
        state_idx = col_index.get("state_code")
        ptype_idx = col_index.get("property_type")
        if city_idx is None or state_idx is None or ptype_idx is None:
            break  # can't proceed without these

        if len(fields) <= max(city_idx, state_idx, ptype_idx):
            continue

        city_val = fields[city_idx].strip()
        state_val = fields[state_idx].strip()
        ptype_val = fields[ptype_idx].strip()

        if state_val != STATE_CODE:
            continue
        if ptype_val != PROPERTY_TYPE:
            continue
        if city_val.lower() not in service_area_lookup:
            continue

        rows_matched += 1
        row = build_row(header, fields, col_index)
        by_city.setdefault(city_val, []).append(row)

    fh.close()
    log(f"Scanned {rows_scanned} rows, matched {rows_matched} rows "
        f"across {len(by_city)} of {len(SERVICE_AREAS)} requested cities.")

    found_cities = {c.lower() for c in by_city.keys()}
    not_found = [c for c in SERVICE_AREAS if c.lower() not in found_cities]
    if not_found:
        log(f"NOTE: no rows found for these service areas (Redfin may not "
            f"track them at city level — consider a county-level fallback "
            f"for these): {not_found}")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Redfin Data Center (city_market_tracker, monthly)",
        "property_type_filter": PROPERTY_TYPE,
        "cities": {},
        "cities_with_no_data": not_found,
    }

    for city_val, rows in by_city.items():
        rows.sort(key=lambda r: r["period_end"] or "")
        latest = rows[-1]
        trend = rows[-TREND_MONTHS:]

        output["cities"][city_val] = {
            "latest": latest,
            "trend": [
                {
                    "period_end": r["period_end"],
                    "median_sale_price": r["median_sale_price"],
                    "homes_sold": r["homes_sold"],
                }
                for r in trend
            ],
        }

    with open("data/market-stats.json", "w") as f:
        json.dump(output, f, indent=2)

    log("Wrote data/market-stats.json")

if __name__ == "__main__":
    main()
