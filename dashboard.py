import streamlit as st
import pandas as pd
from pathlib import Path
from analyser import analyse, analyse_df
from st_aggrid import AgGrid, GridOptionsBuilder

st.set_page_config(page_title="Lead QA Dashboard", layout="wide")

PROJECT_DIR = Path(__file__).resolve().parent
XL_PATH = PROJECT_DIR / "Book1.xlsx"

st.title("📊 Lead Quality Assurance Dashboard")

# ------------------ Upload & Template ------------------
col_up, col_dl = st.columns([2, 1])
with col_dl:
    if XL_PATH.exists():
        import io
        sample_buf = io.BytesIO()
        pd.read_excel(XL_PATH, nrows=0).to_excel(sample_buf, index=False)
        st.download_button(
            "⬇️ Download Sample Template",
            data=sample_buf.getvalue(),
            file_name="sample_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

uploaded_file = col_up.file_uploader("Upload Excel for Analysis", type=["xlsx"], accept_multiple_files=False)

if uploaded_file:
    df_uploaded = pd.read_excel(uploaded_file)
    faulty_df, by_date_df, accuracy_df = analyse_df(df_uploaded)
else:
    if not XL_PATH.exists():
        st.error("No default Excel file found and none uploaded.")
        st.stop()
    faulty_df, by_date_df, accuracy_df = analyse(XL_PATH)

# ------------------ Tab 1 ---------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Faulty Lead & Followup", "Employees Fault", "Top Performers"])

with tab1:
    st.subheader("Summary of Faults")
    total_faults = len(faulty_df)
    lead_faults = faulty_df[faulty_df["Issue Column"] == "Lead Status"].shape[0]
    follow_faults = faulty_df[faulty_df["Issue Column"] == "Followup Status"].shape[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Faults", total_faults)
    col2.metric("Lead Status Faults", lead_faults)
    col3.metric("Follow-up Status Faults", follow_faults)

    st.markdown("#### Fault Count by Date")
    st.dataframe(by_date_df, use_container_width=True)

    st.markdown("#### Breakdown by Issue Type & Suggested Fix")
    if not faulty_df.empty:
        pivot = (faulty_df.copy()
                 .assign(Suggestion=lambda d: d["Suggestion"].astype(str))
                 .groupby(["Issue Column", "Suggestion"])  # type: ignore
                 .size()
                 .reset_index(name="Count"))
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("No faults detected in current data.")

    st.markdown("### Detailed Fault List")
    display_df = faulty_df.copy()
    # Beautify suggestion column for readability
    if "Suggestion" in display_df.columns:
        display_df["Suggestion"] = display_df["Suggestion"].apply(lambda x: ", ".join(x) if isinstance(x, (list, tuple)) else x)

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_default_column(filter='agTextColumnFilter', floatingFilter=True, resizable=True)
    grid_options = gb.build()
    AgGrid(
        display_df,
        gridOptions=grid_options,
        height=600,
        fit_columns_on_grid_load=True,
        enable_enterprise_modules=False,
    )

# ------------------ Tab 2 ---------------------------------------------------
with tab2:
    st.subheader("Faults by Employee")
    if not accuracy_df.empty:
        import altair as alt
        emp_df = accuracy_df[["Assigned To", "Fault Count"]].copy()
        emp_df = emp_df.sort_values("Fault Count", ascending=False)
        chart = (
            alt.Chart(emp_df)
            .mark_bar()
            .encode(
                y=alt.Y("Assigned To:N", sort="-x"),
                x="Fault Count:Q",
                tooltip=["Assigned To", "Fault Count"]
            )
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)
    st.dataframe(accuracy_df[["Assigned To", "Fault Count"]], use_container_width=True)

# ------------------ Tab 3 ---------------------------------------------------
with tab3:
    st.subheader("Correct selections (higher is better)")
    if not accuracy_df.empty:
        import altair as alt
        corr_df = accuracy_df[["Assigned To", "Correct"]].copy()
        corr_df = corr_df.sort_values("Correct", ascending=False)
        chart2 = (
            alt.Chart(corr_df)
            .mark_bar(color="#2e7d32")
            .encode(
                y=alt.Y("Assigned To:N", sort="-x"),
                x="Correct:Q",
                tooltip=["Assigned To", "Correct"]
            )
            .properties(height=400)
        )
        st.altair_chart(chart2, use_container_width=True)
    st.dataframe(accuracy_df[["Assigned To", "Correct", "Total"]], use_container_width=True)
