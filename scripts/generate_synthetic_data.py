"""
Generate 3 messy, mismatched-schema CSVs simulating a retail business with:
- CRM system (customer master data)
- POS/Sales system (transaction line items)
- Ad Platform export (daily campaign performance)

The datasets are intentionally inconsistent (naming, date formats, key formats,
granularity, duplicates, missing values) to practice data consolidation,
cleansing, and reconciliation - mirroring a data intelligence analyst's daily work.

Run: python generate_synthetic_data.py
Output: ../data/raw/crm_customers.csv, pos_transactions.csv, ad_platform_report.csv
"""

import random
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared config: campaigns, date range
# ---------------------------------------------------------------------------

START_DATE = datetime(2024, 6, 1)
N_DAYS = 90
DATES = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]

# base_daily_budget is calibrated so per-campaign ROAS lands in a believable
# ~2x-7x range against this dataset's POS revenue scale (real campaigns rarely
# sustain double-digit ROAS) - see README Step 4 findings for the actual numbers.
CAMPAIGNS = [
    {
        "campaign_id": "SUMMER_PROMO_2024_TH",
        "short_code": "SP24",
        "platforms": ["LINE", "Facebook"],
        "active_days": (5, 35),      # (start_day_idx, end_day_idx)
        "base_daily_budget": 75000,
    },
    {
        "campaign_id": "BACK_TO_SCHOOL_2024",
        "short_code": "BTS24",
        "platforms": ["LINE", "Google"],
        "active_days": (30, 60),
        "base_daily_budget": 60000,
    },
    {
        "campaign_id": "FLASH_SALE_JULY_2024",
        "short_code": "FSJ24",
        "platforms": ["LINE"],
        "active_days": (20, 27),
        "base_daily_budget": 125000,
    },
    {
        "campaign_id": "NEW_USER_ACQUISITION_Q3",
        "short_code": "NUA24",
        "platforms": ["Facebook", "Google"],
        "active_days": (0, 90),
        "base_daily_budget": 40000,
    },
    {
        "campaign_id": "MEMBER_EXCLUSIVE_AUG_2024",
        "short_code": "MEA24",
        "platforms": ["LINE", "Facebook", "Google"],
        "active_days": (60, 85),
        "base_daily_budget": 90000,
    },
]

REGION_VARIANTS = {
    "Bangkok": ["Bangkok", "กรุงเทพ", "BKK", "bangkok"],
    "Chiang Mai": ["Chiang Mai", "เชียงใหม่", "CNX"],
    "Chonburi": ["Chonburi", "ชลบุรี", "Pattaya"],
    "Khon Kaen": ["Khon Kaen", "ขอนแก่น"],
    "Phuket": ["Phuket", "ภูเก็ต", "HKT"],
}

STORE_BRANCH_VARIANTS = {
    "Siam": ["Siam", "SIAM branch", "สยาม"],
    "Central World": ["Central World", "CTW", "เซ็นทรัลเวิลด์"],
    "Online": ["Online", "ONLINE", "Web"],
    "EmQuartier": ["EmQuartier", "EM", "เอ็มควอเทียร์"],
    "Icon Siam": ["Icon Siam", "ICONSIAM", "ไอคอนสยาม"],
}

PRODUCT_CATEGORIES = ["Electronics", "Fashion", "Beauty", "Home & Living", "Sports"]
FIRST_NAMES = ["Somchai", "Suda", "Anan", "Pim", "Kittipong", "Nattaya", "Chai", "Waree",
               "Preecha", "Malee", "Thanapon", "Siriporn", "Wichai", "Ratana", "Somsak"]
LAST_NAMES = ["Sukjai", "Chaiyaporn", "Thongdee", "Rattanakul", "Wongsawat", "Charoensuk",
              "Phanuwat", "Kaewmanee", "Suksawat", "Boonmee"]


def random_phone(clean: bool = True) -> str:
    digits = "08" + "".join(random.choices(string.digits, k=8))
    fmt = random.choice(["plain", "dashed", "intl"]) if not clean else "plain"
    if fmt == "dashed":
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if fmt == "intl":
        return "+66" + digits[1:]
    return digits


def random_signup_date() -> str:
    """Mixed date formats across records, as if CRM went through 2 migrations."""
    d = START_DATE - timedelta(days=random.randint(0, 900))
    fmt = random.choices(
        ["%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%m/%d/%Y"],
        weights=[45, 30, 15, 10],
    )[0]
    return d.strftime(fmt)


