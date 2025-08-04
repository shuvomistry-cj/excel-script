"""Rule engine for validating lead records against business conditions.
Parses `conditions.txt` (human-written) and converts it into a
structured dictionary, then validates each row coming from the Excel dump.

Designed to work standalone; if you provide a MistralAI key via `.env`,
we will optionally improve the parse using the model, otherwise we use a
basic heuristic parser.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple
import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
CONDITION_FILE = PROJECT_DIR / "conditions.txt"

load_dotenv(PROJECT_DIR / ".env")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _basic_parse_conditions(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Extract lead-status blocks and allowed follow-up statuses using regex.
    Returns a dict {lead_status: {"allowed_followups": [...], "raw": <block>}}"""

    blocks: Dict[str, Dict[str, List[str]]] = {}
    current_status = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Check for numbered lead status lines like "2. Cold Lead" or "8. Proposal Shared"
        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            current_status = m.group(1).strip()
            blocks[current_status] = {"allowed_followups": [], "raw": ""}
            continue
        # accumulate raw
        if current_status:
            blocks[current_status]["raw"] += line + "\n"
        # capture follow-up status lines
        if current_status and any(keyword in line.lower() for keyword in ["status options", "next actions"]):
            # subsequent lines until blank or numbered will be options
            continue  # the keyword line itself is skipped
        if current_status and line and not re.match(r"^\d+\.\s+", line):
            # treat top-level bullets as options when they contain keywords typical of follow-ups
            if re.search(r"response|callback|scheduled|engagement|feedback|waiting", line, re.I):
                # Remove leading bullet marks / dashes / emojis
                option = re.sub(r"^[•\-*\s\d.🔥⏳✅]+", "", line).strip()
                # Only the phrase before any dash or parentheses.
                option = re.split(r"\s*[-–]\s*", option)[0].strip()
                blocks[current_status]["allowed_followups"].append(option)
    # Deduplicate
    for v in blocks.values():
        v["allowed_followups"] = sorted(set(v["allowed_followups"]))
    return blocks


def load_rules() -> Dict:
    """Load/parse the conditions.txt (and optionally refine with Mistral)."""
    if not CONDITION_FILE.exists():
        raise FileNotFoundError(f"Missing {CONDITION_FILE}")

    text = CONDITION_FILE.read_text(encoding="utf-8")
    rules = _basic_parse_conditions(text)

    # Optionally: call Mistral for more accurate extraction (omitted to keep
    # offline operation). If key exists, user can enable later.
    return rules


RULES = load_rules()

# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

# Bill range mapping for core lead statuses.
BILL_RULES = {
    "Cold Lead": (None, 999),  # <1000
    "Warm Lead": (1000, 1999),
    "Hot Lead": (2000, None),  # >=2000
}


def _check_bill_status(lead_status: str, bill: float | None) -> Tuple[bool, str | None]:
    if bill is None or lead_status not in BILL_RULES:
        return True, None  # cannot validate
    low, high = BILL_RULES[lead_status]
    if low is not None and bill < low:
        return False, f"Highest_Bill {bill} is below minimum {low} for {lead_status}"
    if high is not None and bill > high:
        return False, f"Highest_Bill {bill} exceeds max {high} for {lead_status}"
    return True, None


def validate_row(row: dict) -> List[dict]:
    """Validate a panda Series (converted to dict). Returns list of issue dicts."""
    issues: List[dict] = []
    lead_status = str(row.get("Lead Status", "")).strip()
    follow_status = (str(row.get("Followup Status", "")).strip() or None)
    bill = row.get("Highest_Bill")

    # 1. Bill / lead-status alignment
    ok, reason = _check_bill_status(lead_status.replace("🔥🔥", "").replace("✅", "").strip(), bill)
    if not ok:
        issues.append({
            "column": "Lead Status",
            "wrong": lead_status,
            "reason": reason,
            "suggestion": _suggest_lead_status_for_bill(bill),
        })

    # 2. Follow-up allowed list check
    allowed = RULES.get(lead_status.replace("🔥🔥", "").replace("✅", "").strip(), {}).get("allowed_followups", [])
    if allowed and (follow_status or "None") not in allowed:
        issues.append({
            "column": "Followup Status",
            "wrong": follow_status,
            "reason": f"'{follow_status}' not allowed for {lead_status}",
            "suggestion": allowed,
        })

    return issues


def _suggest_lead_status_for_bill(bill: float | None) -> str | None:
    if bill is None:
        return None
    if bill < 1000:
        return "Cold Lead"
    if bill < 2000:
        return "Warm Lead"
    return "Hot Lead"


if __name__ == "__main__":
    import json, pandas as pd, sys

    excel_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not excel_path:
        print("Usage: python rules_engine.py <excel_file>")
        sys.exit(1)
    df = pd.read_excel(excel_path)
    all_issues = []
    for _, r in df.iterrows():
        issues = validate_row(r)
        if issues:
            item = r.to_dict()
            item["issues"] = issues
            all_issues.append(item)
    print(json.dumps(all_issues, indent=2, ensure_ascii=False))
