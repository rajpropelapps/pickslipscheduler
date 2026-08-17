from __future__ import annotations
import json
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st
from components import ai_chat_tab, scheduler_tab
from utils.data_processing import parse_and_validate_upload

st.set_page_config(page_title="PickSlip Scheduler", page_icon="📦", layout="wide")

@st.cache_data
def load_employees() -> pd.DataFrame:
    data = json.loads(Path("Employees list.json").read_text(encoding="utf-8"))
    return pd.DataFrame(data["warehouse_employees"])[["employeeID", "Name", "availability"]]

@st.cache_data
def load_project_pickslips() -> tuple[pd.DataFrame | None, list[str]]:
    """Load the supplied warehouse extract rather than accepting uploads."""
    source = Path("Move order list.json")
    if not source.exists():
        return None, ["Move order list.json was not found in the project folder."]
    return parse_and_validate_upload(BytesIO(source.read_bytes()))

employees = load_employees()
pickslips, load_errors = load_project_pickslips()
if load_errors:
    for error in load_errors:
        st.error(error)
else:
    st.session_state.pickslips = pickslips
st.title("📦 PickSlip Scheduler")
st.caption("Schedule work from the project’s Move order list.json and ask data-grounded questions.")
scheduler_view_tab, assistant_tab = st.tabs(["Scheduler View", "AI Assistant"])
with scheduler_view_tab:
    scheduler_tab.render(employees)
with assistant_tab:
    ai_chat_tab.render(employees)
