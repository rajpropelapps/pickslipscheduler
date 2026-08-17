"""Interactive calendar scheduler backed by SQLite assignments."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

DB_PATH = Path("pickslip_scheduler.db")
UNASSIGNED_RESOURCE = "unassigned"
ASSIGNED_COLOR = "#2563eb"
UNASSIGNED_COLOR = "#f59e0b"


def _target_id(order: str, line: str | None) -> str:
    return json.dumps([str(order), None if line is None else str(line)], separators=(",", ":"))


def _read_target(target_id: str) -> tuple[str, str | None]:
    order, line = json.loads(target_id)
    return str(order), None if line is None else str(line)


def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS picker_assignments (
          id INTEGER PRIMARY KEY, moveordernum TEXT NOT NULL, moveorderlinenum TEXT,
          itemnumber TEXT, picker TEXT NOT NULL, pickdatetime TEXT NOT NULL,
          picking_duration_minutes INTEGER NOT NULL, UNIQUE(moveordernum, moveorderlinenum))""")


def _load_assignments() -> pd.DataFrame:
    _init_db()
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("SELECT * FROM picker_assignments", con)


def _save(order: str, line: str | None, item: str | None, picker: str, when: datetime, duration: int) -> None:
    _init_db()
    with sqlite3.connect(DB_PATH) as con:
        # SQLite's UNIQUE constraint does not treat two NULLs as equal.
        if line is None:
            con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum IS NULL", (order,))
        con.execute("""INSERT INTO picker_assignments
          (moveordernum, moveorderlinenum, itemnumber, picker, pickdatetime, picking_duration_minutes)
          VALUES (?, ?, ?, ?, ?, ?)
          ON CONFLICT(moveordernum, moveorderlinenum) DO UPDATE SET
            picker=excluded.picker, pickdatetime=excluded.pickdatetime,
            picking_duration_minutes=excluded.picking_duration_minutes""",
            (order, line, item, picker, when.isoformat(), duration))


def _delete(order: str, line: str | None) -> None:
    with sqlite3.connect(DB_PATH) as con:
        if line is None:
            con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum IS NULL", (order,))
        else:
            con.execute("DELETE FROM picker_assignments WHERE moveordernum=? AND moveorderlinenum=?", (order, line))


def _has_conflict(assignments: pd.DataFrame, picker: str, start: pd.Timestamp, end: pd.Timestamp, target: str) -> bool:
    if assignments.empty:
        return False
    for row in assignments[assignments.picker.eq(picker)].itertuples(index=False):
        if _target_id(row.moveordernum, row.moveorderlinenum) == target:
            continue
        existing_start = pd.Timestamp(row.pickdatetime)
        existing_end = existing_start + pd.Timedelta(minutes=int(row.picking_duration_minutes))
        if start < existing_end and end > existing_start:
            return True
    return False


def _resource_id(employee_id: str) -> str:
    return f"picker:{employee_id}"


