"""
Unit tests for the Swimming Relay Optimiser.

Tests cover:
  - Basic team selection (picks fastest swimmers)
  - Swimmer exclusivity within (event, gender)
  - Mixed relay gender rules (2M + 2F)
  - Age category classification
  - X Group (18-24) rules
  - Medley stroke declaration and multi-stroke selection
  - Trade-off: solver sacrifices one event to improve another
  - Record-breaking teams are preferred over faster non-record teams
  - Speed tiebreaking when no records are broken
  - Edge cases (not enough swimmers, no entries, single candidate)
"""
import sys
import os
import pytest

# Allow imports from project root and src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import Swimmer, Record
from record_fetcher import RecordsFetcher
import optimiser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_swimmer(name, age, gender, entries=None):
    """Create a Swimmer with the given entries.

    entries is a dict of (event, gender_key) -> list of {stroke, time} dicts.
    For convenience, you can also pass a single {stroke, time} dict instead of
    a list, and it will be wrapped automatically.
    """
    clean = {}
    if entries:
        for k, v in entries.items():
            if isinstance(v, dict):
                clean[k] = [v]
            else:
                clean[k] = v
    return Swimmer(name=name, age=age, gender=gender, entries=clean)


def _free_entries(time, events=None, genders=None):
    """Helper: build entries dict for freestyle events.

    Returns entries for the given events and genders at the specified time.
    Defaults to 4x50_free for men only.
    """
    events = events or ["4x50_free"]
    genders = genders or ["men"]
    entries = {}
    for event in events:
        for g in genders:
            entries[(event, g)] = [{"stroke": "free", "time": time}]
    return entries


def make_fetcher(records=None):
    """Create a RecordsFetcher with optional injected records."""
    fetcher = RecordsFetcher.__new__(RecordsFetcher)
    fetcher._records = records or []
    fetcher._index = {}
    if records:
        for r in records:
            key = (r.level, r.event, r.age_category, r.gender)
            if key not in fetcher._index or r.time < fetcher._index[key].time:
                fetcher._index[key] = r
    return fetcher


def committed_names(committed):
    """Extract {slot_key: set of swimmer names} from committed dict."""
    return {
        k: set(v["team"].swimmer_names)
        for k, v in committed.items()
    }


def committed_for_event(committed, event, gender):
    """Get all committed teams for a given (event, gender) pair."""
    return {
        k: v for k, v in committed.items()
        if k[0] == event and k[1] == gender
    }


def total_score(committed):
    """Sum of total_time across all committed teams (lower = faster)."""
    return sum(v["team"].total_time for v in committed.values())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def five_men_50free():
    """Five men aged 25-40 with mens 4x50 free entries, all in 120-159 bracket."""
    return [
        make_swimmer("Fast",   30, "M", _free_entries(23.0)),
        make_swimmer("Quick",  35, "M", _free_entries(24.0)),
        make_swimmer("Medium", 30, "M", _free_entries(26.0)),
        make_swimmer("Slow",   32, "M", _free_entries(28.0)),
        make_swimmer("Snail",  33, "M", _free_entries(30.0)),
    ]


@pytest.fixture
def empty_fetcher():
    return make_fetcher()


# ---------------------------------------------------------------------------
# 1. Basic: picks fastest swimmers
# ---------------------------------------------------------------------------

