"""
Step 4: reconciliation / join layer.

Joins cleaned POS transactions to CRM customers (`customer_ref` -> `cust_id`)
and to ad platform spend (`campaign_code` -> `campaign_id`), then rolls the
result up into a per-campaign ROI table — the core business question this
dataset is built to answer.

CAMPAIGN_CODE_MAP is a small reference table (short code -> full campaign id)
that a real analyst would get from the marketing team, since it isn't stored
in either raw export — POS only carries the short code, the ad platform
report only carries the full id.
"""

import numpy as np
import pandas as pd

CAMPAIGN_CODE_MAP = {
    "SP24": "SUMMER_PROMO_2024_TH",
    "BTS24": "BACK_TO_SCHOOL_2024",
    "FSJ24": "FLASH_SALE_JULY_2024",
    "NUA24": "NEW_USER_ACQUISITION_Q3",
    "MEA24": "MEMBER_EXCLUSIVE_AUG_2024",
}


def build_unified_sales(pos_clean: pd.DataFrame, crm_clean: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """POS transactions enriched with customer info and a resolved campaign_id."""
    report = {}

    df = pos_clean.merge(
        crm_clean[["cust_id", "customer_segment", "region", "source_system"]],
        left_on="customer_ref",
        right_on="cust_id",
        how="left",
    )
    has_ref = df["customer_ref"].notna()
    report["orphan_customer_ref_rows"] = int((has_ref & df["cust_id"].isna()).sum())
    df = df.drop(columns="cust_id")

    df["campaign_id"] = df["campaign_code"].map(CAMPAIGN_CODE_MAP)
    unmapped = df["campaign_code"].notna() & df["campaign_id"].isna()
    report["unmapped_campaign_code_rows"] = int(unmapped.sum())

    report["output_rows"] = len(df)
    return df, report


def build_campaign_summary(unified_sales: pd.DataFrame, ad_clean: pd.DataFrame) -> pd.DataFrame:
    """Per-campaign ad spend vs. attributed sales -> ROI."""
    spend = (
        ad_clean.groupby("campaign_id")
        .agg(
            ad_spend_thb=("spend_thb", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            conversions_reported=("conversions_reported", "sum"),
        )
        .reset_index()
    )

    attributed = unified_sales[unified_sales["campaign_id"].notna() & ~unified_sales["is_return"]]
    sales = (
        attributed.groupby("campaign_id")
        .agg(
            attributed_revenue_thb=("net_amount_thb", "sum"),
            attributed_orders=("transaction_id", "nunique"),
            attributed_customers=("customer_ref", "nunique"),
        )
        .reset_index()
    )

    summary = spend.merge(sales, on="campaign_id", how="outer")
    summary[["ad_spend_thb", "attributed_revenue_thb", "attributed_orders", "attributed_customers"]] = (
        summary[["ad_spend_thb", "attributed_revenue_thb", "attributed_orders", "attributed_customers"]]
        .fillna(0)
    )

    summary["roas"] = np.where(
        summary["ad_spend_thb"] > 0, summary["attributed_revenue_thb"] / summary["ad_spend_thb"], np.nan
    )
    summary["profit_thb"] = summary["attributed_revenue_thb"] - summary["ad_spend_thb"]
    summary["roi_pct"] = np.where(
        summary["ad_spend_thb"] > 0, summary["profit_thb"] / summary["ad_spend_thb"] * 100, np.nan
    )

    return summary.sort_values("roi_pct", ascending=False).reset_index(drop=True)
