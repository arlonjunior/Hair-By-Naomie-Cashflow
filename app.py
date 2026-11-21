from pathlib import Path
import calendar
from datetime import date
import hmac
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Nana Salon Cashflow",
    page_icon="✂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "Nana_Casflow_Jan_to_Oct_2026.csv"
LOGO_FILE = BASE_DIR / "data" / "hair-by-naomie-main-logo.svg"

REQUIRED_COLUMNS = [
    "year",
    "month",
    "month_name",
    "client_count",
    "gross_income_cad",
    "product_cost_cad",
    "other_expenses_cad",
    "total_salon_rent_cad",
    "nana_days_per_week",
    "partner_days_per_week",
    "nana_rent_paid_cad",
]

NUMERIC_DEFAULTS = {
    "year": 2026,
    "month": 1,
    "client_count": 0,
    "gross_income_cad": 0.0,
    "product_cost_cad": 0.0,
    "other_expenses_cad": 0.0,
    "total_salon_rent_cad": 1200.0,
    "nana_days_per_week": 4,
    "partner_days_per_week": 7,
    "nana_rent_paid_cad": 550.0,
}


def get_valid_users() -> dict[str, str]:
    """Return {username: password} from st.secrets['users'], or local fallback."""
    try:
        if "users" in st.secrets:
            return {str(k).strip(): str(v) for k, v in dict(st.secrets["users"]).items()}
        if "APP_USERNAME" in st.secrets and "APP_PASSWORD" in st.secrets:
            return {str(st.secrets["APP_USERNAME"]).strip(): str(st.secrets["APP_PASSWORD"])}
    except Exception:
        pass
    return {"nana": "salon2026"}


def check_login() -> bool:
    """Allow any configured user with equal access to sign in."""
    if st.session_state.get("authenticated", False):
        return True

#   st.markdown("## ✂️ Naomie Salon Cashflow Tracker")
    st.markdown("## Hair By Naomie - Cashflow Tracker")
    st.caption("Private CAD cashflow & profit/loss dashboard")

    valid_users = get_valid_users()

    left_spacer, login_col = st.columns([1.4, 1.0])

    with left_spacer:
        st.markdown("### Private Salon Workspace")
        st.write(
            "Sign in on the right to view monthly cashflow, profit & loss margins, "
            "and partner days-based rent benchmarks."
        )

    with login_col:
        st.markdown("#### Sign In")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            clean_user = username.strip()
            expected_pass = valid_users.get(clean_user)
            if expected_pass is not None and hmac.compare_digest(password, expected_pass):
                st.session_state["authenticated"] = True
                st.session_state["current_user"] = clean_user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    return False

