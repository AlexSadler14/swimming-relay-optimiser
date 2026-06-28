"""
Finds the best relay team assignment across all (event, gender, age_group) slots.

Within a single (event, gender) pair, a swimmer can only appear in ONE age group
team. Across different events, the same swimmer may appear freely.

Priorities (in order):
  1. Maximise the total number of records broken across all teams.
  2. For record-breaking teams, prefer larger margins below the record.
  3. For all teams, prefer faster times.

Uses Integer Linear Programming via PuLP for globally optimal assignment.
"""
from models import RelayTeam
from relay_builder import build_relay_teams
from scorer import Scorer
from record_fetcher import RecordsFetcher
from config import RELAY_EVENTS, GENDER_KEYS, SCORING_WEIGHTS

RECORD_LEVELS = ["world", "european", "british"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(swimmers: list, fetcher: RecordsFetcher) -> dict:
    """
    Run the full optimisation via Integer Linear Programming.

    Returns a dict keyed by (event, gender, age_category) ->
        {"team": RelayTeam, "score": (record_score, time_score),
         "records_broken": [str]}
    Only slots where at least one valid team exists are included.
    """
    try:
        import pulp
    except ImportError:
        print("  [ERROR] PuLP is required (pip install pulp).")
        return {}

    candidates, scorer = _build_candidates(swimmers, fetcher)
    if not candidates:
        return {}

    n = len(candidates)

    # Index candidates by slot and by (swimmer, event, gender)
    slot_index: dict = {}
    swimmer_event_index: dict = {}

    for i, c in enumerate(candidates):
        slot_key = (c["event"], c["gender"], c["age_category"])
        slot_index.setdefault(slot_key, []).append(i)

        event_key = (c["event"], c["gender"])
        for leg in c["team"].legs:
            sw_key = (leg.swimmer.name, event_key)
            swimmer_event_index.setdefault(sw_key, []).append(i)

    # Build LP
    prob = pulp.LpProblem("SwimmingRelayOptimiser", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n)]

    # Objective: maximise total ILP score
    prob += pulp.lpSum(candidates[i]["ilp_score"] * x[i] for i in range(n))

    # Constraint 1: at most one team per slot
    for j, (_, indices) in enumerate(slot_index.items()):
        prob += pulp.lpSum(x[i] for i in indices) <= 1, f"slot_{j}"

    # Constraint 2: each swimmer in at most one team per (event, gender)
    for j, (_, indices) in enumerate(swimmer_event_index.items()):
        if len(indices) > 1:
            prob += pulp.lpSum(x[i] for i in indices) <= 1, f"swimmer_{j}"

    # Constraint 3: each swimmer in at most `max_relays` teams across all events.
    # The solver still picks whichever relays are best for them and the teams.
    name_to_max = {s.name: s.max_relays for s in swimmers}
    swimmer_total_index: dict = {}
    for i, c in enumerate(candidates):
        for leg in c["team"].legs:
            swimmer_total_index.setdefault(leg.swimmer.name, []).append(i)
    for j, (name, indices) in enumerate(swimmer_total_index.items()):
        cap = name_to_max.get(name)
        if cap is not None:
            prob += pulp.lpSum(x[i] for i in indices) <= cap, f"maxrelays_{j}"

    # Solve (silent)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if pulp.LpStatus[prob.status] not in ("Optimal",):
        print(f"  [WARNING] ILP solver status: {pulp.LpStatus[prob.status]}.")
        return {}

    # Extract solution
    committed = {}
    for i, c in enumerate(candidates):
        if pulp.value(x[i]) is not None and pulp.value(x[i]) > 0.5:
            slot_key = (c["event"], c["gender"], c["age_category"])
            committed[slot_key] = {
                "team":           c["team"],
                "score":          c["score"],
                "records_broken": scorer.records_broken(c["team"]),
            }

    return committed


def summary_stats(committed: dict) -> dict:
    """Aggregate counts of record breaks across all committed teams."""
    counts = {"world": 0, "european": 0, "british": 0, "total_teams": 0}
    for v in committed.values():
        counts["total_teams"] += 1
        for level in v["records_broken"]:
            counts[level] += 1
    return counts


# ---------------------------------------------------------------------------
# Candidate generation and scoring
# ---------------------------------------------------------------------------

def _eligible(swimmer, event: str, gender_key: str) -> bool:
    """Returns True if the swimmer has an entry for this (event, gender)."""
    return swimmer.enters(event, gender_key)


def _build_candidates(swimmers: list, fetcher: RecordsFetcher) -> tuple:
    """
    Generate all valid relay teams across all events and genders.

    Returns (candidates list, Scorer instance).
    """
    scorer = Scorer(fetcher)
    candidates = []
    for event in RELAY_EVENTS:
        for gender_key in GENDER_KEYS:
            eligible = [s for s in swimmers if _eligible(s, event, gender_key)]
            teams = build_relay_teams(eligible, event, gender_key)
            for team in teams:
                candidates.append({
                    "event":        event,
                    "gender":       gender_key,
                    "age_category": team.age_category,
                    "team":         team,
                    "score":        scorer.score(team),
                    "ilp_score":    _ilp_score(team, fetcher),
                })

    return candidates, scorer


def _ilp_score(team: RelayTeam, fetcher: RecordsFetcher) -> float:
    """
    Continuous score for the ILP objective.

    Priority 1 — Records: each broken record level adds its weight
        (world=10000, european=1000, british=100) plus the margin in seconds.
        This ensures more records broken always wins, and within the same
        number of records, larger margins are preferred.

    Priority 2 — Speed: faster teams score higher via a speed bonus.
        The bonus is scaled so it can never override a record-breaking decision
        but strongly differentiates teams when no records are at stake.

    The speed bonus uses -total_time * 0.0005 (max ~0.6 points for a 1200s
    relay).  This keeps all scores positive (participation base is 1) while
    being 5x stronger than the previous 0.0001 weight, ensuring the solver
    clearly prefers faster teams in every slot.
    """
    score = float(SCORING_WEIGHTS["participation"])

    # Speed bonus: prefer faster teams (max ~0.6 pts, always keeps score > 0,
    # well below record weights)
    score -= team.total_time * 0.0005

    for level in RECORD_LEVELS:
        rec = fetcher.get_record(level, team.event, team.age_category, team.gender)
        if rec is not None and team.total_time < rec.time:
            margin = rec.time - team.total_time
            score += SCORING_WEIGHTS[level] + margin

    return score
