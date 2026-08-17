# PickSlip Scheduler

## React scheduler (current UI)

The interactive scheduler is now a React + FullCalendar board backed by FastAPI. Run it in two terminals:

```powershell
uv run uvicorn backend.main:app --reload
cd frontend
$env:Path = "$(Resolve-Path ..\.nodeenv\Scripts);$env:Path"
& ..\.nodeenv\Scripts\npm.cmd run dev
```

The browser UI is served at `http://localhost:5173`. Drag an unassigned pick slip from the right panel onto a picker/time slot. The API persists it to SQLite and prevents overlapping picker assignments. Configure a commercial FullCalendar Scheduler license before production deployment.

A Streamlit application that loads `Move order list.json` from the project folder, assigns pickers, views an eight-hour schedule, and provides a data-grounded OpenAI assistant.

## Features

- Strict JSON validation for the project data, including header-row JSON exports.
- Two app tabs: Scheduler View and AI Assistant.
- FullCalendar resource timeline with picker rows and an Unassigned work row.
- Drag-and-drop assignment, rescheduling, duration resizing, overlap prevention, and SQLite persistence.
- Whole-slip or line-level work blocks, including drag-to-unassign.
- OpenAI assistant grounded only in uploaded pick slips, the supplied employee list, and saved assignments.

## Project layout

```text
app.py
components/             # Streamlit tab components
utils/                  # validation and OpenAI wrapper
Employees list.json     # static picker roster
Move order list.json    # project pick-slip data source
pickslip_scheduler.db   # created on first assignment
```

## Example JSON

```json
[{"MoveOrderNum":"MO-1001","MoveOrderLineNum":"1","Qty Required":5,"Qty Delivered":0,"onHandQty":20,"ItemNumber":"SKU-1","Item Desc":"Laptop","RequiredDate":"2026-08-14"}]
```

Each record must contain `MoveOrderNum`, `MoveOrderLineNum`, `Qty Required`, `Qty Delivered`, `onHandQty`, `ItemNumber`, `Item Desc`, and `RequiredDate`. `MoveOrderNum` cannot be blank.

## Setup and run (uv only)

```powershell
uv sync --link-mode=copy
Copy-Item .env.example .env
# Add OPENAI_API_KEY to .env when using the assistant.
uv run streamlit run app.py
```

If the project is stored in OneDrive and `uv sync` reports a hardlink error, use `uv sync --link-mode=copy` once instead.

## Calendar interaction

Select **All dates** to load every pick slip. Amber blocks are unassigned work: drag them to a picker row to assign them. Blue blocks can be dragged to move them, resized to change duration, or dragged to Unassigned work to remove the assignment. Overlapping picker assignments are rejected.

For commercial deployment, set `FULLCALENDAR_LICENSE_KEY` in `.env`; the resource timeline used for picker rows is a FullCalendar Scheduler feature.

The working day is 08:00–16:00. New assignments default to 30 minutes but can run from 15 to 480 minutes. Availability labels are shown for context; overlaps are allowed because the brief says to ignore employee availability for now. Uploading and scheduling work without an OpenAI key; the assistant gives a clear configuration message until one is supplied.