def normalize_and_compute(df: pd.DataFrame) -> pd.DataFrame:
    """Validate schema, coerce types, sort by (year, month), and compute P&L metrics."""
    working = df.copy()
    if working.empty:
        out_cols = REQUIRED_COLUMNS + [
            "total_expenses_cad",
            "net_profit_cad",
            "net_margin_pct",
            "avg_ticket_cad",
            "fair_days_rent_cad",
            "partner_days_share_pct",
            "fair_days_profit_cad",
        ]
        return pd.DataFrame(columns=out_cols)

    # If a legacy combined 'year_month' column is ever uploaded, split it cleanly
    if ("year" not in working.columns or "month" not in working.columns) and "year_month" in working.columns:
        parts = working["year_month"].astype(str).str.strip().str.split("-", n=1, expand=True)
        if parts.shape[1] == 2:
            working["year"] = pd.to_numeric(parts[0], errors="coerce")
            working["month"] = pd.to_numeric(parts[1], errors="coerce")

    missing = [
        c
        for c in ["year", "month", "client_count", "gross_income_cad", "nana_rent_paid_cad"]
        if c not in working.columns
    ]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    for col in REQUIRED_COLUMNS:
        if col not in working.columns:
            working[col] = "" if col == "month_name" else NUMERIC_DEFAULTS.get(col, 0)

    for col, default_val in NUMERIC_DEFAULTS.items():
        working[col] = pd.to_numeric(working[col], errors="coerce").fillna(default_val)

    working["year"] = working["year"].astype(int)
    working["month"] = working["month"].astype(int).clip(1, 12)
    working["client_count"] = working["client_count"].astype(int).clip(lower=0)
    working["nana_days_per_week"] = working["nana_days_per_week"].astype(int).clip(lower=0)
    working["partner_days_per_week"] = working["partner_days_per_week"].astype(int).clip(lower=0)

    for money_col in [
        "gross_income_cad",
        "product_cost_cad",
        "other_expenses_cad",
        "total_salon_rent_cad",
        "nana_rent_paid_cad",
    ]:
        working[money_col] = working[money_col].astype(float).clip(lower=0.0)

    working["month_name"] = working.apply(
        lambda r: (
            str(r["month_name"]).strip()
            if pd.notna(r["month_name"]) and str(r["month_name"]).strip() != ""
            else calendar.month_name[int(r["month"])]
        ),
        axis=1,
    )

    # Deduplicate by (year, month), keeping the latest row
    working = working.drop_duplicates(subset=["year", "month"], keep="last")
    working = working.sort_values(["year", "month"]).reset_index(drop=True)

    # Derived financial metrics
    working["total_expenses_cad"] = (
        working["product_cost_cad"] + working["other_expenses_cad"] + working["nana_rent_paid_cad"]
    )
    working["net_profit_cad"] = working["gross_income_cad"] - working["total_expenses_cad"]
    working["net_margin_pct"] = working.apply(
        lambda r: (r["net_profit_cad"] / r["gross_income_cad"] * 100.0) if r["gross_income_cad"] > 0 else 0.0,
        axis=1,
    )
    working["avg_ticket_cad"] = working.apply(
        lambda r: (r["gross_income_cad"] / r["client_count"]) if r["client_count"] > 0 else 0.0,
        axis=1,
    )

    working["fair_days_rent_cad"] = working.apply(
        lambda r: (
            r["total_salon_rent_cad"]
            * (r["nana_days_per_week"] / (r["nana_days_per_week"] + r["partner_days_per_week"]))
            if (r["nana_days_per_week"] + r["partner_days_per_week"]) > 0
            else r["nana_rent_paid_cad"]
        ),
        axis=1,
    )
    working["partner_days_share_pct"] = working.apply(
        lambda r: (
            r["partner_days_per_week"] / (r["nana_days_per_week"] + r["partner_days_per_week"]) * 100.0
            if (r["nana_days_per_week"] + r["partner_days_per_week"]) > 0
            else 0.0
        ),
        axis=1,
    )
    working["fair_days_profit_cad"] = (
        working["gross_income_cad"]
        - working["product_cost_cad"]
        - working["other_expenses_cad"]
        - working["fair_days_rent_cad"]
    )

    return working


def load_initial_data() -> pd.DataFrame:
    if DATA_FILE.exists():
        raw = pd.read_csv(DATA_FILE)
        return normalize_and_compute(raw)
    empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
    return normalize_and_compute(empty)


def save_master_csv(df: pd.DataFrame) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    export_df = df[REQUIRED_COLUMNS].copy()
    for c in [
        "gross_income_cad",
        "product_cost_cad",
        "other_expenses_cad",
        "total_salon_rent_cad",
        "nana_rent_paid_cad",
    ]:
        export_df[c] = export_df[c].map(lambda x: f"{float(x):.2f}")
    export_df.to_csv(DATA_FILE, index=False)


def upsert_month_row(df: pd.DataFrame, row_dict: dict) -> pd.DataFrame:
    base = df[REQUIRED_COLUMNS].copy()
    new_row_df = pd.DataFrame([row_dict])
    combined = pd.concat([base, new_row_df], ignore_index=True)
    return normalize_and_compute(combined)


