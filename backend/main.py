from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from utils.data_processing import parse_and_validate_upload
from utils.llm_agent import answer_warehouse_question

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "pickslip_scheduler.db"
app = FastAPI(title="PickSlip Scheduler API")
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+", allow_methods=["*"], allow_headers=["*"])

class Assignment(BaseModel):
    moveordernum: str
    moveorderlinenum: str | None = None
    itemnumber: str | None = None
    picker: str
    pickdatetime: datetime
    picking_duration_minutes: int = Field(30, ge=15, le=480)

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict] = []

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS picker_assignments (
      id INTEGER PRIMARY KEY, moveordernum TEXT NOT NULL, moveorderlinenum TEXT, itemnumber TEXT,
      picker TEXT NOT NULL, pickdatetime TEXT NOT NULL, picking_duration_minutes INTEGER NOT NULL,
      UNIQUE(moveordernum, moveorderlinenum))""")
    return con

def _slips() -> pd.DataFrame:
    frame, errors = parse_and_validate_upload(BytesIO((ROOT / "Move order list.json").read_bytes()))
    if errors or frame is None:
        raise HTTPException(500, detail="; ".join(errors))
    return frame

def _conflict(con: sqlite3.Connection, item: Assignment) -> bool:
    end = item.pickdatetime + pd.Timedelta(minutes=item.picking_duration_minutes)
    rows = con.execute("SELECT * FROM picker_assignments WHERE picker=?", (item.picker,)).fetchall()
    for row in rows:
        if row["moveordernum"] == item.moveordernum and row["moveorderlinenum"] == item.moveorderlinenum:
            continue
        start2 = datetime.fromisoformat(row["pickdatetime"]); end2 = start2 + pd.Timedelta(minutes=row["picking_duration_minutes"])
        if item.pickdatetime < end2 and end > start2:
            return True
    return False

@app.get("/api/bootstrap")
def bootstrap():
    employees = json.loads((ROOT / "Employees list.json").read_text())["warehouse_employees"]
    # pandas represents blank numeric fields as NaN, which standard JSON does
    # not permit. Convert blanks to null before FastAPI serializes the payload.
    frame = _slips().copy()
    frame["RequiredDate"] = frame["RequiredDate"].dt.strftime("%Y-%m-%d")
    slips = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
    with _db() as con:
        assignments = [dict(row) for row in con.execute("SELECT * FROM picker_assignments").fetchall()]
    return {"employees": employees, "pickslips": slips, "assignments": assignments}

@app.post("/api/assignments")
def save_assignment(item: Assignment):
    with _db() as con:
        if _conflict(con, item):
            raise HTTPException(409, "Picker already has work in that time slot.")
        if item.moveorderlinenum is None:
            con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum IS NULL", (item.moveordernum,))
        con.execute("""INSERT INTO picker_assignments (moveordernum,moveorderlinenum,itemnumber,picker,pickdatetime,picking_duration_minutes)
        VALUES (?,?,?,?,?,?) ON CONFLICT(moveordernum,moveorderlinenum) DO UPDATE SET picker=excluded.picker,pickdatetime=excluded.pickdatetime,picking_duration_minutes=excluded.picking_duration_minutes""",
        (item.moveordernum,item.moveorderlinenum,item.itemnumber,item.picker,item.pickdatetime.isoformat(),item.picking_duration_minutes))
        # Commit before replying so a browser refresh can never discard a
        # successfully acknowledged picker assignment.
        con.commit()
    return {"ok": True, "saved": True}

@app.delete("/api/assignments/{order}/{line}")
def delete_assignment(order: str, line: str):
    with _db() as con:
        if line == "_header_": con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum IS NULL", (order,))
        else: con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum=?", (order, line))
    return {"ok": True}

@app.post("/api/assistant")
def assistant_chat(request: ChatRequest):
    employees = pd.DataFrame(json.loads((ROOT / "Employees list.json").read_text())["warehouse_employees"])
    with _db() as con:
        assignments = pd.read_sql_query("SELECT * FROM picker_assignments", con)
    try:
        answer = answer_warehouse_question(request.question, _slips(), assignments, employees, request.history)
    except RuntimeError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    return {"answer": answer}
