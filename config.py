COMPETITION_YEAR = 2026

# Relay events: each swimmer's leg distance and stroke
RELAY_EVENTS = {
    "4x50_free":    {"distance": 50,  "strokes": ["free",   "free",   "free",  "free"]},
    "4x100_free":   {"distance": 100, "strokes": ["free",   "free",   "free",  "free"]},
    "4x200_free":   {"distance": 200, "strokes": ["free",   "free",   "free",  "free"]},
    "4x50_medley":  {"distance": 50,  "strokes": ["back",   "breast", "fly",   "free"]},
    "4x100_medley": {"distance": 100, "strokes": ["back",   "breast", "fly",   "free"]},
}

GENDER_KEYS = ["men", "women", "mixed"]

# Column mapping: (event, gender) -> dict of CSV column names
# e.g. ("4x50_free", "men") -> {"yn": "mens_4x50_free", "time": "mens_4x50_free_time"}
# e.g. ("4x50_medley", "men") -> {"yn": "mens_4x50_medley", "stroke": "mens_4x50_medley_stroke", "time": "mens_4x50_medley_time"}
EVENT_GENDER_COLS = {}
for _event, _cfg in RELAY_EVENTS.items():
    _is_medley = len(set(_cfg["strokes"])) > 1
    for _gender in GENDER_KEYS:
        _prefix = f"{_gender}s_{_event}" if _gender != "mixed" else f"mixed_{_event}"
        _cols = {"yn": _prefix, "time": f"{_prefix}_time"}
        if _is_medley:
            _cols["stroke"] = f"{_prefix}_stroke"
        EVENT_GENDER_COLS[(_event, _gender)] = _cols

# Masters relay age group brackets: (min_combined, max_combined)
MASTERS_AGE_GROUPS = [
    (100, 119),
    (120, 159),
    (160, 199),
    (200, 239),
    (240, 279),
    (280, 319),
    (320, 359),
]

# Senior Age Group (X Group): swimmers aged 18-24 inclusive
XGROUP_MIN_AGE = 18
XGROUP_MAX_AGE = 24
XGROUP_RELAY_MIN_COMBINED = 72   # 72+ category minimum combined age

SCORING_WEIGHTS = {
    "world":         10000,
    "european":      1000,
    "british":       100,
    "participation": 1,
}