def _calendar_events(
    slips: pd.DataFrame,
    assignments: pd.DataFrame,
    employees: pd.DataFrame,
    work_scope: str,
    focused_target: str | None = None,
    include_unassigned: bool = True,
) -> list[dict]:
    """Build assigned blocks plus draggable unassigned work in one calendar."""
    event_data: list[dict] = []
    picker_resources = {row.Name: _resource_id(row.employeeID) for row in employees.itertuples(index=False)}
    target_rows: dict[str, pd.Series] = {}
    line_targets: dict[str, pd.Series] = {}
    header_targets: dict[str, pd.Series] = {}
    for _, row in slips.iterrows():
        line_targets[_target_id(row.MoveOrderNum, row.MoveOrderLineNum)] = row
    for _, row in slips.drop_duplicates("MoveOrderNum").iterrows():
        header_targets[_target_id(row.MoveOrderNum, None)] = row
    if work_scope == "Move orders":
        for _, row in slips.drop_duplicates("MoveOrderNum").iterrows():
            target_rows[_target_id(row.MoveOrderNum, None)] = row
    else:
        for _, row in slips.iterrows():
            target_rows[_target_id(row.MoveOrderNum, row.MoveOrderLineNum)] = row

    assigned_targets: set[str] = set()
    for row in assignments.itertuples(index=False):
        target = _target_id(row.moveordernum, row.moveorderlinenum)
        source = line_targets.get(target)
        if source is None:
            source = header_targets.get(target)
        if source is None:
            continue
        assigned_targets.add(target)
        start = pd.Timestamp(row.pickdatetime)
        end = start + pd.Timedelta(minutes=int(row.picking_duration_minutes))
        suffix = f" · line {row.moveorderlinenum}" if pd.notna(row.moveorderlinenum) else ""
        event_data.append({
            "id": target, "title": f"{row.moveordernum}{suffix}", "start": start.isoformat(), "end": end.isoformat(),
            "resourceId": picker_resources.get(row.picker, UNASSIGNED_RESOURCE), "color": ASSIGNED_COLOR,
            "extendedProps": {"item": row.itemnumber or "", "picker": row.picker, "target": target, "status": "Assigned"},
        })
    if not include_unassigned:
        return event_data
    for target, row in target_rows.items():
        if target in assigned_targets or (focused_target is not None and target != focused_target):
            continue
        start = pd.Timestamp(row.RequiredDate).replace(hour=8, minute=0, second=0)
        line_label = f" · line {row.MoveOrderLineNum}" if work_scope == "Line items" else ""
        event_data.append({
            "id": target, "title": f"{row.MoveOrderNum}{line_label}", "start": start.isoformat(),
            "end": (start + pd.Timedelta(minutes=30)).isoformat(), "resourceId": UNASSIGNED_RESOURCE,
            "color": UNASSIGNED_COLOR,
            "extendedProps": {"item": str(row.ItemNumber), "picker": "Unassigned", "target": target, "status": "Unassigned"},
        })
    return event_data


