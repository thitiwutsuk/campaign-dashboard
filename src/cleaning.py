"""
Step 3: per-source cleaning & normalization.

Each clean_* function takes the raw DataFrame (as loaded from data/raw/*.csv)
and returns (clean_df, report) where `report` is a dict of counters describing
what was fixed/dropped/flagged — this feeds the data-quality report page in
the dashboard (Step 6) and the README findings.

The normalization rules below are not guesses: they mirror the exact messiness
injected by scripts/generate_synthetic_data.py (variant spellings, date
formats, currency bugs), so every alias map here is grounded in the profiling
done in Step 2.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

USD_TO_THB = 36.5  # matches the rate used to generate the synthetic USD rows

REGION_ALIASES = {
    "bangkok": "Bangkok", "กรุงเทพ": "Bangkok", "bkk": "Bangkok",
    "chiang mai": "Chiang Mai", "เชียงใหม่": "Chiang Mai", "cnx": "Chiang Mai",
    "chonburi": "Chonburi", "ชลบุรี": "Chonburi", "pattaya": "Chonburi",
    "khon kaen": "Khon Kaen", "ขอนแก่น": "Khon Kaen",
    "phuket": "Phuket", "ภูเก็ต": "Phuket", "hkt": "Phuket",
}

SEGMENT_ALIASES = {
    "vip": "VIP", "1": "VIP",
    "regular": "Regular", "2": "Regular",
    "new": "New", "3": "New",
}

PAYMENT_ALIASES = {
    "credit card": "Credit Card", "cc": "Credit Card",
    "promptpay": "PromptPay", "qr/promptpay": "PromptPay", "qr": "PromptPay",
    "cash": "Cash",
    "line pay": "LINE Pay", "linepay": "LINE Pay",
}

BRANCH_ALIASES = {
    "siam": "Siam", "สยาม": "Siam",
    "central world": "Central World", "ctw": "Central World", "เซ็นทรัลเวิลด์": "Central World",
    "online": "Online", "web": "Online",
    "emquartier": "EmQuartier", "em": "EmQuartier", "เอ็มควอเทียร์": "EmQuartier",
    "icon siam": "Icon Siam", "iconsiam": "Icon Siam", "ไอคอนสยาม": "Icon Siam",
}

PLATFORM_ALIASES = {
    "line": "LINE",
    "facebook": "Facebook", "fb": "Facebook",
    "google": "Google", "google_ads": "Google",
}


def _normalize_categorical(series: pd.Series, aliases: dict) -> pd.Series:
    """Strip/casefold each value and map through an alias table; unmapped -> NaN."""
    key = series.astype(str).str.strip().str.lower()
    key = key.where(series.notna(), np.nan)
    return key.map(aliases)


def _parse_mixed_dates(series: pd.Series, formats: list[str]) -> pd.Series:
    """Try each format in order, keeping the first successful parse per row.

    Deliberately does not use pandas' `format="mixed"` inference: as of
    pandas 3.0 it can misparse unambiguous ISO dates (e.g. "2023-06-08" ->
    2023-08-06) when combined with `dayfirst=True`. Trying explicit formats
    in priority order (unambiguous ones first) avoids that entirely, and
    still resolves genuinely ambiguous "d/m/Y" vs "m/d/Y" values the same
    way dayfirst would: whichever format is tried first wins when both match.
    """
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in formats:
        unparsed = result.isna() & series.notna()
        parsed = pd.to_datetime(series[unparsed], format=fmt, errors="coerce")
        result.loc[parsed.index] = parsed
    return result


def _normalize_phone(value) -> float | str:
    if pd.isna(value):
        return np.nan
    s = str(value).strip()
    if s.startswith("+66"):
        s = "0" + s[3:]
    digits = re.sub(r"\D", "", s)
    return digits if len(digits) == 10 and digits.startswith("0") else np.nan


def clean_crm(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report = {"input_rows": len(df)}
    df = df.copy()

    # --- dedupe -------------------------------------------------------
    exact_dupes = df.duplicated().sum()
    df = df.drop_duplicates()
    report["exact_duplicate_rows_dropped"] = int(exact_dupes)

    # duplicate cust_id with conflicting data: keep the most complete row,
    # tie-break on first occurrence (stable sort preserves original order)
    completeness = df.notna().sum(axis=1)
    df = df.assign(_completeness=completeness)
    df = df.sort_values("_completeness", ascending=False, kind="stable")
    id_dupes = df.duplicated(subset="cust_id").sum()
    df = df.drop_duplicates(subset="cust_id", keep="first").drop(columns="_completeness")
    report["duplicate_cust_id_rows_dropped"] = int(id_dupes)

    # --- email ----------------------------------------------------------
    email = df["email"].astype(str).str.strip()
    email = email.where(df["email"].notna() & (email != ""), np.nan)
    email = email.str.lower()
    valid_email = email.str.contains("@", na=False)
    report["missing_or_invalid_email"] = int((~valid_email).sum())
    df["email"] = email.where(valid_email, np.nan)

    # --- phone ------------------------------------------------------------
    df["phone"] = df["phone"].apply(_normalize_phone)
    report["invalid_phone"] = int(df["phone"].isna().sum())

    # --- signup_date: 4 mixed formats -> single ISO date ------------------
    # order: unambiguous formats first, then "d/m/Y" before "m/d/Y" (matches
    # the raw data's actual weighting of 45% vs 10% for the two "/" formats)
    df["signup_date"] = _parse_mixed_dates(
        df["signup_date"], ["%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%m/%d/%Y"]
    )
    report["unparseable_signup_date"] = int(df["signup_date"].isna().sum())

    # --- customer_segment: 14 raw spellings incl. legacy numeric codes ----
    df["customer_segment"] = _normalize_categorical(df["customer_segment"], SEGMENT_ALIASES)
    report["missing_or_unmapped_segment"] = int(df["customer_segment"].isna().sum())

    # --- region: 34 raw spellings incl. Thai script ------------------------
    df["region"] = _normalize_categorical(df["region"], REGION_ALIASES)
    report["missing_or_unmapped_region"] = int(df["region"].isna().sum())

    # --- total_lifetime_orders: negatives are a data-entry error -----------
    negative_orders = (df["total_lifetime_orders"] < 0).sum()
    df["total_lifetime_orders"] = df["total_lifetime_orders"].abs()
    report["negative_orders_corrected"] = int(negative_orders)
    report["missing_orders"] = int(df["total_lifetime_orders"].isna().sum())
    df["total_lifetime_orders"] = df["total_lifetime_orders"].astype("Int64")

    report["output_rows"] = len(df)
    return df.reset_index(drop=True), report


def clean_pos(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report = {"input_rows": len(df)}
    df = df.copy()

    # --- dedupe: system-retry duplicate transaction_id --------------------
    id_dupes = df.duplicated(subset="transaction_id").sum()
    df = df.drop_duplicates(subset="transaction_id", keep="first")
    report["duplicate_transaction_id_rows_dropped"] = int(id_dupes)

    # --- unit_price: comma-formatted strings -> float ----------------------
    df["unit_price"] = (
        df["unit_price"].astype(str).str.replace(",", "", regex=False).astype(float)
    )

    # --- currency: USD rows -> THB, then drop the now-redundant column ----
    is_usd = df["currency"].str.upper() == "USD"
    report["usd_rows_converted"] = int(is_usd.sum())
    df.loc[is_usd, "unit_price"] = df.loc[is_usd, "unit_price"] * USD_TO_THB
    df["currency"] = "THB"

    # --- discount_pct: clip data-entry outliers to a valid [0, 100] range -
    bad_discount = ((df["discount_pct"] < 0) | (df["discount_pct"] > 100)).sum()
    df["discount_pct"] = df["discount_pct"].clip(lower=0, upper=100)
    report["discount_pct_out_of_range_clipped"] = int(bad_discount)

    # --- qty: returns (negative qty) are expected, just flag them ---------
    df["is_return"] = df["qty"] < 0
    report["return_rows"] = int(df["is_return"].sum())

    # --- payment_method: 14 raw spellings -> 4 canonical categories -------
    df["payment_method"] = _normalize_categorical(df["payment_method"], PAYMENT_ALIASES)
    report["unmapped_payment_method"] = int(df["payment_method"].isna().sum())

    # --- store_channel: branch name variants incl. Thai script -------------
    df["store_channel"] = _normalize_categorical(df["store_channel"], BRANCH_ALIASES)
    report["missing_or_unmapped_store_channel"] = int(df["store_channel"].isna().sum())

    # --- campaign_code: strip whitespace/casing noise ----------------------
    df["campaign_code"] = df["campaign_code"].astype(str).str.strip().str.upper()
    df["campaign_code"] = df["campaign_code"].replace({"NAN": np.nan})
    report["no_campaign_attribution"] = int(df["campaign_code"].isna().sum())

    # --- customer_ref: numeric id -> CRM cust_id format (C-00173) ---------
    def to_cust_id(x):
        if pd.isna(x):
            return np.nan
        return f"C-{int(x):05d}"

    df["customer_ref"] = df["customer_ref"].apply(to_cust_id)
    report["walk_in_no_customer_ref"] = int(df["customer_ref"].isna().sum())

    # --- transaction_datetime: text vs. unix-epoch-seconds export drift ---
    is_epoch = df["transaction_datetime"].astype(str).str.fullmatch(r"\d+")
    dt = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    dt.loc[is_epoch] = pd.to_datetime(
        df.loc[is_epoch, "transaction_datetime"].astype("int64"), unit="s"
    )
    dt.loc[~is_epoch] = pd.to_datetime(df.loc[~is_epoch, "transaction_datetime"], errors="coerce")
    df["transaction_datetime"] = dt
    report["unparseable_transaction_datetime"] = int(df["transaction_datetime"].isna().sum())

    df["net_amount_thb"] = (
        df["qty"] * df["unit_price"] * (1 - df["discount_pct"] / 100)
    ).round(2)

    report["output_rows"] = len(df)
    return df.reset_index(drop=True), report


def clean_ad(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report = {"input_rows": len(df)}
    df = df.copy()

    # --- impressions / clicks: comma-formatted strings -> int --------------
    for col in ("impressions", "clicks"):
        df[col] = df[col].astype(str).str.replace(",", "", regex=False).astype(int)

    # --- ctr: percent-string -> float; recompute where missing/inconsistent
    parsed_ctr = pd.to_numeric(
        df["ctr"].astype(str).str.replace("%", "", regex=False), errors="coerce"
    )
    report["ctr_missing_or_unparseable"] = int(parsed_ctr.isna().sum())
    recomputed = np.where(
        df["impressions"] > 0, (df["clicks"] / df["impressions"] * 100).round(2), np.nan
    )
    df["ctr"] = parsed_ctr.fillna(pd.Series(recomputed, index=df.index))

    # --- currency: USD rows -> THB -----------------------------------------
    is_usd = df["currency"].str.upper() == "USD"
    report["usd_rows_converted"] = int(is_usd.sum())
    df.loc[is_usd, "spend_thb"] = df.loc[is_usd, "spend_thb"] * USD_TO_THB
    df["currency"] = "THB"

    # --- report_date: single "%m/%d/%Y" format, still worth an explicit parse
    df["report_date"] = pd.to_datetime(df["report_date"], format="%m/%d/%Y", errors="coerce")
    report["unparseable_report_date"] = int(df["report_date"].isna().sum())

    # --- platform: 9 raw spellings -> 3 canonical platforms -----------------
    df["platform"] = _normalize_categorical(df["platform"], PLATFORM_ALIASES)
    report["unmapped_platform"] = int(df["platform"].isna().sum())

    # --- flag known event types instead of dropping (all expected) --------
    df["is_billing_adjustment"] = df["spend_thb"] < 0
    df["is_tracking_anomaly"] = (df["impressions"] == 0) & (df["clicks"] > 0)
    report["negative_spend_rows"] = int(df["is_billing_adjustment"].sum())
    report["tracking_anomaly_rows"] = int(df["is_tracking_anomaly"].sum())

    # --- duplicate daily export: same campaign/date/platform/notes reported
    # twice (accidental overlapping manual + scheduled export). Anomaly and
    # billing-adjustment rows carry their own distinct `notes` value, so they
    # never collide with a normal row's key here and are kept as-is.
    dupe_key = ["campaign_id", "report_date", "platform", "notes"]
    dupes = df.duplicated(subset=dupe_key).sum()
    df = df.drop_duplicates(subset=dupe_key, keep="first")
    report["duplicate_daily_export_rows_dropped"] = int(dupes)

    report["output_rows"] = len(df)
    return df.reset_index(drop=True), report
