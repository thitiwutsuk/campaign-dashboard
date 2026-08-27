"""
Runs Step 3 (cleaning) and Step 4 (reconciliation) end to end:
loads the 3 raw CSVs, cleans each, joins them, and writes the results to
data/processed/. Prints a data-quality report summarizing every fix applied.

Run: python3 scripts/run_pipeline.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cleaning import clean_ad, clean_crm, clean_pos
from src.reconcile import build_campaign_summary, build_unified_sales

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def print_report(name: str, report: dict) -> None:
    print(f"\n{name}")
    for key, value in report.items():
        print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    crm_raw = pd.read_csv(RAW_DIR / "crm_customers.csv")
    pos_raw = pd.read_csv(RAW_DIR / "pos_transactions.csv")
    ad_raw = pd.read_csv(RAW_DIR / "ad_platform_report.csv")
    campaign_registry = pd.read_csv(RAW_DIR / "campaign_registry.csv")

    crm_clean, crm_report = clean_crm(crm_raw)
    pos_clean, pos_report = clean_pos(pos_raw)
    ad_clean, ad_report = clean_ad(ad_raw)

    print_report("Step 3 — crm_customers cleaning", crm_report)
    print_report("Step 3 — pos_transactions cleaning", pos_report)
    print_report("Step 3 — ad_platform_report cleaning", ad_report)

    unified_sales, join_report = build_unified_sales(pos_clean, crm_clean, campaign_registry)
    campaign_summary = build_campaign_summary(unified_sales, ad_clean)

    print_report("Step 4 — reconciliation / join layer", join_report)
    print(f"\nStep 4 — per-campaign ROI ({len(campaign_summary)} campaigns, showing top/bottom 5 by ROAS)")
    print(
        pd.concat([campaign_summary.head(5), campaign_summary.tail(5)])[
            ["campaign_id", "ad_spend_thb", "attributed_revenue_thb", "roas", "roi_pct"]
        ].to_string(index=False)
    )

    crm_clean.to_csv(OUT_DIR / "crm_customers_clean.csv", index=False)
    pos_clean.to_csv(OUT_DIR / "pos_transactions_clean.csv", index=False)
    ad_clean.to_csv(OUT_DIR / "ad_platform_report_clean.csv", index=False)
    unified_sales.to_csv(OUT_DIR / "unified_sales.csv", index=False)
    campaign_summary.to_csv(OUT_DIR / "campaign_summary.csv", index=False)

    quality_report = {
        "crm_customers": crm_report,
        "pos_transactions": pos_report,
        "ad_platform_report": ad_report,
        "reconciliation": join_report,
    }
    with open(OUT_DIR / "quality_report.json", "w") as f:
        json.dump(quality_report, f, indent=2)

    print(f"\nSaved cleaned + reconciled tables and quality_report.json to: {OUT_DIR}")


if __name__ == "__main__":
    main()
