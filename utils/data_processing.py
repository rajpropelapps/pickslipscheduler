"""Validation and normalisation for uploaded warehouse pick slips."""
from __future__ import annotations
import json
import re
from io import BytesIO
import pandas as pd

REQUIRED_COLUMNS = {"MoveOrderNum", "MoveOrderLineNum", "Qty Required", "Qty Delivered", "onHandQty", "ItemNumber", "Item Desc", "RequiredDate"}
DISPLAY_COLUMNS = ["MoveOrderNum", "MoveOrderLineNum", "ItemNumber", "Item Desc", "Qty Required", "Qty Delivered", "onHandQty", "RequiredDate"]

# Export systems often remove spaces, change casing, or use a longer label.
HEADER_ALIASES = {
    "moveordernum": "MoveOrderNum", "moveorder": "MoveOrderNum",
    "moveorderlinenum": "MoveOrderLineNum", "moveorderline": "MoveOrderLineNum",
    "qtyrequired": "Qty Required", "requiredqty": "Qty Required", "quantityrequired": "Qty Required",
    "qtydelivered": "Qty Delivered", "deliveredqty": "Qty Delivered", "quantitydelivered": "Qty Delivered",
    "onhandqty": "onHandQty", "onhandquantity": "onHandQty", "availableqty": "onHandQty",
    "itemnumber": "ItemNumber", "itemnum": "ItemNumber", "itemno": "ItemNumber",
    "itemdesc": "Item Desc", "itemdescription": "Item Desc", "description": "Item Desc",
    "requireddate": "RequiredDate", "requiredbydate": "RequiredDate", "duedate": "RequiredDate",
}

def _canonical_column_name(name: object) -> str:
    label = str(name).strip()
    key = re.sub(r"[^a-z0-9]", "", label.lower())
    return HEADER_ALIASES.get(key, label)

def _canonicalise_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    renamed = [_canonical_column_name(column) for column in frame.columns]
    duplicates = pd.Index(renamed)[pd.Index(renamed).duplicated()].unique().tolist()
    if duplicates:
        return None, "Multiple uploaded headers map to the same field: " + ", ".join(duplicates) + "."
    frame = frame.copy()
    frame.columns = renamed
    return frame, None

def _records_from_header_rows(value: object) -> tuple[list[dict] | None, str | None]:
    """Convert ``[[headers], [row values], ...]`` JSON into dictionaries."""
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return None, None
    headers = [str(header).strip() for header in value[0]]
    if len(headers) != len(set(headers)):
        return None, "The first row contains duplicate column headers."
    if len(value) == 1:
        return [], "The file contains headers but no pick-slip rows."
    records: list[dict] = []
    for row_number, row in enumerate(value[1:], start=2):
        if not isinstance(row, list):
            return [], f"Row {row_number} must be an array of values."
        if len(row) != len(headers):
            return [], f"Row {row_number} has {len(row)} values, but the header row has {len(headers)} columns."
        records.append(dict(zip(headers, row, strict=True)))
    return records, None

def _flatten_pickslip_records(value: object, inherited: dict | None = None) -> list[dict]:
    """Flatten flat records and header objects containing line-item arrays.

    Header values such as MoveOrderNum and RequiredDate are carried to every
    nested line. This also prevents pandas from receiving a list as a record.
    """
    inherited = inherited or {}
    if isinstance(value, list):
        records: list[dict] = []
        for item in value:
            records.extend(_flatten_pickslip_records(item, inherited))
        return records
    if not isinstance(value, dict):
        return []

    scalar_values = {key: item for key, item in value.items() if not isinstance(item, (list, dict))}
    context = {**inherited, **scalar_values}
    nested_collections = [item for item in value.values() if isinstance(item, list)]
    if nested_collections:
        records: list[dict] = []
        for collection in nested_collections:
            records.extend(_flatten_pickslip_records(collection, context))
        return records
    # A nested object may be a wrapped record rather than a line-item list.
    nested_objects = [item for item in value.values() if isinstance(item, dict)]
    if nested_objects and not (REQUIRED_COLUMNS & set(context)):
        records: list[dict] = []
        for nested in nested_objects:
            records.extend(_flatten_pickslip_records(nested, context))
        return records
    return [context]

def parse_and_validate_upload(uploaded_file: BytesIO) -> tuple[pd.DataFrame | None, list[str]]:
    try:
        payload = json.load(uploaded_file)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"The uploaded file is not valid JSON: {exc}"]
    if isinstance(payload, dict):
        for key in ("pickslips", "data", "move_orders", "records"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    records, row_error = _records_from_header_rows(payload)
    if row_error:
        return None, [row_error]
    if records is None:
        records = _flatten_pickslip_records(payload)
    if not records:
        return None, ["No pick-slip records were found. Upload rows with a header row followed by values, record objects, or line-item arrays nested under a pick-slip header."]
    frame, header_error = _canonicalise_columns(pd.DataFrame(records))
    if header_error:
        return None, [header_error]
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        return None, ["Missing required field(s): " + ", ".join(missing) + ". Headers found: " + ", ".join(map(str, frame.columns)) + "."]
    if frame["MoveOrderNum"].isna().any() or frame["MoveOrderNum"].astype(str).str.strip().eq("").any():
        return None, ["MoveOrderNum cannot be empty."]
    clean = frame.loc[:, DISPLAY_COLUMNS].copy()
    clean["MoveOrderNum"] = clean["MoveOrderNum"].astype(str).str.strip()
    clean["MoveOrderLineNum"] = clean["MoveOrderLineNum"].astype(str)
    clean["RequiredDate"] = pd.to_datetime(clean["RequiredDate"], format="mixed", errors="coerce")
    if clean["RequiredDate"].isna().any():
        return None, ["RequiredDate must be a valid date for every line."]
    for column in ("Qty Required", "Qty Delivered", "onHandQty"):
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    return clean.sort_values(["RequiredDate", "MoveOrderNum", "MoveOrderLineNum"], kind="stable").reset_index(drop=True), []

def upload_stats(frame: pd.DataFrame) -> dict[str, object]:
    return {"move_orders": frame["MoveOrderNum"].nunique(), "lines": len(frame), "first_date": frame["RequiredDate"].min().date(), "last_date": frame["RequiredDate"].max().date()}
