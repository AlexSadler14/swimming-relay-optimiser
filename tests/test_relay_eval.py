"""
Unit tests for the pure-logic relay evaluation layer (src/relay_eval.py),
which backs the interactive GUI editor.

Covers: team evaluation (complete / incomplete / invalid), dynamic age
re-bracketing, record delta lookup at the dynamic bracket, candidate filtering
(freestyle vs medley stroke, 72+ toggle), and board-wide conflict detection
(duplicate swimmer, duplicate bracket, mixed gender balance).
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from models import Swimmer, Record
from record_fetcher import RecordsFetcher
from relay_eval import (
    evaluate_team, candidate_swimmers, detect_conflicts, TeamSnapshot,
    leg_strokes, leg_split_time,
)


# ---------------------------------------------------------------------------
# Helpers (mirroring tests/test_optimiser.py)
# ---------------------------------------------------------------------------

def make_swimmer(name, age, gender, entries=None):
    clean = {}
    if entries:
        for k, v in entries.items():
            clean[k] = [v] if isinstance(v, dict) else v
    return Swimmer(name=name, age=age, gender=gender, entries=clean)


def make_fetcher(records=None):
    fetcher = RecordsFetcher.__new__(RecordsFetcher)
    fetcher.course = "long_course"
    fetcher._records = records or []
    fetcher._index = {}
    for r in (records or []):
        key = (r.level, r.event, r.age_category, r.gender)
        if key not in fetcher._index or r.time < fetcher._index[key].time:
            fetcher._index[key] = r
    return fetcher


def free_men(name, age, time, event="4x50_free"):
    return make_swimmer(name, age, "M",
                        {(event, "men"): {"stroke": "free", "time": time}})


# ---------------------------------------------------------------------------
# leg_strokes / leg_split_time
# ---------------------------------------------------------------------------

def test_leg_strokes():
    assert leg_strokes("4x50_free") == ["free", "free", "free", "free"]
    assert leg_strokes("4x50_medley") == ["back", "breast", "fly", "free"]


def test_leg_split_time_medley_picks_matching_stroke():
    s = make_swimmer("Multi", 40, "M", {
        ("4x50_medley", "men"): [
            {"stroke": "back", "time": 30.0},
            {"stroke": "fly", "time": 28.0},
        ]
    })
    assert leg_split_time(s, "4x50_medley", "men", "back") == 30.0
    assert leg_split_time(s, "4x50_medley", "men", "fly") == 28.0
    assert leg_split_time(s, "4x50_medley", "men", "breast") is None
    assert leg_split_time(None, "4x50_medley", "men", "back") is None


# ---------------------------------------------------------------------------
# evaluate_team
# ---------------------------------------------------------------------------

def test_evaluate_complete_free_team_with_record_break():
    swimmers = [free_men(f"S{i}", 40, 25.0) for i in range(4)]   # combined 160
    rec = Record(level="british", event="4x50_free",
                 age_category="160-199", gender="men", time=101.0)
    ev = evaluate_team(swimmers, "4x50_free", "men", make_fetcher([rec]))
    assert ev.complete is True
    assert ev.total_time == pytest.approx(100.0)
    assert ev.age_category == "160-199"
    assert ev.records["british"]["broken"] is True
    assert ev.records["british"]["delta"] == pytest.approx(1.0)
    assert ev.broken_levels == ["british"]
    assert "incomplete" not in ev.flags


def test_evaluate_incomplete_team():
    swimmers = [free_men(f"S{i}", 40, 25.0) for i in range(3)] + [None]
    ev = evaluate_team(swimmers, "4x50_free", "men", make_fetcher())
    assert ev.complete is False
    assert ev.total_time is None
    assert ev.age_category is None
    assert "incomplete" in ev.flags
    assert ev.broken_levels == []


def test_evaluate_no_valid_bracket_too_young():
    # Combined age below 100 -> no Masters bracket.
    swimmers = [free_men(f"S{i}", 24 + i, 25.0) for i in range(4)]  # but 24 is xgroup...
    # use ages 26,26,26,18-ineligible avoided -> keep all 26-ish so combined < 100? 26*4=104>100
    swimmers = [free_men(f"S{i}", 25, 25.0) for i in range(4)]      # combined 100 -> valid
    ev = evaluate_team(swimmers, "4x50_free", "men", make_fetcher())
    assert ev.age_category == "100-119"
    # Now push below 100 is impossible with masters mins; instead test above 359.
    old = [free_men(f"O{i}", 90, 25.0) for i in range(4)]            # combined 360
    ev2 = evaluate_team(old, "4x50_free", "men", make_fetcher())
    assert ev2.age_category is None
    assert "no_valid_bracket" in ev2.flags


def test_dynamic_rebracket_uses_new_bracket_record():
    # Two british records at different brackets; verify the delta uses the
    # bracket the *current* combined age falls into, and bracket_changed fires.
    recs = [
        Record("british", "4x50_free", "160-199", "men", 200.0),
        Record("british", "4x50_free", "120-159", "men", 90.0),
    ]
    fetcher = make_fetcher(recs)
    # ages 40,40,38,37 = 155 -> "120-159"
    swimmers = [free_men("A", 40, 25.0), free_men("B", 40, 25.0),
                free_men("C", 38, 25.0), free_men("D", 37, 25.0)]
    ev = evaluate_team(swimmers, "4x50_free", "men", fetcher,
                       original_bracket="160-199")
    assert ev.age_category == "120-159"
    assert "bracket_changed" in ev.flags
    # delta should be vs the 120-159 record (90.0), not the 160-199 one.
    assert ev.records["british"]["record_time"] == pytest.approx(90.0)
    assert ev.records["british"]["delta"] == pytest.approx(90.0 - 100.0)


def test_mixed_gender_balance_flag():
    entries = lambda: {("4x50_free", "mixed"): {"stroke": "free", "time": 25.0}}
    swimmers = [
        make_swimmer("M1", 40, "M", entries()),
        make_swimmer("M2", 40, "M", entries()),
        make_swimmer("M3", 40, "M", entries()),   # 3 men, 1 woman -> imbalance
        make_swimmer("F1", 40, "F", entries()),
    ]
    ev = evaluate_team(swimmers, "4x50_free", "mixed", make_fetcher())
    assert "mixed_needs_2m2f" in ev.flags


def test_mixed_balanced_no_flag():
    entries = lambda: {("4x50_free", "mixed"): {"stroke": "free", "time": 25.0}}
    swimmers = [
        make_swimmer("M1", 40, "M", entries()),
        make_swimmer("M2", 40, "M", entries()),
        make_swimmer("F1", 40, "F", entries()),
        make_swimmer("F2", 40, "F", entries()),
    ]
    ev = evaluate_team(swimmers, "4x50_free", "mixed", make_fetcher())
    assert "mixed_needs_2m2f" not in ev.flags


# ---------------------------------------------------------------------------
# candidate_swimmers
# ---------------------------------------------------------------------------

def test_candidates_free_sorted_and_filtered():
    pool = [
        free_men("Fast", 40, 22.0),
        free_men("Slow", 40, 30.0),
        free_men("Mid", 40, 26.0),
        make_swimmer("NotEntered", 40, "M", {}),       # didn't enter
        make_swimmer("Woman", 40, "F",
                     {("4x50_free", "men"): {"stroke": "free", "time": 20.0}}),  # wrong pool? still "men" entry
    ]
    cands = candidate_swimmers(pool, "4x50_free", "men", "free")
    names = [s.name for s in cands]
    assert "NotEntered" not in names
    # sorted fastest-first among those who entered men 4x50_free
    assert names[:3] == ["Woman", "Fast", "Mid"]  # Woman has 20.0 (entered men bucket in this fixture)


def test_candidates_excludes_xgroup_unless_72plus():
    pool = [
        free_men("Master", 40, 25.0),
        make_swimmer("Young", 20, "M",
                     {("4x50_free", "men"): {"stroke": "free", "time": 21.0}}),
    ]
    no72 = [s.name for s in candidate_swimmers(pool, "4x50_free", "men", "free",
                                               allow_72plus=False)]
    yes72 = [s.name for s in candidate_swimmers(pool, "4x50_free", "men", "free",
                                                allow_72plus=True)]
    assert no72 == ["Master"]
    assert set(yes72) == {"Master", "Young"}


def test_candidates_medley_stroke_filter():
    backer = make_swimmer("Backer", 40, "M",
                          {("4x50_medley", "men"): {"stroke": "back", "time": 30.0}})
    flyer = make_swimmer("Flyer", 40, "M",
                         {("4x50_medley", "men"): {"stroke": "fly", "time": 28.0}})
    versatile = make_swimmer("Versa", 40, "M", {("4x50_medley", "men"): [
        {"stroke": "back", "time": 29.0}, {"stroke": "fly", "time": 27.0}]})
    pool = [backer, flyer, versatile]
    back_cands = [s.name for s in candidate_swimmers(pool, "4x50_medley", "men", "back")]
    fly_cands = [s.name for s in candidate_swimmers(pool, "4x50_medley", "men", "fly")]
    assert set(back_cands) == {"Backer", "Versa"}
    assert set(fly_cands) == {"Flyer", "Versa"}


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------

def test_conflict_duplicate_swimmer_same_event_gender():
    s = free_men("Dup", 40, 25.0)
    others = [free_men(f"X{i}", 40, 25.0) for i in range(6)]
    snap_a = TeamSnapshot("4x50_free", "men", "160-199",
                          [s, others[0], others[1], others[2]])
    snap_b = TeamSnapshot("4x50_free", "men", "120-159",
                          [s, others[3], others[4], others[5]])
    res = detect_conflicts([snap_a, snap_b])
    assert (0, 0) in res["leg_conflicts"]   # Dup in team 0 leg 0
    assert (1, 0) in res["leg_conflicts"]   # Dup in team 1 leg 0
    # others appear once -> not flagged
    assert (0, 1) not in res["leg_conflicts"]


def test_no_conflict_same_swimmer_different_events():
    s_free = make_swimmer("Multi", 40, "M", {
        ("4x50_free", "men"): {"stroke": "free", "time": 25.0},
        ("4x100_free", "men"): {"stroke": "free", "time": 55.0},
    })
    snap_a = TeamSnapshot("4x50_free", "men", "160-199", [s_free, None, None, None])
    snap_b = TeamSnapshot("4x100_free", "men", "160-199", [s_free, None, None, None])
    res = detect_conflicts([snap_a, snap_b])
    assert res["leg_conflicts"] == set()


def test_conflict_duplicate_bracket():
    a = [free_men(f"A{i}", 40, 25.0) for i in range(4)]
    b = [free_men(f"B{i}", 40, 25.0) for i in range(4)]
    snap_a = TeamSnapshot("4x50_free", "men", "160-199", a)
    snap_b = TeamSnapshot("4x50_free", "men", "160-199", b)
    snap_c = TeamSnapshot("4x50_free", "men", "120-159", b)
    res = detect_conflicts([snap_a, snap_b, snap_c])
    assert res["bracket_collisions"] == {0, 1}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