SEGMENT_VARIANTS = {
    "VIP": ["VIP", "vip", " VIP ", "Vip"],
    "Regular": ["Regular", "regular", "REGULAR", " Regular"],
    "New": ["New", "new", "NEW"],
}
# some legacy records store segment as a numeric code instead of text
SEGMENT_CODE_MAP = {"1": "VIP", "2": "Regular", "3": "New"}


def random_segment():
    r = random.random()
    if r < 0.08:
        return None
    if r < 0.13:
        return "N/A"
    if r < 0.20:
        return random.choice(list(SEGMENT_CODE_MAP.keys()))  # legacy numeric code
    canonical = random.choices(["VIP", "Regular", "New"], weights=[12, 58, 30])[0]
    return random.choice(SEGMENT_VARIANTS[canonical])


def random_email(first, last, i) -> str:
    base = f"{first.lower()}.{last.lower()}{i}@example.com"
    r = random.random()
    if r < 0.03:
        return base.replace("@", " at ")          # malformed, no @
    if r < 0.06:
        return base.upper()                        # inconsistent casing
    if r < 0.09:
        return " " + base + "  "                   # stray whitespace
    if r < 0.11:
        return ""                                   # missing email
    return base


# ---------------------------------------------------------------------------
# 1. CRM customers
# ---------------------------------------------------------------------------

def generate_crm_customers(n=800):
    rows = []
    for i in range(1, n + 1):
        cust_id = f"C-{i:05d}"
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        canonical_region = random.choice(list(REGION_VARIANTS.keys()))
        region = random.choice(REGION_VARIANTS[canonical_region])
        # extra whitespace/casing noise on top of the name variants themselves
        if random.random() < 0.05:
            region = region.upper()
        if random.random() < 0.05:
            region = f" {region} "

        total_orders = random.randint(0, 40)
        if random.random() < 0.08:
            total_orders = None  # sync failure
        elif random.random() < 0.02:
            total_orders = -total_orders  # data entry error, should never be negative

        # migration artifact: legacy vs. new CRM system wrote the record
        source_system = random.choices(
            ["CRM_V2", "CRM_LEGACY", "CRM_LEGACY_MIGRATED"], weights=[70, 20, 10]
        )[0]

        rows.append({
            "cust_id": cust_id,
            "full_name": f"{first} {last}",
            "email": random_email(first, last, i),
            "phone": random_phone(clean=False),
            "signup_date": random_signup_date(),
            "customer_segment": random_segment(),
            "region": region,
            "total_lifetime_orders": total_orders,
            "source_system": source_system,
        })

    df = pd.DataFrame(rows)

    # Inject ~2% duplicate cust_id (merge error: different name/data, same id)
    n_dupes = int(n * 0.02)
    dupe_rows = df.sample(n=n_dupes, random_state=1).copy()
    dupe_rows["full_name"] = [f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}" for _ in range(n_dupes)]
    dupe_rows["email"] = dupe_rows["email"].apply(lambda e: "dup_" + e if e else e)
    df = pd.concat([df, dupe_rows], ignore_index=True)

    # Inject ~1% exact full-duplicate rows (accidental re-export from source system)
    n_exact_dupes = int(n * 0.01)
    exact_dupes = df.sample(n=n_exact_dupes, random_state=5).copy()
    df = pd.concat([df, exact_dupes], ignore_index=True)

    df = df.sample(frac=1, random_state=2).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# 2. POS transactions (business logic: sales lift near active campaigns)
# ---------------------------------------------------------------------------

PAYMENT_METHOD_VARIANTS = {
    "Credit Card": ["Credit Card", "credit card", "CC", "Credit card"],
    "PromptPay": ["PromptPay", "QR/PromptPay", "promptpay", "QR"],
    "Cash": ["Cash", "cash", "CASH"],
    "LINE Pay": ["LINE Pay", "LINEPAY", "line pay"],
}


def random_sku(base_id: int) -> str:
    """Same SKU, 3 different formats depending on which POS terminal exported it."""
    fmt = random.choices(["dash", "underscore", "plain"], weights=[60, 25, 15])[0]
    if fmt == "underscore":
        return f"SKU_{base_id}"
    if fmt == "plain":
        return str(base_id)
    return f"SKU-{base_id}"


def random_campaign_code_str(code: str) -> str:
    """Same campaign short code, inconsistent casing/whitespace across POS terminals."""
    r = random.random()
    if r < 0.25:
        return code.lower()
    if r < 0.35:
        return f" {code} "
    return code


