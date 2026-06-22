from dataclasses import dataclass, field
from config import XGROUP_MIN_AGE, XGROUP_MAX_AGE


@dataclass
class Swimmer:
    name: str
    age: int                            # age as of 31 Dec of competition year
    gender: str                         # 'M' or 'F'
    entries: dict = field(default_factory=dict)
    # entries keys: (event, gender) tuples, e.g. ("4x50_free", "men")
    # entries values: list of {"stroke": str, "time": float}
    #   Freestyle: [{"stroke": "free", "time": 22.0}]
    #   Medley single: [{"stroke": "back", "time": 26.5}]
    #   Medley multi: [{"stroke": "free", "time": 22.0}, {"stroke": "back", "time": 26.5}]

    @property
    def is_xgroup(self) -> bool:
        """Senior Age Group: 18-24 year olds who can only enter 72+ relays."""
        return XGROUP_MIN_AGE <= self.age <= XGROUP_MAX_AGE

    def enters(self, event: str, gender: str) -> bool:
        return (event, gender) in self.entries

    def get_entries(self, event: str, gender: str) -> list:
        return self.entries.get((event, gender), [])

    def __repr__(self):
        return f"Swimmer({self.name!r}, age={self.age}, gender={self.gender!r})"


@dataclass
class RelayLeg:
    swimmer: Swimmer
    stroke: str       # e.g. 'free', 'back', 'breast', 'fly'
    split_time: float  # seconds


@dataclass
class RelayTeam:
    event: str          # e.g. "4x100_medley"
    age_category: str   # e.g. "160-199" or "72+"
    gender: str         # "men", "women", "mixed"
    legs: list          # list[RelayLeg], always 4
    total_time: float   # sum of splits in seconds

    @property
    def swimmer_names(self) -> list:
        return [leg.swimmer.name for leg in self.legs]

    def format_time(self) -> str:
        secs = self.total_time
        mins = int(secs // 60)
        secs_rem = secs - mins * 60
        return f"{mins}:{secs_rem:05.2f}"

    def __repr__(self):
        return (
            f"RelayTeam({self.event} {self.gender} {self.age_category} "
            f"{self.format_time()} [{', '.join(self.swimmer_names)}])"
        )


@dataclass
class Record:
    level: str          # 'world', 'european', 'british', 'sag'
    event: str
    age_category: str   # e.g. "160-199" or "72+" (sag has no sub-brackets)
    gender: str         # 'men', 'women', 'mixed'
    time: float         # seconds
