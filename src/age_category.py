"""
Determines the relay age group for a set of 4 swimmers based on
their combined age as of 31 Dec of the competition year.

Rules:
- Swimmers aged 18–24 are 'X Group' and may ONLY enter the 72+ relay category.
- The 72+ category requires combined age >= 72 AND at least one X Group swimmer.
- Regular Masters categories (100-119, 120-159, ..., 320-359) require no X Group members.
- The combined age bracket is the smallest bracket that contains the sum.
"""
import config
from config import MASTERS_AGE_GROUPS, XGROUP_MIN_AGE, XGROUP_MAX_AGE, XGROUP_RELAY_MIN_COMBINED


def get_relay_age_group(swimmers: list) -> "str | None":
    """
    Given a list of exactly 4 Swimmer objects, return the relay age group string
    (e.g. "160-199", "72+") or None if the combination is not valid for any category.
    """
    combined = sum(s.age for s in swimmers)
    has_xgroup = any(s.is_xgroup for s in swimmers)

    if has_xgroup:
        # 72+ (Senior Age Group) is the only category an X Group swimmer can enter.
        # If the competition doesn't offer it, no valid category exists for this team.
        if not config.ALLOW_72_PLUS_CATEGORY:
            return None
        if combined >= XGROUP_RELAY_MIN_COMBINED:
            return "72+"
        return None  # Has X Group swimmer but combined age < 72 — invalid

    # No X Group: regular Masters brackets
    # Guard: no swimmer under Masters minimum age (25) should appear here
    if any(s.age < XGROUP_MAX_AGE + 1 for s in swimmers):
        return None  # Under-25 non-X-group swimmer slipped through

    for lo, hi in MASTERS_AGE_GROUPS:
        if lo <= combined <= hi:
            return f"{lo}-{hi}"

    return None  # Below 100 (too young), or above 359 (no records held)


def swimmer_eligible_for_category(swimmer, age_category: str) -> bool:
    """
    Check whether a swimmer is eligible to be part of a relay in the given
    age category. X Group swimmers can ONLY appear in 72+ relays.
    """
    if age_category == "72+":
        return True  # Anyone is eligible to swim in 72+ (as long as team has one X Group)
    # Regular Masters: X Group swimmers are not allowed
    return not swimmer.is_xgroup