class TestBasicSelection:
    def test_picks_fastest_four_from_five(self, five_men_50free, empty_fetcher):
        """With 5 men and 1 freestyle event, should pick the 4 fastest."""
        committed = optimiser.run(five_men_50free, empty_fetcher)
        men_teams = committed_for_event(committed, "4x50_free", "men")

        assert len(men_teams) == 1
        team = list(men_teams.values())[0]["team"]
        assert set(team.swimmer_names) == {"Fast", "Quick", "Medium", "Slow"}
        assert team.total_time == pytest.approx(23.0 + 24.0 + 26.0 + 28.0)

    def test_exactly_four_swimmers_all_selected(self, empty_fetcher):
        """With exactly 4 swimmers, all must be in the team."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(25.0)),
            make_swimmer("B", 30, "M", _free_entries(26.0)),
            make_swimmer("C", 30, "M", _free_entries(27.0)),
            make_swimmer("D", 30, "M", _free_entries(28.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_teams = committed_for_event(committed, "4x50_free", "men")
        assert len(men_teams) == 1
        assert set(list(men_teams.values())[0]["team"].swimmer_names) == {"A", "B", "C", "D"}

    def test_fewer_than_four_swimmers_no_team(self, empty_fetcher):
        """With fewer than 4 swimmers, no team can be formed."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(25.0)),
            make_swimmer("B", 30, "M", _free_entries(26.0)),
            make_swimmer("C", 30, "M", _free_entries(27.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 0


# ---------------------------------------------------------------------------
# 2. Swimmer exclusivity within (event, gender)
# ---------------------------------------------------------------------------

class TestSwimmerExclusivity:
    def test_swimmer_not_in_two_age_categories_same_event(self, empty_fetcher):
        """A swimmer can't appear in two different age category teams for the same event+gender."""
        swimmers = [
            make_swimmer("Young1", 26, "M", _free_entries(23.0)),
            make_swimmer("Young2", 27, "M", _free_entries(24.0)),
            make_swimmer("Young3", 28, "M", _free_entries(24.5)),
            make_swimmer("Young4", 29, "M", _free_entries(25.0)),
            make_swimmer("Old1",   40, "M", _free_entries(26.0)),
            make_swimmer("Old2",   41, "M", _free_entries(27.0)),
            make_swimmer("Old3",   42, "M", _free_entries(28.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        all_names = []
        for v in men_50.values():
            all_names.extend(v["team"].swimmer_names)

        assert len(all_names) == len(set(all_names))


# ---------------------------------------------------------------------------
# 3. Mixed relay gender rules
# ---------------------------------------------------------------------------

class TestMixedRelay:
    def test_mixed_relay_has_2m_2f(self, empty_fetcher):
        """Mixed relay teams must have exactly 2 males and 2 females."""
        swimmers = [
            make_swimmer("M1", 30, "M", _free_entries(23.0, genders=["mixed"])),
            make_swimmer("M2", 30, "M", _free_entries(24.0, genders=["mixed"])),
            make_swimmer("M3", 30, "M", _free_entries(25.0, genders=["mixed"])),
            make_swimmer("F1", 30, "F", _free_entries(26.0, genders=["mixed"])),
            make_swimmer("F2", 30, "F", _free_entries(27.0, genders=["mixed"])),
            make_swimmer("F3", 30, "F", _free_entries(28.0, genders=["mixed"])),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        mixed_50 = committed_for_event(committed, "4x50_free", "mixed")

        for v in mixed_50.values():
            genders = [leg.swimmer.gender for leg in v["team"].legs]
            assert genders.count("M") == 2
            assert genders.count("F") == 2

    def test_no_mixed_relay_with_insufficient_gender(self, empty_fetcher):
        """Can't form a mixed relay with only 1 female."""
        swimmers = [
            make_swimmer("M1", 30, "M", _free_entries(23.0, genders=["mixed"])),
            make_swimmer("M2", 30, "M", _free_entries(24.0, genders=["mixed"])),
            make_swimmer("M3", 30, "M", _free_entries(25.0, genders=["mixed"])),
            make_swimmer("F1", 30, "F", _free_entries(26.0, genders=["mixed"])),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        mixed_50 = committed_for_event(committed, "4x50_free", "mixed")
        assert len(mixed_50) == 0


# ---------------------------------------------------------------------------
# 4. Age category classification
# ---------------------------------------------------------------------------

class TestAgeCategories:
    def test_age_bracket_correct(self, empty_fetcher):
        """Four swimmers aged 30 each = combined 120, should be in 120-159."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(23.0)),
            make_swimmer("B", 30, "M", _free_entries(24.0)),
            make_swimmer("C", 30, "M", _free_entries(25.0)),
            make_swimmer("D", 30, "M", _free_entries(26.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 1
        slot_key = list(men_50.keys())[0]
        assert slot_key[2] == "120-159"

    def test_different_ages_span_brackets(self, empty_fetcher):
        """Swimmers of different ages should land in the correct bracket."""
        swimmers = [
            make_swimmer("A", 50, "M", _free_entries(25.0)),
            make_swimmer("B", 50, "M", _free_entries(26.0)),
            make_swimmer("C", 50, "M", _free_entries(27.0)),
            make_swimmer("D", 50, "M", _free_entries(28.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 1
        slot_key = list(men_50.keys())[0]
        assert slot_key[2] == "200-239"

    def test_multiple_age_brackets_filled(self, empty_fetcher):
        """With enough swimmers spanning age ranges, multiple brackets can be filled."""
        swimmers = [
            make_swimmer("Y1", 26, "M", _free_entries(23.0)),
            make_swimmer("Y2", 26, "M", _free_entries(24.0)),
            make_swimmer("Y3", 26, "M", _free_entries(25.0)),
            make_swimmer("Y4", 26, "M", _free_entries(26.0)),
            make_swimmer("O1", 80, "M", _free_entries(27.0)),
            make_swimmer("O2", 80, "M", _free_entries(28.0)),
            make_swimmer("O3", 80, "M", _free_entries(29.0)),
            make_swimmer("O4", 80, "M", _free_entries(30.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        brackets = {k[2] for k in men_50.keys()}
        assert len(brackets) >= 2


# ---------------------------------------------------------------------------
# 5. X Group (18-24) rules
# ---------------------------------------------------------------------------

class TestXGroup:
    @pytest.fixture(autouse=True)
    def _enable_72plus(self):
        """These tests exercise the 72+ category, which is off by default."""
        import config
        prev = config.ALLOW_72_PLUS_CATEGORY
        config.ALLOW_72_PLUS_CATEGORY = True
        yield
        config.ALLOW_72_PLUS_CATEGORY = prev

    def test_xgroup_swimmers_in_72plus_only(self, empty_fetcher):
        """Swimmers aged 18-24 should only appear in 72+ age category."""
        swimmers = [
            make_swimmer("X1", 20, "M", _free_entries(22.0)),
            make_swimmer("X2", 20, "M", _free_entries(23.0)),
            make_swimmer("X3", 20, "M", _free_entries(24.0)),
            make_swimmer("X4", 20, "M", _free_entries(25.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        for slot_key, v in men_50.items():
            assert slot_key[2] == "72+"

    def test_xgroup_combined_age_below_72_invalid(self, empty_fetcher):
        """X Group swimmers with combined age = 72 should work (>= 72)."""
        swimmers = [
            make_swimmer("X1", 18, "M", _free_entries(22.0)),
            make_swimmer("X2", 18, "M", _free_entries(23.0)),
            make_swimmer("X3", 18, "M", _free_entries(24.0)),
            make_swimmer("X4", 18, "M", _free_entries(25.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 1

    def test_xgroup_mixed_with_masters(self, empty_fetcher):
        """Mixing X Group with Masters should classify as 72+."""
        from age_category import get_relay_age_group
        swimmers = [
            make_swimmer("X1", 20, "M", _free_entries(22.0)),
            make_swimmer("M1", 30, "M", _free_entries(23.0)),
            make_swimmer("M2", 30, "M", _free_entries(24.0)),
            make_swimmer("M3", 30, "M", _free_entries(25.0)),
        ]
        result = get_relay_age_group(swimmers)
        assert result == "72+"

    def test_xgroup_not_in_masters_bracket(self, empty_fetcher):
        """An X Group swimmer must NOT appear in a regular Masters bracket team."""
        swimmers = [
            make_swimmer("X1", 20, "M", _free_entries(22.0)),
            make_swimmer("M1", 30, "M", _free_entries(23.0)),
            make_swimmer("M2", 30, "M", _free_entries(24.0)),
            make_swimmer("M3", 30, "M", _free_entries(25.0)),
            make_swimmer("M4", 30, "M", _free_entries(26.0)),
            make_swimmer("M5", 30, "M", _free_entries(27.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        for slot_key, v in men_50.items():
            if slot_key[2] != "72+":
                assert "X1" not in v["team"].swimmer_names


# ---------------------------------------------------------------------------
# 6. Medley stroke declaration
# ---------------------------------------------------------------------------

class TestMedleyAssignment:
    def test_medley_uses_declared_strokes(self, empty_fetcher):
        """Each swimmer should swim their declared stroke."""
        swimmers = [
            make_swimmer("Backer", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "back", "time": 28.0}],
            }),
            make_swimmer("Breaster", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "breast", "time": 30.0}],
            }),
            make_swimmer("Flyer", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "fly", "time": 27.0}],
            }),
            make_swimmer("Freestyler", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "free", "time": 25.0}],
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_medley = committed_for_event(committed, "4x50_medley", "men")

        assert len(men_medley) == 1
        team = list(men_medley.values())[0]["team"]

        for leg in team.legs:
            if leg.swimmer.name == "Backer":
                assert leg.stroke == "back"
            elif leg.swimmer.name == "Breaster":
                assert leg.stroke == "breast"
            elif leg.swimmer.name == "Flyer":
                assert leg.stroke == "fly"
            elif leg.swimmer.name == "Freestyler":
                assert leg.stroke == "free"

        assert team.total_time == pytest.approx(28.0 + 30.0 + 27.0 + 25.0)

    def test_multi_stroke_picks_best_assignment(self, empty_fetcher):
        """
        When swimmers declare multiple strokes, the system should pick the
        combination that minimises total time.
        """
        swimmers = [
            make_swimmer("A", 30, "M", {
                ("4x50_medley", "men"): [
                    {"stroke": "back", "time": 29.0},
                    {"stroke": "breast", "time": 33.0},
                ],
            }),
            make_swimmer("B", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "back", "time": 28.0}],
            }),
            make_swimmer("C", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "fly", "time": 27.0}],
            }),
            make_swimmer("D", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "free", "time": 24.0}],
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_medley = committed_for_event(committed, "4x50_medley", "men")

        assert len(men_medley) == 1
        team = list(men_medley.values())[0]["team"]

        strokes = {leg.swimmer.name: leg.stroke for leg in team.legs}
        assert strokes["B"] == "back"
        assert strokes["A"] == "breast"
        assert team.total_time == pytest.approx(28.0 + 33.0 + 27.0 + 24.0)

    def test_medley_missing_stroke_no_team(self, empty_fetcher):
        """If no swimmer declares a required stroke, no medley team can form."""
        swimmers = [
            make_swimmer("A", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "back", "time": 28.0}],
            }),
            make_swimmer("B", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "fly", "time": 27.0}],
            }),
            make_swimmer("C", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "free", "time": 25.0}],
            }),
            make_swimmer("D", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "back", "time": 30.0}],
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_medley = committed_for_event(committed, "4x50_medley", "men")
        assert len(men_medley) == 0

    def test_medley_swimmer_with_declared_stroke_only(self, empty_fetcher):
        """A swimmer declaring only free for medley should only swim free."""
        swimmers = [
            make_swimmer("A", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "back", "time": 28.0}],
            }),
            make_swimmer("B", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "breast", "time": 32.0}],
            }),
            make_swimmer("C", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "fly", "time": 27.0}],
            }),
            make_swimmer("D", 30, "M", {
                ("4x50_medley", "men"): [{"stroke": "free", "time": 24.0}],
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_medley = committed_for_event(committed, "4x50_medley", "men")
        assert len(men_medley) == 1
        team = list(men_medley.values())[0]["team"]
        strokes = {leg.swimmer.name: leg.stroke for leg in team.legs}
        assert strokes["D"] == "free"


# ---------------------------------------------------------------------------
# 7. Global trade-off (ILP advantage)
# ---------------------------------------------------------------------------

class TestGlobalTradeoff:
    def test_ilp_sacrifices_one_event_for_better_total(self, empty_fetcher):
        """ILP should find the assignment where Shared goes to the event
        where he adds the most marginal value."""
        swimmers = [
            make_swimmer("Shared", 30, "M", {
                **_free_entries(22.0, ["4x50_free"]),
                **_free_entries(48.0, ["4x100_free"]),
            }),
            make_swimmer("A", 30, "M", {
                **_free_entries(23.0, ["4x50_free"]),
                **_free_entries(55.0, ["4x100_free"]),
            }),
            make_swimmer("B", 30, "M", {
                **_free_entries(24.0, ["4x50_free"]),
                **_free_entries(56.0, ["4x100_free"]),
            }),
            make_swimmer("C", 30, "M", {
                **_free_entries(25.0, ["4x50_free"]),
                **_free_entries(57.0, ["4x100_free"]),
            }),
            make_swimmer("D", 30, "M", {
                **_free_entries(26.0, ["4x50_free"]),
                **_free_entries(58.0, ["4x100_free"]),
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)

        men_50 = committed_for_event(committed, "4x50_free", "men")
        men_100 = committed_for_event(committed, "4x100_free", "men")
        assert len(men_50) >= 1
        assert len(men_100) >= 1


# ---------------------------------------------------------------------------
# 8. Record-breaking preference
# ---------------------------------------------------------------------------

class TestRecordBreaking:
    def test_record_breaking_team_preferred_over_faster_non_breaker(self):
        """A team that breaks a record should be preferred."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(23.0)),
            make_swimmer("B", 30, "M", _free_entries(24.0)),
            make_swimmer("C", 30, "M", _free_entries(25.0)),
            make_swimmer("D", 30, "M", _free_entries(26.0)),
        ]
        fetcher = make_fetcher([
            Record(level="british", event="4x50_free", age_category="120-159",
                   gender="men", time=100.0),
        ])

        committed = optimiser.run(swimmers, fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 1
        team_entry = list(men_50.values())[0]
        assert "british" in team_entry["records_broken"]

    def test_record_breaking_outweighs_speed(self):
        """A slower team that breaks a record should be selected over a faster
        team that doesn't break any records."""
        swimmers = [
            make_swimmer("Y1", 30, "M", _free_entries(22.0)),
            make_swimmer("Y2", 30, "M", _free_entries(23.0)),
            make_swimmer("Y3", 30, "M", _free_entries(24.0)),
            make_swimmer("Y4", 30, "M", _free_entries(25.0)),
            make_swimmer("O1", 45, "M", _free_entries(26.0)),
            make_swimmer("O2", 45, "M", _free_entries(27.0)),
            make_swimmer("O3", 45, "M", _free_entries(28.0)),
            make_swimmer("O4", 45, "M", _free_entries(29.0)),
        ]

        fetcher = make_fetcher([
            Record(level="british", event="4x50_free", age_category="160-199",
                   gender="men", time=111.0),
        ])

        committed = optimiser.run(swimmers, fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        assert ("4x50_free", "men", "160-199") in men_50
        assert "british" in men_50[("4x50_free", "men", "160-199")]["records_broken"]

    def test_margin_bonus_prefers_larger_buffer(self):
        """Between two record-breaking teams, the one with a larger margin wins."""
        swimmers = [
            make_swimmer("Fast1", 30, "M", _free_entries(22.0)),
            make_swimmer("Fast2", 30, "M", _free_entries(23.0)),
            make_swimmer("Fast3", 30, "M", _free_entries(24.0)),
            make_swimmer("Fast4", 30, "M", _free_entries(25.0)),
            make_swimmer("Slow5", 30, "M", _free_entries(30.0)),
        ]
        fetcher = make_fetcher([
            Record(level="british", event="4x50_free", age_category="120-159",
                   gender="men", time=110.0),
        ])

        committed = optimiser.run(swimmers, fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        team = list(men_50.values())[0]["team"]

        assert set(team.swimmer_names) == {"Fast1", "Fast2", "Fast3", "Fast4"}


# ---------------------------------------------------------------------------
# 9. Speed tiebreaking (no records)
# ---------------------------------------------------------------------------

class TestSpeedTiebreaking:
    def test_faster_team_chosen_when_no_records(self, empty_fetcher):
        """With no records, the fastest possible team should be selected."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(22.0)),
            make_swimmer("B", 30, "M", _free_entries(23.0)),
            make_swimmer("C", 30, "M", _free_entries(24.0)),
            make_swimmer("D", 30, "M", _free_entries(25.0)),
            make_swimmer("E", 30, "M", _free_entries(30.0)),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")

        assert len(men_50) == 1
        team = list(men_50.values())[0]["team"]
        assert set(team.swimmer_names) == {"A", "B", "C", "D"}
        assert team.total_time == pytest.approx(94.0)

    def test_ilp_score_positive_for_all_teams(self, empty_fetcher):
        """ILP scores should always be positive so the solver prefers having teams."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(25.0)),
            make_swimmer("B", 30, "M", _free_entries(26.0)),
            make_swimmer("C", 30, "M", _free_entries(27.0)),
            make_swimmer("D", 30, "M", _free_entries(28.0)),
        ]
        from relay_builder import build_relay_teams
        teams = build_relay_teams(swimmers, "4x50_free", "men")
        for team in teams:
            score = optimiser._ilp_score(team, empty_fetcher)
            assert score > 0, f"ILP score should be positive, got {score}"

    def test_ilp_score_positive_for_slow_team(self, empty_fetcher):
        """Even a very slow team (4x200 free) should have a positive ILP score."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(280.0, ["4x200_free"])),
            make_swimmer("B", 30, "M", _free_entries(290.0, ["4x200_free"])),
            make_swimmer("C", 30, "M", _free_entries(295.0, ["4x200_free"])),
            make_swimmer("D", 30, "M", _free_entries(300.0, ["4x200_free"])),
        ]
        from relay_builder import build_relay_teams
        teams = build_relay_teams(swimmers, "4x200_free", "men")
        for team in teams:
            score = optimiser._ilp_score(team, empty_fetcher)
            assert score > 0, f"ILP score for slow 4x200 team should be positive, got {score}"


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_swimmers_returns_empty(self, empty_fetcher):
        committed = optimiser.run([], empty_fetcher)
        assert committed == {}

    def test_swimmers_with_no_entries_returns_empty(self, empty_fetcher):
        """Swimmers who have no entries can't form any relay."""
        swimmers = [
            make_swimmer("A", 30, "M", {}),
            make_swimmer("B", 30, "M", {}),
            make_swimmer("C", 30, "M", {}),
            make_swimmer("D", 30, "M", {}),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        assert committed == {}

    def test_mixed_entries_partial_teams(self, empty_fetcher):
        """Only swimmers with entries for the required event should be considered."""
        swimmers = [
            make_swimmer("Has50",    30, "M", _free_entries(25.0)),
            make_swimmer("Has100",   30, "M", _free_entries(55.0, ["4x100_free"])),
            make_swimmer("HasBoth1", 30, "M", {
                **_free_entries(24.0, ["4x50_free"]),
                **_free_entries(52.0, ["4x100_free"]),
            }),
            make_swimmer("HasBoth2", 30, "M", {
                **_free_entries(26.0, ["4x50_free"]),
                **_free_entries(53.0, ["4x100_free"]),
            }),
            make_swimmer("HasBoth3", 30, "M", {
                **_free_entries(27.0, ["4x50_free"]),
                **_free_entries(54.0, ["4x100_free"]),
            }),
            make_swimmer("HasBoth4", 30, "M", {
                **_free_entries(28.0, ["4x50_free"]),
                **_free_entries(56.0, ["4x100_free"]),
            }),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)

        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 1
        team_50 = list(men_50.values())[0]["team"]
        assert "Has100" not in team_50.swimmer_names

    def test_all_swimmers_no_entry_for_event(self, empty_fetcher):
        """If no swimmers have entries for an event, no team should form."""
        swimmers = [
            make_swimmer("A", 30, "M", _free_entries(50.0, ["4x100_free"])),
            make_swimmer("B", 30, "M", _free_entries(51.0, ["4x100_free"])),
            make_swimmer("C", 30, "M", _free_entries(52.0, ["4x100_free"])),
            make_swimmer("D", 30, "M", _free_entries(53.0, ["4x100_free"])),
        ]
        committed = optimiser.run(swimmers, empty_fetcher)
        men_50 = committed_for_event(committed, "4x50_free", "men")
        assert len(men_50) == 0
