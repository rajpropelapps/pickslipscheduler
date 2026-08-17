"""OpenAI wrapper grounded in the active warehouse schedule."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv
from openai import OpenAI

# Always load this project's configuration, independent of the directory from
# which Uvicorn was started.  ``override=True`` also replaces an inherited
# empty environment variable with the key in the local .env file.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

def build_context(pickslips, assignments, employees) -> str:
    orders = pickslips.to_dict("records") if pickslips is not None else []
    assigned = assignments.to_dict("records") if assignments is not None else []
    employee_rows = employees.to_dict("records") if employees is not None else []
    return f"""Warehouse data (only use these facts):
Pick-slip lines: {orders}
Assignments: {assigned}
Employees: {employee_rows}
Working day: 08:00–16:00. Availability labels are informational; do not infer conflicts beyond scheduled times."""

def answer_warehouse_question(question: str, pickslips, assignments, employees, history: Iterable[dict]) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured. Add it to .env and restart the app.")
    messages = [
        {"role": "system", "content": "You are a concise warehouse scheduling assistant. Answer only from supplied data. State when data is insufficient; never invent assignments, availability, or operational facts."},
        {"role": "system", "content": build_context(pickslips, assignments, employees)},
        *list(history)[-8:], {"role": "user", "content": question},
    ]
    try:
        response = OpenAI(api_key=key).chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), messages=messages, temperature=0.2)
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc
    answer = response.choices[0].message.content if response.choices else None
    if not answer or not answer.strip():
        raise RuntimeError("OpenAI returned an empty response.")
    return answer.strip()