def _apply_drag(change: dict, assignments: pd.DataFrame, employees: pd.DataFrame, targets: dict[str, pd.Series]) -> str | None:
    """Persist an event drag/resize, returning an error when it cannot be used."""
    event = change.get("event", {})
    target = event.get("id")
    if not target or target not in targets:
        return "The moved calendar block does not match the active pick-slip view."
    resource_id = event.get("resourceId", UNASSIGNED_RESOURCE)
    order, line = _read_target(target)
    if resource_id == UNASSIGNED_RESOURCE:
        _delete(order, line)
        return None
    resource_to_picker = {_resource_id(row.employeeID): row.Name for row in employees.itertuples(index=False)}
    picker = resource_to_picker.get(resource_id)
    if not picker:
        return "Drop work only on a picker row or the Unassigned work row."
    start = pd.Timestamp(event["start"])
    end = pd.Timestamp(event.get("end") or start + pd.Timedelta(minutes=30))
    if end.date() != start.date() or start.hour < 8 or end.hour > 16 or (end.hour == 16 and end.minute > 0):
        return "Assignments must stay within the 08:00–16:00 working day."
    if _has_conflict(assignments, picker, start, end, target):
        return f"{picker} already has work in that time slot. The move was not saved."
    row = targets[target]
    _save(order, line, str(row.ItemNumber), picker, start.to_pydatetime(), int((end - start).total_seconds() // 60))
    return None


def render(employees: pd.DataFrame) -> None:
    st.header("Warehouse calendar")
    slips = st.session_state.get("pickslips")
    if slips is None:
        st.error("Move order list.json could not be loaded, so scheduling is unavailable.")
        return
    assignments = _load_assignments()
    st.session_state.assignments = assignments
    f1, f2 = st.columns([1.3, 1.5])
    selected_picker = f1.selectbox("Picker", ["All pickers", *employees.Name.tolist()])
    work_scope = f2.radio("Pick-slip level", ["Move orders", "Line items"], horizontal=True)
    # RequiredDate is intentionally not used for filtering or timeline placement.
    filtered = slips.copy()

    if selected_picker == "All pickers":
        shown_employees = employees
    else:
        shown_employees = employees[employees.Name.eq(selected_picker)]

    # The right-side palette keeps unassigned work focused and easy to find.
    if work_scope == "Move orders":
        palette_rows = filtered.drop_duplicates("MoveOrderNum").copy()
        palette_rows["target"] = palette_rows["MoveOrderNum"].map(lambda value: _target_id(value, None))
        palette_rows["label"] = palette_rows.apply(
            lambda row: f"{row.MoveOrderNum} · {row.RequiredDate.date()} · {len(filtered[filtered.MoveOrderNum.eq(row.MoveOrderNum)])} lines", axis=1
        )
    else:
        palette_rows = filtered.copy()
        palette_rows["target"] = palette_rows.apply(lambda row: _target_id(row.MoveOrderNum, row.MoveOrderLineNum), axis=1)
        palette_rows["label"] = palette_rows.apply(
            lambda row: f"{row.MoveOrderNum} · line {row.MoveOrderLineNum} · {row.ItemNumber}", axis=1
        )
    assignment_targets = {
        _target_id(row.moveordernum, row.moveorderlinenum)
        for row in assignments.itertuples(index=False)
        if (work_scope == "Move orders" and pd.isna(row.moveorderlinenum))
        or (work_scope == "Line items" and pd.notna(row.moveorderlinenum))
    }
    palette_rows = palette_rows.loc[~palette_rows.target.isin(assignment_targets)].copy()
    palette_map = dict(zip(palette_rows.target, palette_rows.label, strict=True))
    board, palette = st.columns([4, 1.25], gap="large")
    with palette:
        st.subheader("Pick slips")
        st.caption("Unassigned work only. Selecting a pick slip shows its details; it is not placed on the timeline.")
        if palette_map:
            palette_key = f"pickslip_palette_{work_scope}"
            if st.session_state.get(palette_key) not in palette_map:
                st.session_state.pop(palette_key, None)
            focused_target = st.selectbox("Work to schedule", list(palette_map), format_func=palette_map.get, key=palette_key)
            selected_row = palette_rows.loc[palette_rows.target.eq(focused_target)].iloc[0]
            st.markdown(f"**{selected_row.MoveOrderNum}**")
            if work_scope == "Line items":
                st.caption(f"{selected_row.ItemNumber} — {selected_row['Item Desc']}")
            st.dataframe(palette_rows[["MoveOrderNum", "MoveOrderLineNum", "ItemNumber"]].head(100), hide_index=True, use_container_width=True, height=360)
        else:
            focused_target = None
            st.success("All work in this view is assigned.")
    resources = [{"id": UNASSIGNED_RESOURCE, "title": "Unassigned work"}]
    resources += [{"id": _resource_id(row.employeeID), "title": f"{row.Name} — {row.availability}"} for row in shown_employees.itertuples(index=False)]
    events = _calendar_events(filtered, assignments, shown_employees, work_scope, focused_target)
    # Only the selected unassigned pick slip is staged in the calendar; the
    # rest remain in the right-side list.
    resources = ([] if focused_target is None else [{"id": UNASSIGNED_RESOURCE, "title": "Selected pick slip"}])
    resources += [{"id": _resource_id(row.employeeID), "title": row.Name} for row in shown_employees.itertuples(index=False)]
    calendar_assignments = assignments if selected_picker == "All pickers" else assignments[assignments.picker.eq(selected_picker)]
    events = _calendar_events(filtered, calendar_assignments, shown_employees, work_scope, focused_target, include_unassigned=focused_target is not None)
    initial_date = str(pd.Timestamp.now().date())
    options = {
        "initialView": "resourceTimelineDay",
        "initialDate": initial_date, "resources": resources, "editable": True, "eventResizableFromStart": True,
        "eventStartEditable": True, "eventDurationEditable": True, "eventResourceEditable": True, "eventOverlap": False,
        "slotMinTime": "08:00:00", "slotMaxTime": "16:00:00", "slotDuration": "00:30:00",
        "headerToolbar": {"left": "today prev,next", "center": "title", "right": "resourceTimelineDay,resourceTimelineWeek,resourceTimelineMonth"},
        "resourceAreaHeaderContent": "Picker / work", "height": 690, "nowIndicator": True,
    }
    with board:
        st.caption("Drag the amber selected pick slip to a picker row and time. Blue blocks are saved assignments and can be rescheduled.")
        result = calendar(events=events, options=options, license_key=os.getenv("FULLCALENDAR_LICENSE_KEY", "CC-Attribution-NonCommercial-NoDerivatives"), custom_css="""
          .fc-event { border-radius: 5px; font-weight: 600; padding: 2px 4px; }
          .fc-resource-area { min-width: 240px; }
          .fc-timeline-slot { min-width: 42px; }
        """, key=f"warehouse_calendar_{selected_picker}_{initial_date}")

    date_click = result.get("dateClick") if result else None
    if focused_target and date_click:
        clicked_resource = (date_click.get("resource") or {}).get("id")
        click_signature = f"{focused_target}|{date_click.get('date')}|{clicked_resource}"
        if clicked_resource and clicked_resource != UNASSIGNED_RESOURCE and click_signature != st.session_state.get("last_calendar_slot"):
            st.session_state.last_calendar_slot = click_signature
            active_targets = {}
            for _, row in filtered.iterrows():
                active_targets[_target_id(row.MoveOrderNum, row.MoveOrderLineNum)] = row
            for _, row in filtered.drop_duplicates("MoveOrderNum").iterrows():
                active_targets[_target_id(row.MoveOrderNum, None)] = row
            start = pd.Timestamp(date_click["date"])
            error = _apply_drag(
                {"event": {"id": focused_target, "resourceId": clicked_resource, "start": start.isoformat(), "end": (start + pd.Timedelta(minutes=30)).isoformat()}},
                assignments,
                employees,
                active_targets,
            )
            if error:
                st.error(error)
            else:
                st.rerun()

    change = result.get("eventChange") if result else None
    if change:
        event = change.get("event", {})
        signature = "|".join(str(event.get(key, "")) for key in ("id", "start", "end", "resourceId"))
        if signature and signature != st.session_state.get("last_calendar_change"):
            st.session_state.last_calendar_change = signature
            active_targets = {}
            for _, row in filtered.iterrows():
                active_targets[_target_id(row.MoveOrderNum, row.MoveOrderLineNum)] = row
            for _, row in filtered.drop_duplicates("MoveOrderNum").iterrows():
                active_targets[_target_id(row.MoveOrderNum, None)] = row
            error = _apply_drag(change, assignments, employees, active_targets)
            if error:
                st.error(error)
            else:
                st.rerun()

    clicked = result.get("eventClick", {}).get("event", {}) if result else {}
    if clicked.get("id"):
        st.session_state.selected_calendar_target = clicked["id"]
    selected_target = st.session_state.get("selected_calendar_target")
    if selected_target:
        try:
            order, line = _read_target(selected_target)
        except (TypeError, ValueError, json.JSONDecodeError):
            st.session_state.pop("selected_calendar_target", None)
        else:
            is_assigned = not assignments.empty and ((assignments.moveordernum.astype(str).eq(order)) & (assignments.moveorderlinenum.fillna("").astype(str).eq(line or ""))).any()
            if is_assigned and st.button("Unassign selected calendar block"):
                _delete(order, line)
                st.session_state.pop("selected_calendar_target", None)
                st.rerun()
