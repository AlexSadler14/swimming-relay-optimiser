"""
Scores a RelayTeam against the records database.

Score tuple: (record_score: int, time_score: float)
  record_score: sum of SCORING_WEIGHTS for each record level beaten, plus participation
  time_score:   negative total_time (so lower time = higher score for tiebreaking)

Higher score is better on both components.
"""
from models import RelayTeam
from record_fetcher import RecordsFetcher
from config import SCORING_WEIGHTS

RECORD_LEVELS = ["world", "european", "british"]


class Scorer:
    def __init__(self, fetcher: RecordsFetcher):
        self._fetcher = fetcher

    def score(self, team: RelayTeam) -> tuple:
        """
        Returns (record_score, time_score).
        record_score includes participation (always >= 1 for any valid team).
        """
        record_score = SCORING_WEIGHTS["participation"]

        for level in RECORD_LEVELS:
            rec = self._fetcher.get_record(
                level, team.event, team.age_category, team.gender
            )
            if rec is not None and team.total_time < rec.time:
                record_score += SCORING_WEIGHTS[level]

        time_score = -team.total_time  # lower time = higher (less negative) score
        return (record_score, time_score)

    def records_broken(self, team: RelayTeam) -> list:
        """Return list of record levels this team would break."""
        broken = []
        for level in RECORD_LEVELS:
            rec = self._fetcher.get_record(
                level, team.event, team.age_category, team.gender
            )
            if rec is not None and team.total_time < rec.time:
                broken.append(level)
        return broken

    def margin_vs_record(self, team: RelayTeam, level: str) -> "float | None":
        """
        Seconds faster than the record at the given level.
        Positive = faster (record broken). Negative = slower. None = no record.
        """
        rec = self._fetcher.get_record(
            level, team.event, team.age_category, team.gender
        )
        if rec is None:
            return None
        return rec.time - team.total_time
