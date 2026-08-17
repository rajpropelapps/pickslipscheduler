from __future__ import annotations
import pandas as pd
import streamlit as st
from utils.llm_agent import answer_warehouse_question

def render(employees: pd.DataFrame) -> None:
    st.header("AI Assistant")
    slips = st.session_state.get("pickslips")
    if slips is None:
        st.info("Upload pick-slip data before asking the warehouse manager assistant.")
        return
    history = st.session_state.setdefault("chat_history", [])
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("Ask about picker assignments, workload, or unassigned pick slips")
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    history.append({"role": "user", "content": question})
    with st.chat_message("assistant"):
        with st.spinner("Reviewing warehouse data…"):
            try:
                answer = answer_warehouse_question(question, slips, st.session_state.get("assignments", pd.DataFrame()), employees, history[:-1])
            except RuntimeError as exc:
                st.error(str(exc))
                return
            st.markdown(answer)
    history.append({"role": "assistant", "content": answer})
