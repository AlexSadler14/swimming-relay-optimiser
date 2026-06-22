"""
Loads relay records from data/records.json into Record objects.
Provides fast lookup by (level, event, age_category, gender).
"""
import json
import os
from models import Record

# Path relative to project root
_RECORDS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "records.json")

LEVELS = ["world", "european", "british"]
SAG_CATEGORY = "72+"


def _parse_time(time_str: str) -> float:
    """Convert 'M:SS.hh' string to float seconds."""
    parts = time_str.strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    return int(parts[0]) * 60 + float(parts[1])


def load_records() -> list:
    """Load all records from JSON and return list[Record]."""
    with open(_RECORDS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    records = []

    # Masters records (world / european / british)
    for level in LEVELS:
        level_data = data[level]
        for gender, age_groups in level_data.items():
            for age_cat, events in age_groups.items():
                for event, time_str in events.items():
                    if time_str is None:
                        continue
                    records.append(Record(
                        level=level,
                        event=event,
                        age_category=age_cat,
                        gender=gender,
                        time=_parse_time(time_str),
                    ))

    # SAG records (apply to 72+ relay category)
    for gender, events in data["sag"].items():
        if not isinstance(events, dict):
            continue
        for event, time_str in events.items():
            if time_str is None:
                continue
            for level in LEVELS:
                # SAG records serve as world/european/british equivalents for 72+
                # We store them under all three levels so the scorer can check each
                records.append(Record(
                    level=level,
                    event=event,
                    age_category=SAG_CATEGORY,
                    gender=gender,
                    time=_parse_time(time_str),
                ))

    return records


class RecordsFetcher:
    """
    Provides O(1) lookup of records by (level, event, age_category, gender).
    """

    def __init__(self):
        self._records = load_records()
        self._index: dict = {}
        for rec in self._records:
            key = (rec.level, rec.event, rec.age_category, rec.gender)
            # Keep only the fastest (lowest time) per key — should be unique but guard anyway
            if key not in self._index or rec.time < self._index[key].time:
                self._index[key] = rec

    def get_record(self, level: str, event: str, age_category: str, gender: str) -> "Record | None":
        return self._index.get((level, event, age_category, gender))

    def all_records(self) -> list:
        return self._records