def generate_pos_transactions(crm_df, n_base=5000):
    valid_cust_numeric_ids = crm_df["cust_id"].str.replace("C-", "", regex=False).str.lstrip("0")
    valid_cust_numeric_ids = valid_cust_numeric_ids.replace("", "0").tolist()
    max_valid_id = crm_df["cust_id"].str.replace("C-", "", regex=False).astype(int).max()

    rows = []
    # ground truth for the ad-platform generator: real attributed orders per
    # (campaign short_code, day_idx), counted before the duplicate-row
    # injection below (matching what the cleaning pipeline dedupes down to)
    attributed_order_counts = {}
    for day_idx, date in enumerate(DATES):
        # base transaction volume per day
        daily_txn_count = np.random.poisson(lam=n_base / N_DAYS)

        # find campaigns active today -> lift multiplier + eligible short codes
        active_campaigns = [
            c for c in CAMPAIGNS if c["active_days"][0] <= day_idx < c["active_days"][1]
        ]
        lift = 1.0 + 0.6 * len(active_campaigns)  # more active campaigns -> more sales
        n_today = int(daily_txn_count * lift)

        for _ in range(n_today):
            hour = random.randint(9, 22)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            dt = date.replace(hour=hour, minute=minute, second=second)

            # walk-in (no customer ref) ~15% of the time
            if random.random() < 0.15:
                customer_ref = None
            elif random.random() < 0.03:
                # orphan reference: id that doesn't exist in CRM (bad sync)
                customer_ref = str(max_valid_id + random.randint(1, 500))
            else:
                customer_ref = random.choice(valid_cust_numeric_ids)

            canonical_branch = random.choice(list(STORE_BRANCH_VARIANTS.keys()))
            branch = random.choice(STORE_BRANCH_VARIANTS[canonical_branch])
            if random.random() < 0.02:
                branch = None  # missing channel on some legacy terminal exports

            # ~40% of transactions during an active campaign carry its short code
            campaign_code = None
            if active_campaigns and random.random() < 0.4:
                raw_code = random.choice(active_campaigns)["short_code"]
                campaign_code = random_campaign_code_str(raw_code)
                key = (raw_code, day_idx)
                attributed_order_counts[key] = attributed_order_counts.get(key, 0) + 1

            # returns: small share of rows have negative qty
            qty = random.randint(1, 5)
            if random.random() < 0.02:
                qty = -qty

            unit_price = round(random.uniform(150, 5000), 2)
            price_str = f"{unit_price:,.2f}" if random.random() < 0.5 else f"{unit_price:.2f}"

            # currency mislabeling bug: ~2% of rows say USD but the number is still THB-scale
            currency = "USD" if random.random() < 0.02 else "THB"

            discount_pct = round(random.choice([0, 0, 0, 5, 10, 15, 20]), 1)
            if random.random() < 0.01:
                discount_pct = round(random.uniform(-10, 150), 1)  # bad data entry

            payment_canonical = random.choices(
                list(PAYMENT_METHOD_VARIANTS.keys()), weights=[35, 30, 20, 15]
            )[0]
            payment_method = random.choice(PAYMENT_METHOD_VARIANTS[payment_canonical])

            # datetime format drift: most terminals export text, a few export unix epoch seconds
            if random.random() < 0.05:
                transaction_datetime = str(int(dt.timestamp()))
            else:
                transaction_datetime = dt.strftime("%Y-%m-%d %H:%M:%S")

            rows.append({
                "transaction_id": str(uuid.uuid4()),
                "customer_ref": customer_ref,
                "product_sku": random_sku(random.randint(1000, 1200)),
                "product_category": random.choice(PRODUCT_CATEGORIES),
                "qty": qty,
                "unit_price": price_str,
                "currency": currency,
                "discount_pct": discount_pct,
                "payment_method": payment_method,
                "transaction_datetime": transaction_datetime,
                "store_channel": branch,
                "campaign_code": campaign_code,
            })

    df = pd.DataFrame(rows)

    # Inject ~1% duplicate transaction_id rows (system retry)
    n_dupes = int(len(df) * 0.01)
    dupe_rows = df.sample(n=n_dupes, random_state=3).copy()
    df = pd.concat([df, dupe_rows], ignore_index=True).sample(frac=1, random_state=4).reset_index(drop=True)
    return df, attributed_order_counts


# ---------------------------------------------------------------------------
# 3. Ad platform daily report (spend drives impressions/clicks/conversions)
# ---------------------------------------------------------------------------

PLATFORM_CASING_VARIANTS = {
    "LINE": ["LINE", "Line", "line"],
    "Facebook": ["Facebook", "facebook", "FB"],
    "Google": ["Google", "google", "GOOGLE_ADS"],
}

# rough THB->USD for the ~3% of rows some regional sub-account exported in USD
USD_TO_THB = 36.5


def maybe_thousands_str(n: int) -> str:
    """~20% of the time the export renders integers with thousands separators."""
    if random.random() < 0.2:
        return f"{n:,}"
    return str(n)


