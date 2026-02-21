from __future__ import annotations

import re
import pandas as pd
import numpy as np

# ------------------------
# Column inference + utilities
# ------------------------
def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).strip().lower()).strip()


def infer_mapping(df: pd.DataFrame) -> dict:
    """
    Best-effort inference based on column names + dtypes.

    mapping keys:
      date, revenue, cost, profit,
      country, region, city,
      product, category,
      channel, customer
    """
    cols = list(df.columns)
    norm = {c: normalize(c) for c in cols}

    def pick_by_keywords(keywords, must_be_numeric=False, must_be_datetime=False):
        candidates = []
        for c in cols:
            n = norm[c]
            score = 0
            for kw in keywords:
                if kw in n:
                    score += 1
            if score == 0:
                continue

            if must_be_numeric and not pd.api.types.is_numeric_dtype(df[c]):
                continue

            if must_be_datetime:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    pass
                else:
                    parsed = pd.to_datetime(df[c], errors="coerce")
                    if parsed.notna().mean() < 0.6:
                        continue

            candidates.append((score, c))

        candidates.sort(reverse=True, key=lambda x: x[0])
        return candidates[0][1] if candidates else None

    mapping = {}

    # Measures
    mapping["revenue"] = pick_by_keywords(
        ["revenue", "sales", "amount", "total", "net sales", "turnover", "gmv"],
        must_be_numeric=True
    )
    mapping["cost"] = pick_by_keywords(
        ["cost", "cogs", "expense", "purchase", "landed cost"],
        must_be_numeric=True
    )
    mapping["profit"] = pick_by_keywords(
        ["profit", "gross profit", "net profit"],
        must_be_numeric=True
    )

    # Dimensions
    mapping["date"] = pick_by_keywords(
        ["date", "order date", "invoice date", "transaction date", "created"],
        must_be_datetime=True
    )
    mapping["country"] = pick_by_keywords(["country"])
    mapping["region"] = pick_by_keywords(["region", "state", "province"])
    mapping["city"] = pick_by_keywords(["city"])
    mapping["product"] = pick_by_keywords(["product", "sku", "item", "asin"])
    mapping["category"] = pick_by_keywords(["category", "sub category", "subcategory", "department", "brand"])
    mapping["channel"] = pick_by_keywords(["channel", "store", "platform", "marketplace", "source"])
    mapping["customer"] = pick_by_keywords(["customer", "client", "account", "buyer", "customer id", "client id"])

    # drop Nones
    mapping = {k: v for k, v in mapping.items() if v in cols}
    return mapping


def add_profit_margin(df: pd.DataFrame, revenue_col: str, cost_col: str | None, profit_col: str | None) -> pd.DataFrame:
    out = df.copy()

    # If profit isn't provided but cost is, compute profit
    if profit_col is None and cost_col is not None:
        out["__profit"] = out[revenue_col] - out[cost_col]
        profit_col = "__profit"

    if profit_col is not None:
        out["__profit_final"] = out[profit_col]
        out["__margin"] = np.where(
            out[revenue_col].astype(float) != 0,
            out["__profit_final"] / out[revenue_col],
            np.nan
        )
    else:
        out["__profit_final"] = np.nan
        out["__margin"] = np.nan

    return out


