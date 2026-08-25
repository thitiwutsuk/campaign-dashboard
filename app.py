"""
Step 6: Streamlit dashboard.

Reads the tables scripts/run_pipeline.py already cleaned and reconciled into
data/processed/ — this app does no cleaning itself, it only visualizes.
Run: streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent / "data" / "processed"

st.set_page_config(page_title="Campaign Dashboard", layout="wide")


@st.cache_data
def load_data():
    unified_sales = pd.read_csv(DATA_DIR / "unified_sales.csv", parse_dates=["transaction_datetime"])
    campaign_summary = pd.read_csv(DATA_DIR / "campaign_summary.csv")
    ad_clean = pd.read_csv(DATA_DIR / "ad_platform_report_clean.csv", parse_dates=["report_date"])
    crm_clean = pd.read_csv(DATA_DIR / "crm_customers_clean.csv")
    with open(DATA_DIR / "quality_report.json") as f:
        quality_report = json.load(f)
    return unified_sales, campaign_summary, ad_clean, crm_clean, quality_report


try:
    unified_sales, campaign_summary, ad_clean, crm_clean, quality_report = load_data()
except FileNotFoundError:
    st.error(
        "No processed data found. Run `python3 scripts/run_pipeline.py` first to "
        "generate data/processed/, then reload this page."
    )
    st.stop()

st.title("Campaign Dashboard")
st.caption("Retail sales reconciled against ad campaign spend — synthetic CRM, POS, and ad platform data.")

# --- sidebar filters --------------------------------------------------------
min_date = unified_sales["transaction_datetime"].min().date()
max_date = unified_sales["transaction_datetime"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

campaign_options = sorted(unified_sales["campaign_id"].dropna().unique())
selected_campaigns = st.sidebar.multiselect("Campaigns", campaign_options, default=campaign_options)

mask = (
    (unified_sales["transaction_datetime"].dt.date >= start_date)
    & (unified_sales["transaction_datetime"].dt.date <= end_date)
)
sales = unified_sales[mask].copy()
sales_in_campaigns = sales[sales["campaign_id"].isin(selected_campaigns) | sales["campaign_id"].isna()]
sales_no_returns = sales[~sales["is_return"]]

tab_overview, tab_trend, tab_roi, tab_segments, tab_quality = st.tabs(
    ["Overview", "Sales Trend", "Campaign ROI", "Customer Segments", "Data Quality"]
)

# --- Overview ----------------------------------------------------------------
with tab_overview:
    total_revenue = sales_no_returns["net_amount_thb"].sum()
    attributed_revenue = campaign_summary["attributed_revenue_thb"].sum()
    total_ad_spend = campaign_summary["ad_spend_thb"].sum()
    total_orders = sales["transaction_id"].nunique()
    total_customers = crm_clean["cust_id"].nunique()
    overall_roas = attributed_revenue / total_ad_spend if total_ad_spend else float("nan")

    def compact_thb(value: float) -> str:
        if abs(value) >= 1_000_000:
            return f"฿{value / 1_000_000:,.1f}M"
        if abs(value) >= 1_000:
            return f"฿{value / 1_000:,.0f}K"
        return f"฿{value:,.0f}"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Sales Revenue", compact_thb(total_revenue))
    c2.metric("Ad Spend", compact_thb(total_ad_spend))
    c3.metric("Attributed Revenue", compact_thb(attributed_revenue))
    c4.metric("Overall ROAS", f"{overall_roas:.1f}x")
    c5.metric("Total Orders", f"{total_orders:,}")

    st.caption(
        "Total Sales Revenue covers all POS transactions in range; Attributed Revenue is the "
        "subset linked to a campaign via `campaign_code` — the two are not the same denominator, "
        "most POS transactions carry no campaign attribution (see Data Quality tab)."
    )

    st.subheader("Per-campaign summary")
    st.dataframe(
        campaign_summary[
            ["campaign_id", "ad_spend_thb", "attributed_revenue_thb", "attributed_orders", "roas", "roi_pct"]
        ].style.format(
            {"ad_spend_thb": "฿{:,.0f}", "attributed_revenue_thb": "฿{:,.0f}", "roas": "{:.1f}x", "roi_pct": "{:.0f}%"}
        ),
        width="stretch",
        hide_index=True,
    )

# --- Sales Trend ---------------------------------------------------------------
with tab_trend:
    st.subheader("Daily sales revenue")
    daily = (
        sales_no_returns.assign(date=sales_no_returns["transaction_datetime"].dt.date)
        .groupby("date", as_index=False)["net_amount_thb"]
        .sum()
    )
    fig = px.line(daily, x="date", y="net_amount_thb", labels={"net_amount_thb": "Revenue (THB)", "date": "Date"})
    st.plotly_chart(fig, width="stretch")

    st.subheader("Daily revenue: attributed vs. non-attributed")
    daily_attr = (
        sales_no_returns.assign(
            date=sales_no_returns["transaction_datetime"].dt.date,
            attributed=sales_no_returns["campaign_id"].notna().map({True: "Attributed", False: "Not attributed"}),
        )
        .groupby(["date", "attributed"], as_index=False)["net_amount_thb"]
        .sum()
    )
    fig2 = px.area(
        daily_attr, x="date", y="net_amount_thb", color="attributed",
        labels={"net_amount_thb": "Revenue (THB)", "date": "Date", "attributed": ""},
    )
    st.plotly_chart(fig2, width="stretch")

# --- Campaign ROI -----------------------------------------------------------
with tab_roi:
    st.subheader("ROAS by campaign")
    fig3 = px.bar(
        campaign_summary.sort_values("roas"), x="roas", y="campaign_id", orientation="h",
        labels={"roas": "ROAS (revenue / spend)", "campaign_id": ""},
    )
    st.plotly_chart(fig3, width="stretch")

    st.subheader("Spend vs. attributed revenue")
    spend_vs_rev = campaign_summary.melt(
        id_vars="campaign_id", value_vars=["ad_spend_thb", "attributed_revenue_thb"],
        var_name="metric", value_name="thb",
    )
    fig4 = px.bar(spend_vs_rev, x="campaign_id", y="thb", color="metric", barmode="group",
                  labels={"thb": "THB", "campaign_id": "", "metric": ""})
    st.plotly_chart(fig4, width="stretch")

# --- Customer Segments -------------------------------------------------------
with tab_segments:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Revenue by customer segment")
        by_segment = sales_no_returns.dropna(subset=["customer_segment"]).groupby(
            "customer_segment", as_index=False
        )["net_amount_thb"].sum()
        fig5 = px.pie(by_segment, names="customer_segment", values="net_amount_thb")
        st.plotly_chart(fig5, width="stretch")
    with col2:
        st.subheader("Revenue by region")
        by_region = sales_no_returns.dropna(subset=["region"]).groupby(
            "region", as_index=False
        )["net_amount_thb"].sum().sort_values("net_amount_thb", ascending=False)
        fig6 = px.bar(by_region, x="region", y="net_amount_thb", labels={"net_amount_thb": "Revenue (THB)"})
        st.plotly_chart(fig6, width="stretch")

    st.caption(
        "Segment/region are only known for transactions linked to a CRM customer — walk-in sales "
        "and orphan customer_ref rows are excluded from these two charts."
    )

# --- Data Quality -------------------------------------------------------------
with tab_quality:
    st.subheader("What was cleaned, and why")
    st.write(
        "Every number below comes from `src/cleaning.py` / `src/reconcile.py` at pipeline run time "
        "(`data/processed/quality_report.json`) — nothing here is hand-typed."
    )
    labels = {
        "crm_customers": "crm_customers.csv",
        "pos_transactions": "pos_transactions.csv",
        "ad_platform_report": "ad_platform_report.csv",
        "reconciliation": "Reconciliation / join layer",
    }
    for key, label in labels.items():
        with st.expander(label, expanded=False):
            report_df = pd.DataFrame(
                quality_report[key].items(), columns=["Check", "Count"]
            )
            st.dataframe(report_df, width="stretch", hide_index=True)
