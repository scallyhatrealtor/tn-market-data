# tn-market-data

Monthly East Tennessee housing market stats for the Market Dashboard page on
samuelwellsrealestate site (Lovable/Supabase).

## What this does

Once a month, a GitHub Action:
1. Downloads Redfin's free public city-level market data file
2. Filters it down to ~28 East Tennessee service-area cities
3. Writes the result to `data/market-stats.json`
4. Commits that file back to this repo

The website fetches `data/market-stats.json` directly from:
```
https://raw.githubusercontent.com/scallyhatrealtor/tn-market-data/main/data/market-stats.json
```
No API calls, no backend processing on the site's side — just one fetch of
a small JSON file.

## Setup (one-time)

1. Push these files to the repo (root, `.github/workflows/`, `scripts/`, and
   an empty `data/` folder).
2. Go to the repo's **Actions** tab and click into
   "Update TN market data" → **Run workflow** to trigger the first run
   manually (don't wait for the schedule).
3. Check the run log for two things:
   - Any `WARNING: expected columns not found` message — Redfin
     occasionally renames a column; the log tells you exactly what changed
     so `scripts/fetch_market_data.py`'s `COLUMN_MAP` can be updated.
   - The `NOTE: no rows found for these service areas` line — lists any of
     the ~28 cities that don't show up in Redfin's city-level file at all
     (small towns sometimes only have county-level data). The site's
     display logic should handle a city being absent from the JSON
     gracefully (e.g., fall back to a county-level stat, or hide that
     card).
4. Confirm `data/market-stats.json` got committed after the run.

After that, it runs itself on the 22nd of every month.

## Editing the city list

Edit the `SERVICE_AREAS` list near the top of
`scripts/fetch_market_data.py`, then re-run the workflow manually once to
pick up the change immediately.

## Data source & attribution

Data from the [Redfin Data Center](https://www.redfin.com/news/data-center/),
used per Redfin's terms with attribution. The live site should credit
Redfin near the Market Dashboard stats.
