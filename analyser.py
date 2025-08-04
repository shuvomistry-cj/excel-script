"""Analyser: produces data frames required by dashboard.
Usage (stand-alone):
    python analyser.py Book1.xlsx
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Tuple
from rules_engine import validate_row


def analyse_df(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Analyse using an already-loaded DataFrame."""
    # ------------- Identify issues row-wise ---------------------------------
    issues_list: list[dict] = []
    for idx, row in df.iterrows():
        issues = validate_row(row)
        for issue in issues:
            issues_list.append({
                "Created Date": row.get("Created Date"),
                "Lead Name": row.get("Lead Name"),
                "Mobile Number": row.get("Mobile Number"),
                "Assigned To": row.get("Assigned To"),
                "Issue Column": issue["column"],
                "Wrong Value": issue["wrong"],
                "Suggestion": issue.get("suggestion"),
                "Reason": issue["reason"],
            })

    faulty_df = pd.DataFrame(issues_list)
    if not faulty_df.empty:
        faulty_df["Date"] = pd.to_datetime(faulty_df["Created Date"], unit="ms").dt.date

    # ------------- Aggregations ---------------------------------------------
    by_date = faulty_df.groupby("Date").size().reset_index(name="Fault Count") if not faulty_df.empty else pd.DataFrame()
    by_employee = faulty_df.groupby("Assigned To").size().reset_index(name="Fault Count") if not faulty_df.empty else pd.DataFrame()

    # Accuracy df: total rows per employee minus faults
    total_by_emp = df.groupby("Assigned To").size().reset_index(name="Total")
    merged = total_by_emp.merge(by_employee, on="Assigned To", how="left").fillna(0)
    merged["Correct"] = merged["Total"] - merged["Fault Count"]

    return faulty_df, by_date, merged

def analyse(excel_path: str | Path):
    df = pd.read_excel(excel_path)
    return analyse_df(df)

if __name__ == "__main__":
    import sys
    xl = sys.argv[1] if len(sys.argv) > 1 else "Book1.xlsx"
    fd, bd, acc = analyse(xl)
    print("Faulty rows:", len(fd))
