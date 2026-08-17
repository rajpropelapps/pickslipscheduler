# Reusable Prompt: AI Pick-Slip Scheduler

You are an expert Python full-stack developer and AI engineer. Build a polished, local-first proof of concept for a warehouse manager to assign pick slips to warehouse pickers.

## Product goal

Create an operational scheduling application that helps a warehouse manager view unassigned pick-slip work, assign it to pickers, and ask grounded questions about the current schedule. The UI must feel like a calendar/work-planning tool, not a collection of disconnected widgets.

## Required technology

- Frontend: React with Vite.
- Scheduling UI: FullCalendar resource timeline with interaction support.
- Backend: Python FastAPI.
- Database: SQLite for permanent assignments.
- Data processing: pandas and numpy.
- AI: OpenAI Python SDK, with the key read from `OPENAI_API_KEY` in `.env`.
- Python package and environment management: `uv` only.

Do not use Streamlit for the scheduler UI. Do not use yfinance, portfolio data, or financial-analysis functionality.

## Data sources and loading

The project includes these static JSON files in its root:

- `Move order list.json`: pick-slip / move-order data.
- `Employees list.json`: picker names.

Do not show a data-upload tab. Load these project files when the backend starts or when data is requested.

The move-order parser must accept common JSON structures, including:

- A list of records.
- A header row followed by rows of values.
- Pick-slip headers containing nested line-item arrays.

Normalize the input into line-level records. Convert missing values to JSON-safe nulls before returning API responses.

## Required data fields

Treat `MoveOrderNum` as the pick-slip header identifier. Required line-level fields are:

- `MoveOrderLineNum`
- `ItemNumber`
- `Item Desc`
- `Qty Required`
- `Qty Delivered`
- `onHandQty`
- `RequiredDate`

Validate that `MoveOrderNum` is present. Display clear data-validation errors rather than crashing. Preserve a move-order hierarchy concept: a picker may be assigned either to an entire header or to an individual line item.

## Application navigation

Create exactly two top-level tabs:

1. **Scheduler**
2. **AI Warehouse Manager Analyst**

## Scheduler: shared behavior

Place a filter toolbar at the top of the Scheduler tab with:

- Schedule date.
- Picker selector, including “All pickers.”
- Search/filter by move order, item number, or item description.
- A view toggle between **Timeline** and **Assign picker**.

All filters must work consistently in both views. The picker list should show only picker names; do not show availability labels. Ignore a pick slip’s `RequiredDate` for assignment eligibility, while retaining it as data.

Show only unassigned pick slips in any unassigned-work list. Never create assignments by default. Once an assignment succeeds, immediately remove that pick slip from every unassigned list.

## Scheduler view A: Timeline

Use a calendar-style resource timeline:

- Picker names are resource rows.
- The day runs from 08:00 to 16:00.
- The center area is the timeline/calendar, with persisted assignments rendered as events.
- A clearly visible right-side panel contains unassigned pick slips.
- An unassigned pick slip can be dragged from the panel onto a picker/time slot.
- An existing assignment can be moved to another valid time or picker.

Add a non-drag alternative:

- Right-click a picker/time slot.
- Present a selector containing only currently unassigned pick slips.
- Selecting a pick slip creates the assignment for that picker and time slot.

Provide concise inline instructions explaining both drag-and-drop and right-click workflows.

## Scheduler view B: Assign picker

Make this view visually consistent with Timeline view: the same filter toolbar, a large left work area, and a right-side panel.

- Display unassigned pick slips as drop targets in the main work area.
- Display picker names as draggable items in the right-side panel.
- Dragging a picker onto a pick slip assigns that picker at the currently selected date and time.
- Right-clicking an unassigned pick slip shows a picker selector as a non-drag alternative.
- Use the same API and validation path as Timeline assignments.

## Assignment persistence and rules

Persist assignments in SQLite with at least:

- `moveordernum`
- `moveorderlinenum`
- `itemnumber`
- `picker`
- `pickdatetime`
- `picking_duration_minutes`

Rules:

- One pick slip or pick-slip line may have only one assignment at a time.
- A picker can have multiple assignments only when their time ranges do not overlap.
- Default picking duration is 30 minutes; allow a bounded configurable duration if the UI supports it.
- A successful API response must be committed to SQLite before the frontend reports success.
- Assignments must remain after browser refresh and backend restart.
- On a validation conflict, return a clear error, revert any visual drag operation, and leave the pick slip unassigned.
- Support unassignment through a backend endpoint and keep the UI/data state consistent.

## API requirements

Expose a FastAPI API with at least:

- `GET /api/bootstrap` for employees, normalized pick slips, and saved assignments.
- `POST /api/assignments` to validate and save an assignment.
- `DELETE /api/assignments/{order}/{line}` to unassign work.
- `POST /api/assistant` for the AI Analyst chat.

Allow local frontend development origins through CORS. Return useful HTTP status codes, especially `409` for scheduling conflicts and `503` for unavailable AI configuration or requests.

## AI Warehouse Manager Analyst tab

Build a professional chatbot interface rather than a plain form:

- Assistant identity/header and short explanatory text.
- Empty-state welcome message with suggested warehouse questions.
- Distinct user and assistant message bubbles.
- Scrollable conversation history.
- Multiline text composer with Enter to send and Shift+Enter for a new line.
- Loading/thinking state and helpful API error display.

Use OpenAI only after the user asks a question. The backend must load `.env` by an explicit project-root path, not depend on the process working directory. Use `OPENAI_MODEL` with a sensible default such as `gpt-4.1-mini`.

Ground every response only in the supplied pick slips, employees, and persisted assignments. The assistant must not invent picker availability, operational facts, or assignments. It should state when the available data is insufficient.

Useful example questions:

- Which pick slips are unassigned?
- Which picker has the most scheduled work?
- What work is scheduled for a particular picker?
- Are there picker scheduling conflicts?

## UX and quality requirements

- Use a responsive, clean, accessible design.
- Include clear loading, empty, retry, success, and validation-error states.
- Avoid a perpetual loading screen if an API request fails.
- Use concise labels and color only to improve scheduling comprehension.
- Ensure both assignment views have the same visual language.
- Keep the AI tab independent from scheduler rendering problems.

## Project structure

Use a maintainable structure similar to:

```text
pickslip-scheduler/
  backend/
    main.py
  frontend/
    src/
      main.jsx
      style.css
  utils/
    data_processing.py
    llm_agent.py
  Move order list.json
  Employees list.json
  pyproject.toml
  uv.lock
  .env.example
  .gitignore
  README.md
```

Keep `.env`, SQLite runtime data, virtual environments, and `node_modules` out of version control. Never hardcode secrets.

## Completion checks

Before declaring the project complete:

1. Confirm the backend serializes blank data safely and `/api/bootstrap` returns valid JSON.
2. Confirm assignments persist through a reload/restart.
3. Confirm drag/drop and right-click assignment flows use the same backend validation.
4. Confirm assigned pick slips disappear from unassigned lists.
5. Confirm the React production build succeeds.
6. Confirm the AI tab gracefully handles a missing or failed OpenAI configuration.