def generate_ad_platform_report(attributed_order_counts):
    rows = []
    for campaign in CAMPAIGNS:
        start_idx, end_idx = campaign["active_days"]
        for day_idx in range(start_idx, end_idx):
            date = DATES[day_idx]

            # ~5% of days fail to export (missing data)
            if random.random() < 0.05:
                continue

            # real POS-attributed orders for this campaign/day, split evenly
            # across whichever platforms ran that day - the ground truth that
            # conversions_reported below over-counts relative to
            real_orders_today = attributed_order_counts.get((campaign["short_code"], day_idx), 0)
            real_orders_per_platform = real_orders_today / len(campaign["platforms"])

            for platform in campaign["platforms"]:
                platform_str = random.choice(PLATFORM_CASING_VARIANTS[platform])

                budget_noise = np.random.normal(1.0, 0.15)
                spend = max(500, campaign["base_daily_budget"] * budget_noise / len(campaign["platforms"]))
                impressions = int(spend * random.uniform(15, 25))
                clicks = int(impressions * random.uniform(0.01, 0.04))
                ctr = round((clicks / impressions) * 100, 2) if impressions else 0.0
                # pixel-tracked conversions - noisy vs. real POS sales, but
                # grounded in the real order count (platforms typically
                # over-count conversions by 1.3x-2x vs. server-side truth)
                overcount_factor = random.uniform(1.3, 2.0)
                conversions_reported = int(round(real_orders_per_platform * overcount_factor))

                # currency bug: a few rows report spend in USD without converting
                currency = "USD" if random.random() < 0.03 else "THB"
                spend_value = spend / USD_TO_THB if currency == "USD" else spend

                utm_source = random.choice([None, None, None, "newsletter", "affiliate"])
                notes = random.choice([None, None, None, None, "manual adjustment", "backfilled"])

                rows.append({
                    "campaign_id": campaign["campaign_id"],
                    "report_date": date.strftime("%m/%d/%Y"),
                    "impressions": maybe_thousands_str(impressions),
                    "clicks": maybe_thousands_str(clicks),
                    "ctr": f"{ctr}%",
                    "spend_thb": round(spend_value, 2),
                    "currency": currency,
                    "conversions_reported": conversions_reported,
                    "platform": platform_str,
                    "utm_source": utm_source,
                    "notes": notes,
                })

                # ~1.5% chance the same campaign/date/platform gets double-exported
                # (overlapping manual + scheduled export)
                if random.random() < 0.015:
                    dup = rows[-1].copy()
                    dup["impressions"] = maybe_thousands_str(int(impressions * random.uniform(0.95, 1.05)))
                    rows.append(dup)

                # ~1% chance of a tracking anomaly: impressions collapse to 0 but clicks persist
                if random.random() < 0.01:
                    rows.append({
                        "campaign_id": campaign["campaign_id"],
                        "report_date": date.strftime("%m/%d/%Y"),
                        "impressions": "0",
                        "clicks": maybe_thousands_str(random.randint(5, 50)),
                        "ctr": "N/A",
                        "spend_thb": round(spend_value * random.uniform(0.1, 0.3), 2),
                        "currency": currency,
                        "conversions_reported": 0,
                        "platform": platform_str,
                        "utm_source": None,
                        "notes": "tracking anomaly",
                    })

                # ~0.5% chance of a refund/adjustment row with negative spend
                if random.random() < 0.005:
                    rows.append({
                        "campaign_id": campaign["campaign_id"],
                        "report_date": date.strftime("%m/%d/%Y"),
                        "impressions": "0",
                        "clicks": "0",
                        "ctr": "0%",
                        "spend_thb": round(-spend_value * random.uniform(0.05, 0.2), 2),
                        "currency": currency,
                        "conversions_reported": 0,
                        "platform": platform_str,
                        "utm_source": None,
                        "notes": "billing adjustment",
                    })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    crm_df = generate_crm_customers(n=800)
    pos_df, attributed_order_counts = generate_pos_transactions(crm_df, n_base=5000)
    ad_df = generate_ad_platform_report(attributed_order_counts)

    crm_df.to_csv(OUT_DIR / "crm_customers.csv", index=False)
    pos_df.to_csv(OUT_DIR / "pos_transactions.csv", index=False)
    ad_df.to_csv(OUT_DIR / "ad_platform_report.csv", index=False)

    print(f"crm_customers.csv      -> {len(crm_df):,} rows")
    print(f"pos_transactions.csv   -> {len(pos_df):,} rows")
    print(f"ad_platform_report.csv -> {len(ad_df):,} rows")
    print(f"Saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
