"""
Pure-logic evaluation layer for the interactive relay editor.

Given the four swimmers currently sitting in a relay's legs, work out the
team's time, its (dynamic) age bracket, how it compares to each record level,
and any validity problems -- without any printing or UI. The GUI sits on top
of this; everything here is unit-testable on its own.

Reuses the existing rules: get_relay_age_group (age brackets / 72+), the
Scorer (record deltas), and RELAY_EVENTS (leg strokes).
"""
from dataclasses import dataclass, field

from models import RelayTeam, RelayLeg, Swimmer
from age_category import get_relay_age_group
from scorer import Scorer, RECORD_LEVELS
from config import RELAY_EVENTS


def leg_strokes(event: str) -> list:
    """Fixed stroke for each of the 4 legs of an event.

    Freestyle: ['free','free','free','free']. Medley: ['back','breast','fly','free'].
    """
    return list(RELAY_EVENTS[event]["strokes"])


def leg_split_time(swimmer: "Swimmer | None", event: str, gender: str,
                   stroke: str) -> "float | None":
    """The swimmer's split for a given leg stroke, or None if unavailable.

    Freestyle uses the single declared free time; medley picks the entry whose
    declared stroke matches this leg.
    """
    if swimmer is None:
        return None
    entries = swimmer.get_entries(event, gender)
    if not entries:
        return None
    for e in entries:
        if e["stroke"] == stroke:
            return e["time"]
    # Freestyle legs: the single entry is the free time regardless of label.
    if stroke == "free" and len(entries) == 1:
        return entries[0]["time"]
    return None


@dataclass
class TeamEval:
    """Result of evaluating one relay's current four legs."""
    event: str
    gender: str
    complete: bool                      # all 4 legs have a swimmer (with a usable split)
    total_time: "float | None"          # sum of splits, or None if incomplete
    age_category: "str | None"          # dynamic bracket from combined age, or None
    splits: list                        # per-leg split seconds (float | None), len 4
    # per level -> {"record_time": float|None, "delta": float|None, "broken": bool}
    #   delta > 0 means faster than the record (would break it)
    records: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)   # e.g. "incomplete", "no_valid_bracket", ...

    @property
    def broken_levels(self) -> list:
        return [lv for lv in RECORD_LEVELS if self.records.get(lv, {}).get("broken")]


def evaluate_team(swimmers: list, event: str, gender: str, fetcher,
                  original_bracket: "str | None" = None) -> TeamEval:
    """Evaluate a relay given its four leg swimmers (Swimmer or None, in leg order).

    `original_bracket` is the age group this slot started in, used only to flag
    that a swap has moved the team into a different bracket.
    """
    strokes = leg_strokes(event)
    splits = [leg_split_time(swimmers[i], event, gender, strokes[i]) for i in range(4)]

    filled = [s for s in swimmers if s is not None]
    # "complete" needs every leg filled AND a usable split for each leg's stroke.
    complete = len(filled) == 4 and all(sp is not None for sp in splits)

    flags = []
    # A swimmer is present but can't swim this leg's stroke -> not usable.
    if len(filled) == 4 and not complete:
        flags.append("stroke_missing")
    if not complete:
        flags.append("incomplete")

    # Gender balance (mixed must be exactly 2M + 2F).
    men = sum(1 for s in filled if s.gender == "M")
    women = sum(1 for s in filled if s.gender == "F")
    if gender == "mixed":
        if men > 2 or women > 2 or (len(filled) == 4 and (men != 2 or women != 2)):
            flags.append("mixed_needs_2m2f")

    age_category = None
    total_time = None
    records = {lv: {"record_time": None, "delta": None, "broken": False}
               for lv in RECORD_LEVELS}

    if complete:
        total_time = sum(splits)
        age_category = get_relay_age_group(filled)
        if age_category is None:
            flags.append("no_valid_bracket")
        else:
            if original_bracket is not None and age_category != original_bracket:
                flags.append("bracket_changed")
            team = RelayTeam(
                event=event, age_category=age_category, gender=gender,
                legs=[RelayLeg(swimmer=swimmers[i], stroke=strokes[i],
                               split_time=splits[i]) for i in range(4)],
                total_time=total_time,
            )
            scorer = Scorer(fetcher)
            for lv in RECORD_LEVELS:
                margin = scorer.margin_vs_record(team, lv)   # +ve = faster than record
                rec = fetcher.get_record(lv, event, age_category, gender)
                records[lv] = {
                    "record_time": rec.time if rec else None,
                    "delta": margin,
                    "broken": margin is not None and margin > 0,
                }

    return TeamEval(
        event=event, gender=gender, complete=complete, total_time=total_time,
        age_category=age_category, splits=splits, records=records, flags=flags,
    )


def candidate_swimmers(pool: list, event: str, gender: str, leg_stroke: str,
                       allow_72plus: bool = False) -> list:
    """Swimmers eligible to fill a given leg, fastest-first.

    Permissive on purpose: anyone who entered this (event, gender) and -- for
    medley -- can swim this leg's stroke. X Group (18-24) swimmers are only
    offered when the 72+ category is enabled. Gender balance, age bracket and
    duplicate-usage problems are surfaced by evaluation/conflict checks, not
    filtered out here.
    """
    out = []
    for s in pool:
        if not s.enters(event, gender):
            continue
        if s.is_xgroup and not allow_72plus:
            continue
        t = leg_split_time(s, event, gender, leg_stroke)
        if t is None:
            continue          # can't swim this leg's stroke
        out.append((t, s))
    out.sort(key=lambda ts: ts[0])
    return [s for _, s in out]


@dataclass
class TeamSnapshot:
    """Minimal view of one relay used for cross-team conflict detection."""
    event: str
    gender: str
    age_category: "str | None"
    swimmers: list          # list[Swimmer | None], leg order


def detect_conflicts(snapshots: list) -> dict:
    """Find board-wide problems to highlight.

    Returns:
      "leg_conflicts": set of (team_index, leg_index) -- a swimmer used more than
          once within the same (event, gender) (incl. twice in one team).
      "bracket_collisions": set of team_index -- two or more teams occupy the same
          (event, gender, age_category).
    """
    # Duplicate swimmer within the same (event, gender).
    by_key = {}   # (event, gender, name) -> list of (ti, li)
    for ti, snap in enumerate(snapshots):
        for li, sw in enumerate(snap.swimmers):
            if sw is None:
                continue
            by_key.setdefault((snap.event, snap.gender, sw.name), []).append((ti, li))
    leg_conflicts = set()
    for positions in by_key.values():
        if len(positions) > 1:
            leg_conflicts.update(positions)

    # Two teams in the same (event, gender, age_category).
    by_slot = {}
    for ti, snap in enumerate(snapshots):
        if snap.age_category is None:
            continue
        by_slot.setdefault((snap.event, snap.gender, snap.age_category), []).append(ti)
    bracket_collisions = set()
    for tis in by_slot.values():
        if len(tis) > 1:
            bracket_collisions.update(tis)

    return {"leg_conflicts": leg_conflicts, "bracket_collisions": bracket_collisions}