def month_bucket(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    return dt.dt.to_period("M").astype(str)


def top_n_table(df: pd.DataFrame, dim: str, metric: str, n: int = 5) -> pd.DataFrame:
    return (
        df.groupby(dim, dropna=False)[metric]
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
    )


# ------------------------
# Templates availability
# ------------------------
def available_templates(mapping: dict) -> list[tuple[str, str]]:
    """
    Returns list of (id, label) to show the user.
    Only returns templates that match detected dimensions.
    """
    has = lambda k: k in mapping and mapping[k] is not None

    templates = []
    if has("revenue"):
        templates.append(("overview", "Sales Performance Overview"))

    if has("revenue") and (has("product") or has("category")):
        templates.append(("product", "Product & Profitability"))

    if has("revenue") and (has("country") or has("region") or has("city") or has("channel")):
        templates.append(("geo", "Geo / Channel Performance"))

    if has("revenue") and has("customer"):
        templates.append(("customer", "Customer Performance"))

    return templates


# ------------------------
# Renderers (Streamlit)
# ------------------------
def render_overview(st, df: pd.DataFrame, mapping: dict):
    revenue = mapping["revenue"]
    cost = mapping.get("cost")
    profit = mapping.get("profit")
    datec = mapping.get("date")

    work = add_profit_margin(df, revenue, cost, profit)

    total_rev = float(work[revenue].sum())
    total_profit = float(np.nansum(work["__profit_final"]))
    avg_margin = float(np.nanmean(work["__margin"]))

    st.subheader("Sales Performance Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Revenue", f"{total_rev:,.0f}")
    c2.metric("Total Profit", f"{total_profit:,.0f}" if not np.isnan(total_profit) else "—")
    c3.metric("Avg Margin", f"{avg_margin*100:.1f}%" if not np.isnan(avg_margin) else "—")

    if datec:
        tmp = work.copy()
        tmp["__month"] = month_bucket(tmp[datec])
        trend = tmp.groupby("__month")[[revenue, "__profit_final"]].sum().reset_index()
        st.write("Monthly Trend")
        st.line_chart(trend.set_index("__month")[[revenue, "__profit_final"]])

    dims = []
    for k in ["category", "product", "country", "channel"]:
        if k in mapping:
            dims.append((k, mapping[k]))

    if dims:
        st.write("Top Drivers")
        cols = st.columns(2)
        for i, (k, dimc) in enumerate(dims[:4]):
            with cols[i % 2]:
                st.caption(f"Top {k.title()} by Revenue")
                st.dataframe(top_n_table(work, dimc, revenue, n=5), use_container_width=True)

    # Simple alerts (optional)
    st.write("Alerts")
    alerts = []
    if not np.isnan(avg_margin) and avg_margin < 0.05:
        alerts.append("Low overall margin (< 5%).")
    if total_profit < 0:
        alerts.append("Overall profit is negative.")
    if not alerts:
        alerts.append("No major alerts detected from available columns.")
    st.info("\n".join([f"• {a}" for a in alerts]))


def render_product(st, df: pd.DataFrame, mapping: dict):
    revenue = mapping["revenue"]
    cost = mapping.get("cost")
    profit = mapping.get("profit")
    dim = mapping.get("product") or mapping.get("category")

    st.subheader("Product & Profitability")
    work = add_profit_margin(df, revenue, cost, profit)

    grp = (
        work.groupby(dim, dropna=False)
        .agg(
            revenue_sum=(revenue, "sum"),
            profit_sum=("__profit_final", "sum"),
            margin_avg=("__margin", "mean"),
        )
        .reset_index()
        .sort_values("revenue_sum", ascending=False)
    )

    st.write("Top Products / Categories")
    st.dataframe(grp.head(20), use_container_width=True)

    st.write("High Revenue, Low Margin (Risk)")
    med_rev = grp["revenue_sum"].median() if len(grp) else 0
    risk = grp[(grp["revenue_sum"] > med_rev) & (grp["margin_avg"].fillna(0) < 0.10)]
    st.dataframe(risk.sort_values("revenue_sum", ascending=False).head(20), use_container_width=True)


def render_geo(st, df: pd.DataFrame, mapping: dict):
    revenue = mapping["revenue"]
    cost = mapping.get("cost")
    profit = mapping.get("profit")
    datec = mapping.get("date")

    geo = mapping.get("country") or mapping.get("region") or mapping.get("city")
    channel = mapping.get("channel")

    st.subheader("Geo / Channel Performance")
    work = add_profit_margin(df, revenue, cost, profit)

    if geo:
        st.caption(f"Top {geo} by Revenue")
        st.dataframe(top_n_table(work, geo, revenue, n=10), use_container_width=True)

    if channel:
        st.caption(f"Channel performance ({channel})")
        ch = (
            work.groupby(channel, dropna=False)
            .agg(
                revenue_sum=(revenue, "sum"),
                profit_sum=("__profit_final", "sum"),
                margin_avg=("__margin", "mean"),
            )
            .reset_index()
            .sort_values("revenue_sum", ascending=False)
        )
        st.dataframe(ch, use_container_width=True)

    if datec and (geo or channel):
        dim = channel or geo
        tmp = work.copy()
        tmp["__month"] = month_bucket(tmp[datec])
        pv = (
            tmp.groupby(["__month", dim], dropna=False)[revenue]
            .sum()
            .reset_index()
            .pivot(index="__month", columns=dim, values=revenue)
            .fillna(0)
        )
        st.write(f"Monthly revenue by {dim}")
        st.line_chart(pv)


def render_customer(st, df: pd.DataFrame, mapping: dict):
    revenue = mapping["revenue"]
    cost = mapping.get("cost")
    profit = mapping.get("profit")
    cust = mapping["customer"]

    st.subheader("Customer Performance")
    work = add_profit_margin(df, revenue, cost, profit)

    t = (
        work.groupby(cust, dropna=False)
        .agg(
            revenue_sum=(revenue, "sum"),
            profit_sum=("__profit_final", "sum"),
            margin_avg=("__margin", "mean"),
        )
        .reset_index()
        .sort_values("revenue_sum", ascending=False)
    )

    st.write("Top Customers")
    st.dataframe(t.head(25), use_container_width=True)

    total = t["revenue_sum"].sum()
    top5 = t.head(5)["revenue_sum"].sum()
    if total > 0:
        st.warning(f"Revenue concentration: Top 5 customers = {top5/total*100:.1f}% of revenue")