def main() -> None:
    if not check_login():
        return

    if "cashflow_df" not in st.session_state:
        st.session_state["cashflow_df"] = load_initial_data()

    df = st.session_state["cashflow_df"]

    raw_user = str(st.session_state.get("current_user", "")).strip()
    display_name = raw_user.capitalize() if raw_user else "User"

    with st.sidebar:
        if LOGO_FILE.exists():
            st.image(str(LOGO_FILE), use_container_width=True)
        st.markdown(
            f"<h3 style='text-align: center; margin-top: 0.5rem;'>Welcome, {display_name}!</h3>",
            unsafe_allow_html=True,
        )
        if st.button("Sign Out", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state.pop("current_user", None)
            st.rerun()

#   st.title("✂️ Hair By Naomie - Cashflow")
    st.title("Hair By Naomie - Cashflow")
    st.caption("• Currency: CAD ($) • Separated Year & Month Ledger • Days-Based Rent Split Analysis")

    if df.empty:
        st.info("No monthly records yet. Use the **CSV Upload & Add Month** tab to import your CSV or add a month.")
        tabs = st.tabs(["CSV Upload & Add Month"])
        with tabs[0]:
            render_data_manager(df)
        return

    tab_month, tab_analytics, tab_data = st.tabs(
        ["📅 Monthly P&L View", "📊 Analytics & History", "📥 CSV Upload & Add Month"]
    )

    # -------------------------------------------------------------------------
    # TAB 1: MONTH-BY-MONTH VIEW
    # -------------------------------------------------------------------------
    with tab_month:
        years_available = sorted(df["year"].unique().tolist(), reverse=True)
        c_yr, c_mo = st.columns([1, 2])
        with c_yr:
            selected_year = st.selectbox("Year", options=years_available, index=0)

        months_in_year = df[df["year"] == selected_year].sort_values("month")
        month_options = [
            (int(r["month"]), f"{int(r['month']):02d} — {r['month_name']} {int(r['year'])}")
            for _, r in months_in_year.iterrows()
        ]
        with c_mo:
            chosen_pair = st.selectbox(
                "Month",
                options=month_options,
                index=len(month_options) - 1,
                format_func=lambda item: item[1],
            )
        selected_month = chosen_pair[0]

        row = months_in_year[months_in_year["month"] == selected_month].iloc[0]

        st.subheader(f"{row['month_name']} {int(row['year'])} Summary")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Gross Client Income", f"${row['gross_income_cad']:,.2f} CAD", f"{int(row['client_count'])} clients")
        k2.metric(
            "Total Expenses (Nana)",
            f"${row['total_expenses_cad']:,.2f} CAD",
            f"Rent paid: ${row['nana_rent_paid_cad']:,.2f}",
        )
        k3.metric("Net Profit / Loss", f"${row['net_profit_cad']:,.2f} CAD", f"Margin: {row['net_margin_pct']:.1f}%")
        k4.metric("Avg Ticket / Client", f"${row['avg_ticket_cad']:,.2f} CAD", f"Products: ${row['product_cost_cad']:,.2f}")

        st.divider()

        left_box, right_box = st.columns(2)
        with left_box:
            st.markdown("### 🏠 Rent & Partner Days Breakdown")
            st.write(f"- **Total Salon Rent:** ${row['total_salon_rent_cad']:,.2f} CAD")
            st.write(
                f"- **Schedule:** Nana **{int(row['nana_days_per_week'])}** days/wk vs. Partner "
                f"**{int(row['partner_days_per_week'])}** days/wk"
            )
            st.write(f"- **Partner Days Share:** **{row['partner_days_share_pct']:.2f}%**")
            st.write(f"- **Nana Rent Actually Paid:** **${row['nana_rent_paid_cad']:,.2f} CAD**")

        with right_box:
            st.markdown("### ⚖️ Proportional Days-Split Benchmark")
            diff_rent = row["nana_rent_paid_cad"] - row["fair_days_rent_cad"]
            st.write(f"- **Proportional Days Rent (`days / total_days`):** **${row['fair_days_rent_cad']:,.2f} CAD**")
            st.write(f"- **Profit Under Days-Split Rent:** **${row['fair_days_profit_cad']:,.2f} CAD**")
            if diff_rent > 0:
                st.info(f"Nana is paying **${diff_rent:,.2f} CAD** above a pure usage-days split this month.")
            elif diff_rent < 0:
                st.success(f"Nana is paying **${abs(diff_rent):,.2f} CAD** below a pure usage-days split this month.")
            else:
                st.success("Nana's rent matches the exact proportional days split.")

 # -------------------------------------------------------------------------
    # TAB 2: MULTI-MONTH ANALYTICS & FULL LEDGER
    # -------------------------------------------------------------------------
    with tab_analytics:
        st.markdown("### Filter Analytics & History")
        st.caption("Defaults to the current year (up to 12 months). Filter by a specific year and/or month(s) anytime.")

        current_yr = date.today().year
        available_years = sorted(df["year"].unique().tolist(), reverse=True)
        year_choices = ["All Years"] + [str(y) for y in available_years]

        default_year_choice = str(current_yr) if str(current_yr) in year_choices else year_choices[1] if len(year_choices) > 1 else "All Years"

        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            selected_year_filter = st.selectbox(
                "Year",
                options=year_choices,
                index=year_choices.index(default_year_choice),
            )

        if selected_year_filter == "All Years":
            year_scoped_df = df.copy()
        else:
            year_scoped_df = df[df["year"] == int(selected_year_filter)].copy()

        month_lookup = {
            m: f"{m:02d} — {calendar.month_name[m]}"
            for m in sorted(year_scoped_df["month"].unique().tolist())
        }
        all_month_nums = sorted(month_lookup.keys())

        with f_col2:
            selected_months = st.multiselect(
                "Month(s) (leave empty for all 12 months in selection)",
                options=all_month_nums,
                default=[],
                format_func=lambda m: month_lookup[m],
            )

        filtered_df = year_scoped_df.copy()
        if selected_months:
            filtered_df = filtered_df[filtered_df["month"].isin(selected_months)]

        filtered_df = filtered_df.sort_values(["year", "month"]).reset_index(drop=True)

        if filtered_df.empty:
            st.warning("No records match the selected year/month filter.")
        else:
            tot_clients = int(filtered_df["client_count"].sum())
            tot_income = float(filtered_df["gross_income_cad"].sum())
            tot_expenses = float(filtered_df["total_expenses_cad"].sum())
            tot_profit = float(filtered_df["net_profit_cad"].sum())
            overall_margin = (tot_profit / tot_income * 100.0) if tot_income > 0 else 0.0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Months Shown", f"{len(filtered_df)} / 12", f"{tot_clients} total clients")
            m2.metric("Period Income", f"${tot_income:,.2f} CAD")
            m3.metric("Period Expenses", f"${tot_expenses:,.2f} CAD")
            m4.metric("Period Net Profit", f"${tot_profit:,.2f} CAD", f"Margin: {overall_margin:.1f}%")

            df_chart = filtered_df.copy()
            df_chart["period"] = df_chart.apply(lambda r: f"{int(r['year'])}-{int(r['month']):02d}", axis=1)
            chart_series = df_chart.set_index("period")[["gross_income_cad", "total_expenses_cad", "net_profit_cad"]]
            chart_series.columns = ["Gross Income (CAD)", "Total Expenses (CAD)", "Net Profit (CAD)"]

            st.markdown("### Income vs. Expenses vs. Net Profit")
            st.bar_chart(chart_series, use_container_width=True)

            st.markdown("### Net Profit Margin (%)")
            margin_series = df_chart.set_index("period")[["net_margin_pct"]]
            margin_series.columns = ["Net Profit Margin (%)"]
            st.line_chart(margin_series, use_container_width=True)

            st.markdown("### Filtered Cashflow Ledger")
            display_cols = [
                "year",
                "month",
                "month_name",
                "client_count",
                "gross_income_cad",
                "product_cost_cad",
                "other_expenses_cad",
                "nana_rent_paid_cad",
                "total_expenses_cad",
                "net_profit_cad",
                "net_margin_pct",
                "fair_days_rent_cad",
            ]
            st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)

            csv_bytes = filtered_df[REQUIRED_COLUMNS].to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Filtered CSV",
                data=csv_bytes,
                file_name="nana_salon_cashflow_filtered.csv",
                mime="text/csv",
            )


    # -------------------------------------------------------------------------
    # TAB 3: CSV UPLOAD & ADD / UPDATE MONTH
    # -------------------------------------------------------------------------
    with tab_data:
        render_data_manager(df)


