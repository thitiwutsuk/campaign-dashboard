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

LINE_GREEN = "#06C755"
LINE_GREY = "#C4C4C4"
CHART_FONT = "Prompt, sans-serif"
GREEN_RAMP = ["#06C755", "#00893D", "#7ED9A8", "#003A1F", "#B6EFCB", "#00B14F"]

st.set_page_config(page_title="Campaign Dashboard", layout="wide")
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = GREEN_RAMP


def style_fig(fig):
    fig.update_layout(template="plotly_white", font_family=CHART_FONT)
    return fig


def compact_thb(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"฿{value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"฿{value / 1_000:,.0f}K"
    return f"฿{value:,.0f}"


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
campaign_selection = st.sidebar.multiselect(
    "Campaigns", campaign_options, default=[],
    help="Leave empty to include all campaigns — with 40+ campaigns, pre-selecting all as pills isn't readable.",
)
selected_campaigns = campaign_selection if campaign_selection else campaign_options

mask = (
    (unified_sales["transaction_datetime"].dt.date >= start_date)
    & (unified_sales["transaction_datetime"].dt.date <= end_date)
)
sales = unified_sales[mask].copy()
sales_no_returns = sales[~sales["is_return"]]

# --- Key Insights -------------------------------------------------------------
if not sales_no_returns.empty and not campaign_summary.empty:
    best_campaign = campaign_summary.loc[campaign_summary["roas"].idxmax()]
    worst_campaign = campaign_summary.loc[campaign_summary["roas"].idxmin()]

    dow_revenue = (
        sales_no_returns.assign(day_of_week=sales_no_returns["transaction_datetime"].dt.day_name())
        .groupby("day_of_week")["net_amount_thb"].mean()
    )
    best_day = dow_revenue.idxmax()

    payment_revenue = sales_no_returns.groupby("payment_method")["net_amount_thb"].sum().sort_values(ascending=False)
    top_payment = payment_revenue.index[0]
    top_payment_share = payment_revenue.iloc[0] / payment_revenue.sum() * 100

    unattributed_share = sales["campaign_id"].isna().mean() * 100

    st.markdown(
        f"""
        <div style="background:{LINE_GREEN}15; border-left:4px solid {LINE_GREEN}; border-radius:6px;
                    padding:1rem 1.25rem; margin-bottom:1.5rem; font-family:{CHART_FONT};">
            <div style="font-weight:700; font-size:1.05rem; margin-bottom:0.4rem;">Key Insights</div>
            <ul style="margin:0; padding-left:1.2rem; line-height:1.8; font-size:0.92rem;">
                <li><b>Best campaign:</b> {best_campaign["campaign_id"]} at {best_campaign["roas"]:.1f}x ROAS</li>
                <li><b>Weakest campaign:</b> {worst_campaign["campaign_id"]} at {worst_campaign["roas"]:.1f}x ROAS</li>
                <li><b>Best day to sell:</b> {best_day}, averaging {compact_thb(dow_revenue.max())} in daily revenue</li>
                <li><b>Preferred payment method:</b> {top_payment}, driving {top_payment_share:.0f}% of revenue</li>
                <li><b>Attribution gap:</b> {unattributed_share:.0f}% of transactions in range carry no campaign code at all</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
    fig = px.line(
        daily, x="date", y="net_amount_thb", labels={"net_amount_thb": "Revenue (THB)", "date": "Date"},
        color_discrete_sequence=[LINE_GREEN],
    )
    st.plotly_chart(style_fig(fig), width="stretch")

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
        color_discrete_map={"Attributed": LINE_GREEN, "Not attributed": LINE_GREY},
    )
    st.plotly_chart(style_fig(fig2), width="stretch")

    col_dow, col_month = st.columns(2)
    with col_dow:
        st.subheader("Revenue by day of week")
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        by_dow = (
            sales_no_returns.assign(day_of_week=sales_no_returns["transaction_datetime"].dt.day_name())
            .groupby("day_of_week", as_index=False)["net_amount_thb"].sum()
        )
        by_dow["day_of_week"] = pd.Categorical(by_dow["day_of_week"], categories=dow_order, ordered=True)
        by_dow = by_dow.sort_values("day_of_week")
        fig_dow = px.bar(
            by_dow, x="day_of_week", y="net_amount_thb",
            labels={"net_amount_thb": "Revenue (THB)", "day_of_week": ""},
            color_discrete_sequence=[LINE_GREEN],
        )
        st.plotly_chart(style_fig(fig_dow), width="stretch")
    with col_month:
        st.subheader("Revenue by month")
        by_month = (
            sales_no_returns.assign(month=sales_no_returns["transaction_datetime"].dt.to_period("M").astype(str))
            .groupby("month", as_index=False)["net_amount_thb"].sum()
        )
        fig_month = px.bar(
            by_month, x="month", y="net_amount_thb",
            labels={"net_amount_thb": "Revenue (THB)", "month": ""},
            color_discrete_sequence=[LINE_GREEN],
        )
        st.plotly_chart(style_fig(fig_month), width="stretch")

# --- Campaign ROI -----------------------------------------------------------
with tab_roi:
    st.subheader("Ad-reported conversions vs. real orders")
    ad_filtered = ad_clean[
        (ad_clean["report_date"].dt.date >= start_date)
        & (ad_clean["report_date"].dt.date <= end_date)
        & (ad_clean["campaign_id"].isin(selected_campaigns))
    ]
    attributed_sales = sales_no_returns[sales_no_returns["campaign_id"].isin(selected_campaigns)]

    compare_labels = ["Conversions (ad-reported)", "Orders (POS-attributed)"]
    compare_values = [
        int(ad_filtered["conversions_reported"].sum()),
        int(attributed_sales["transaction_id"].nunique()),
    ]
    match_pct = (compare_values[1] / compare_values[0] * 100) if compare_values[0] else float("nan")
    funnel_revenue = attributed_sales["net_amount_thb"].sum()

    col_chart, col_stat = st.columns([3, 1])
    with col_chart:
        fig_compare = px.bar(
            x=compare_labels, y=compare_values, labels={"x": "", "y": "Count"},
            color=compare_labels,
            color_discrete_map={compare_labels[0]: LINE_GREY, compare_labels[1]: LINE_GREEN},
        )
        fig_compare.update_layout(showlegend=False)
        st.plotly_chart(style_fig(fig_compare), width="stretch")
    with col_stat:
        st.markdown(
            f"""
            <div style="text-align:center; padding-top:3rem;">
                <div style="font-family:{CHART_FONT}; font-size:3rem; font-weight:700;
                            color:{LINE_GREEN};">{match_pct:.0f}%</div>
                <div style="font-family:{CHART_FONT}; font-size:0.9rem; color:#666;">
                    of ad-reported conversions<br>match a real POS order</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(
        f"Those {compare_values[1]:,} POS-attributed orders generated ฿{funnel_revenue:,.0f} in "
        "revenue. The gap shows the ad platform's own pixel-tracked conversions are noisy and "
        "don't reconcile 1:1 with real sales."
    )

    st.subheader("ROAS by campaign")
    fig3 = px.bar(
        campaign_summary.sort_values("roas"), x="roas", y="campaign_id", orientation="h",
        labels={"roas": "ROAS (revenue / spend)", "campaign_id": ""},
        color_discrete_sequence=[LINE_GREEN],
    )
    st.plotly_chart(style_fig(fig3), width="stretch")

    st.subheader("Spend vs. attributed revenue")
    spend_vs_rev = campaign_summary.melt(
        id_vars="campaign_id", value_vars=["ad_spend_thb", "attributed_revenue_thb"],
        var_name="metric", value_name="thb",
    )
    fig4 = px.bar(
        spend_vs_rev, x="campaign_id", y="thb", color="metric", barmode="group",
        labels={"thb": "THB", "campaign_id": "", "metric": ""},
        color_discrete_map={"ad_spend_thb": LINE_GREY, "attributed_revenue_thb": LINE_GREEN},
    )
    st.plotly_chart(style_fig(fig4), width="stretch")

# --- Customer Segments -------------------------------------------------------
with tab_segments:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Revenue by customer segment")
        by_segment = sales_no_returns.dropna(subset=["customer_segment"]).groupby(
            "customer_segment", as_index=False
        )["net_amount_thb"].sum()
        fig5 = px.pie(
            by_segment, names="customer_segment", values="net_amount_thb",
            color_discrete_sequence=GREEN_RAMP,
        )
        st.plotly_chart(style_fig(fig5), width="stretch")
    with col2:
        st.subheader("Revenue by region")
        by_region = sales_no_returns.dropna(subset=["region"]).groupby(
            "region", as_index=False
        )["net_amount_thb"].sum().sort_values("net_amount_thb", ascending=False)
        fig6 = px.bar(
            by_region, x="region", y="net_amount_thb", labels={"net_amount_thb": "Revenue (THB)"},
            color_discrete_sequence=[LINE_GREEN],
        )
        st.plotly_chart(style_fig(fig6), width="stretch")

    st.caption(
        "Segment/region are only known for transactions linked to a CRM customer — walk-in sales "
        "and orphan customer_ref rows are excluded from these two charts."
    )

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Revenue by payment method")
        by_payment = sales_no_returns.dropna(subset=["payment_method"]).groupby(
            "payment_method", as_index=False
        )["net_amount_thb"].sum()
        fig_payment = px.pie(
            by_payment, names="payment_method", values="net_amount_thb",
            color_discrete_sequence=GREEN_RAMP,
        )
        st.plotly_chart(style_fig(fig_payment), width="stretch")
    with col4:
        st.subheader("Payment mix by customer segment")
        seg_payment = (
            sales_no_returns.dropna(subset=["customer_segment", "payment_method"])
            .groupby(["customer_segment", "payment_method"], as_index=False)["net_amount_thb"].sum()
        )
        seg_payment["pct_of_segment"] = (
            seg_payment["net_amount_thb"] / seg_payment.groupby("customer_segment")["net_amount_thb"].transform("sum") * 100
        )
        fig_seg_pay = px.bar(
            seg_payment, x="customer_segment", y="pct_of_segment", color="payment_method", barmode="stack",
            labels={"pct_of_segment": "% of segment revenue", "customer_segment": "", "payment_method": ""},
            color_discrete_sequence=GREEN_RAMP,
        )
        st.plotly_chart(style_fig(fig_seg_pay), width="stretch")

    st.caption(
        "Payment mix is normalized to % of each segment's own revenue, so the comparison shows "
        "preference patterns rather than which segment simply spends more."
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
