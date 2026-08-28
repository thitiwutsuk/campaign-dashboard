# Campaign Dashboard

[![Live Demo](https://img.shields.io/badge/Live%20Demo-campaign--dashboard.streamlit.app-06C755?style=flat-square&logo=streamlit&logoColor=white)](https://campaign-dashboard-hojogusrcfkpzhow56trpd.streamlit.app/)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-3.0-150458?style=flat-square&logo=pandas&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.62-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-3DA639?style=flat-square&logo=opensourceinitiative&logoColor=white)
![Progress](https://img.shields.io/badge/Progress-Complete-06C755?style=flat-square)

Reconciles three disconnected, intentionally messy retail data sources — CRM, POS, and ad
platform exports — into one trustworthy dataset, then surfaces per-campaign ROI on a live
Streamlit dashboard.

## Preview

| Overview | Campaign ROI |
|---|---|
| ![Overview tab](docs/img/overview.png) | ![Campaign ROI tab](docs/img/campaign-roi.png) |

## Highlights

- Cleaned and reconciled 12,400+ records across 3 mismatched schemas (90 days, 5 campaigns) —
  duplicate keys, mixed date/currency formats, and inconsistent categorical values, all resolved
  through explicit, testable rules rather than manual fixes.
- Joined POS, CRM, and ad-spend data on non-matching keys to compute real per-campaign ROAS
  (1.9x–7.3x) — no unrealistic double-digit outliers.
- Quantified the gap between platform-reported and real conversions: only 61% of ad-reported
  conversions reconcile to an actual POS order.
- Fully automated: one script regenerates raw data, one script cleans and reconciles it, and the
  dashboard reads only the processed output — no manual steps in between.

## Tech Stack

Python · Pandas · Streamlit · Plotly

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 scripts/generate_synthetic_data.py   # generate raw data
python3 scripts/run_pipeline.py              # clean + reconcile
streamlit run app.py                         # launch dashboard
```
Requires Python 3.11+.

## How It Works

```
data/raw/*.csv → src/cleaning.py → src/reconcile.py → data/processed/*.csv → app.py
```

1. **Ingest** — 3 raw CSVs simulate a CRM, POS system, and ad platform export, each with its own
   schema quirks (`scripts/generate_synthetic_data.py`).
2. **Clean** (`src/cleaning.py`) — unify date/currency formats, collapse duplicate category
   spellings via alias tables, dedupe rows, flag rather than drop expected edge cases.
3. **Reconcile** (`src/reconcile.py`) — join across mismatched keys (`customer_ref` ↔ `cust_id`,
   `campaign_code` ↔ `campaign_id`) to compute per-campaign ROI.
4. **Serve** (`app.py`) — the dashboard reads only the cleaned output; its Data Quality tab shows
   exactly what was fixed, sourced live from the same pipeline run.

## Project Structure

```
campaign-dashboard/
├── data/
│   ├── raw/            # synthetic source CSVs
│   └── processed/      # cleaned + reconciled output (run_pipeline.py)
├── scripts/
│   ├── generate_synthetic_data.py
│   └── run_pipeline.py
├── src/
│   ├── cleaning.py
│   └── reconcile.py
├── app.py               # Streamlit dashboard
└── requirements.txt
```

## Deployment Notes

Deployed on Streamlit Community Cloud. One gotcha worth flagging for anyone reusing this setup:
Cloud ignores `runtime.txt` and always runs its own current default Python — pin dependency
*versions* with wheels for a recent Python instead of trying to pin the interpreter itself.
