from __future__ import annotations
import streamlit as st
from utils.data_processing import DISPLAY_COLUMNS, parse_and_validate_upload, upload_stats

def render() -> None:
    st.header("Data Upload")
    uploaded = st.file_uploader("Upload pick-slip JSON", type=["json"], help="Only JSON pick-slip line records are accepted.")
    if not uploaded:
        st.info("Upload a valid pick-slip JSON file to unlock scheduling and the assistant.")
        return
    frame, errors = parse_and_validate_upload(uploaded)
    if errors:
        for error in errors:
            st.error(error)
        return
    st.session_state.pickslips = frame
    stats = upload_stats(frame)
    c1, c2, c3 = st.columns(3)
    c1.metric("Move orders", stats["move_orders"])
    c2.metric("Total lines", stats["lines"])
    c3.metric("Required-date range", f"{stats['first_date']} → {stats['last_date']}")
    st.subheader("Cleaned pick-slip lines")
    st.dataframe(frame[DISPLAY_COLUMNS], use_container_width=True, hide_index=True)
