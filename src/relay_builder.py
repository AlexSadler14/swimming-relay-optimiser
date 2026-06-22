"""
Generates all valid RelayTeam combinations for a given event and gender category.

For freestyle relays: all 4 swimmers swim free; each swimmer provides their time.
For medley relays: back -> breast -> fly -> free (fixed order).
  Each swimmer declares which stroke(s) they can swim (possibly multiple).
  The builder finds the best stroke assignment across each 4-swimmer combo.

A swimmer can appear in multiple different relay events but only once per relay.
X Group swimmers (18-24) are excluded from regular Masters teams — they only
appear in 72+ teams (handled by including them in the full pool; age_category.py
will classify any combo containing them as "72+" or None).
"""
from itertools import combinations, product

from models import RelayTeam, RelayLeg
from age_category import get_relay_age_group
from config import RELAY_EVENTS

MEDLEY_STROKES = ["back", "breast", "fly", "free"]


def build_relay_teams(swimmers: list, event: str, gender_key: str) -> list:
    """
    Generate all valid RelayTeam objects for the given event and gender category.

    swimmers:   pool of Swimmer objects who have entries for this (event, gender_key)
    event:      e.g. "4x50_free", "4x100_medley"
    gender_key: "men", "women", or "mixed"

    Returns a list of RelayTeam objects sorted by total_time ascending.
    """
    cfg = RELAY_EVENTS[event]
    is_medley = len(set(cfg["strokes"])) > 1

    # Split pool by gender
    males   = [s for s in swimmers if s.gender == "M"]
    females = [s for s in swimmers if s.gender == "F"]

    if gender_key == "men":
        combos = list(combinations(males, 4))
    elif gender_key == "women":
        combos = list(combinations(females, 4))
    else:  # mixed: exactly 2M + 2F
        combos = [
            list(mc) + list(fc)
            for mc in combinations(males, 2)
            for fc in combinations(females, 2)
        ]

    results = []
    for combo in combos:
        age_cat = get_relay_age_group(list(combo))
        if age_cat is None:
            continue

        if is_medley:
            result = _best_medley_team(combo, event, gender_key, age_cat)
        else:
            result = _freestyle_team(combo, event, gender_key, age_cat)

        if result is not None:
            results.append(result)

    results.sort(key=lambda t: t.total_time)
    return results


def _freestyle_team(combo, event, gender_key, age_cat) -> "RelayTeam | None":
    """Build a freestyle RelayTeam from swimmers who have entered this event."""
    legs = []
    for swimmer in combo:
        entry_list = swimmer.get_entries(event, gender_key)
        if not entry_list:
            return None
        legs.append(RelayLeg(swimmer=swimmer, stroke="free",
                             split_time=entry_list[0]["time"]))

    legs.sort(key=lambda l: l.split_time)
    total = sum(l.split_time for l in legs)
    return RelayTeam(event=event, age_category=age_cat, gender=gender_key,
                     legs=legs, total_time=total)


def _best_medley_team(combo, event, gender_key, age_cat) -> "RelayTeam | None":
    """
    Find the minimum-time valid assignment of 4 swimmers to 4 medley strokes.

    Each swimmer has declared one or more strokes they can swim. We need to
    find an assignment where each of the 4 strokes (back, breast, fly, free)
    is covered by exactly one swimmer, using only their declared strokes.
    """
    # Build each swimmer's options: list of (stroke, time) they declared
    swimmer_options = []
    for swimmer in combo:
        entry_list = swimmer.get_entries(event, gender_key)
        if not entry_list:
            return None
        swimmer_options.append(entry_list)

    best_time = None
    best_legs = None

    # Try all combinations of stroke choices (one per swimmer)
    for choices in product(*swimmer_options):
        # choices[i] = {"stroke": ..., "time": ...} for swimmer i
        strokes_used = [c["stroke"] for c in choices]

        # All 4 medley strokes must be covered exactly once
        if sorted(strokes_used) != MEDLEY_STROKES:
            continue

        # Build legs in medley order (back, breast, fly, free)
        stroke_to_idx = {c["stroke"]: i for i, c in enumerate(choices)}
        ordered_legs = []
        for stroke in MEDLEY_STROKES:
            si = stroke_to_idx[stroke]
            ordered_legs.append(RelayLeg(
                swimmer=combo[si],
                stroke=stroke,
                split_time=choices[si]["time"],
            ))

        total = sum(l.split_time for l in ordered_legs)
        if best_time is None or total < best_time:
            best_time = total
            best_legs = ordered_legs

    if best_legs is None:
        return None

    return RelayTeam(event=event, age_category=age_cat, gender=gender_key,
                     legs=best_legs, total_time=best_time)