def render_data_manager(df: pd.DataFrame) -> None:
    st.markdown("### 1. Upload & Merge CSV File")
    st.caption(
        "Upload a CSV using separated columns (`year`, `month`, `month_name`, `client_count`, `gross_income_cad`, "
        "`product_cost_cad`, `other_expenses_cad`, `total_salon_rent_cad`, `nana_days_per_week`, "
        "`partner_days_per_week`, `nana_rent_paid_cad`). Rows match by `(year, month)`."
    )

    uploaded_file = st.file_uploader("Choose CSV file", type=["csv"])
    if uploaded_file is not None:
        try:
            incoming_raw = pd.read_csv(uploaded_file)
            incoming_clean = normalize_and_compute(incoming_raw)
            st.dataframe(incoming_clean[REQUIRED_COLUMNS], use_container_width=True, hide_index=True)

            if st.button("Apply CSV & Upsert by (Year, Month)", type="primary"):
                merged = pd.concat(
                    [df[REQUIRED_COLUMNS], incoming_clean[REQUIRED_COLUMNS]],
                    ignore_index=True,
                )
                updated = normalize_and_compute(merged)
                st.session_state["cashflow_df"] = updated
                save_master_csv(updated)
                st.success("CSV merged and saved successfully!")
                st.rerun()
        except Exception as exc:
            st.error(f"Could not process CSV: {exc}")

    st.divider()
    st.markdown("### 2. Add or Update a Single Month")

    with st.form("add_month_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            yr_val = int(st.number_input("Year", min_value=2024, max_value=2035, value=2026, step=1))
        with c2:
            mo_val = int(st.number_input("Month (1–12)", min_value=1, max_value=12, value=11, step=1))
        with c3:
            clients_val = int(st.number_input("Number of Clients", min_value=0, max_value=500, value=0, step=1))

        c4, c5, c6 = st.columns(3)
        with c4:
            income_val = float(st.number_input("Gross Income (CAD)", min_value=0.0, value=0.0, step=10.0))
        with c5:
            prod_val = float(st.number_input("Product Cost (CAD)", min_value=0.0, value=30.0, step=5.0))
        with c6:
            other_val = float(st.number_input("Other Expenses (CAD)", min_value=0.0, value=0.0, step=5.0))

        c7, c8, c9, c10 = st.columns(4)
        with c7:
            total_rent_val = float(st.number_input("Total Salon Rent (CAD)", min_value=0.0, value=1200.0, step=50.0))
        with c8:
            nana_days_val = int(st.number_input("Nana Days / Week", min_value=0, max_value=7, value=4, step=1))
        with c9:
            partner_days_val = int(st.number_input("Partner Days / Week", min_value=0, max_value=7, value=7, step=1))
        with c10:
            rent_paid_val = float(st.number_input("Nana Rent Paid (CAD)", min_value=0.0, value=550.0, step=10.0))

        save_btn = st.form_submit_button("Save Month Entry", use_container_width=True)

    if save_btn:
        new_entry = {
            "year": yr_val,
            "month": mo_val,
            "month_name": calendar.month_name[mo_val],
            "client_count": clients_val,
            "gross_income_cad": income_val,
            "product_cost_cad": prod_val,
            "other_expenses_cad": other_val,
            "total_salon_rent_cad": total_rent_val,
            "nana_days_per_week": nana_days_val,
            "partner_days_per_week": partner_days_val,
            "nana_rent_paid_cad": rent_paid_val,
        }
        updated = upsert_month_row(df, new_entry)
        st.session_state["cashflow_df"] = updated
        save_master_csv(updated)
        st.success(f"Saved {calendar.month_name[mo_val]} {yr_val}!")
        st.rerun()


if __name__ == "__main__":
    main()
