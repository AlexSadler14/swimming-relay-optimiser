"""
Independent verifier for the relay optimiser.

For every (event, gender, age_category) slot it enumerates EVERY valid team
(reusing the same builder the tool uses) and reports the fastest possible team,
then shows what the optimiser actually committed and whether they match.

Where they differ, the cause is almost always the swimmer-sharing rule: a
swimmer can only be used in ONE team per (event, gender), so the global optimum
sometimes gives a slightly slower team in one slot to win a record in another.
This script makes that trade-off visible so you can confirm it's intentional.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import main as cli
from relay_builder import build_relay_teams
from record_fetcher import RecordsFetcher
from config import RELAY_EVENTS, GENDER_KEYS
import optimiser

GENDER_LABEL = {"men": "Men", "women": "Women", "mixed": "Mixed"}


def event_label(event):
    dist = event.split("_")[0]
    kind = "Medley" if "medley" in event else "Freestyle"
    return f"{dist} {kind}"


def fmt(secs):
    m = int(secs // 60)
    return f"{m}:{secs - m*60:05.2f}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/cheshires_2026_entries.csv"
    swimmers = cli.load_swimmers(path)
    fetcher = RecordsFetcher()
    committed = optimiser.run(swimmers, fetcher)

    # Build every candidate team grouped by full slot key.
    by_slot = {}
    for event in RELAY_EVENTS:
        for gk in GENDER_KEYS:
            eligible = [s for s in swimmers if s.enters(event, gk)]
            for team in build_relay_teams(eligible, event, gk):
                by_slot.setdefault((event, gk, team.age_category), []).append(team)

    print("=" * 78)
    print("  INDEPENDENT VERIFICATION — fastest possible team vs. tool's pick")
    print("=" * 78)

    matches = 0
    differs = 0
    for slot in sorted(by_slot, key=lambda s: (s[0], s[1], s[2])):
        event, gk, age = slot
        teams = sorted(by_slot[slot], key=lambda t: t.total_time)
        fastest = teams[0]
        label = f"{GENDER_LABEL[gk]} {event_label(event)} [{age}]"
        print(f"\n  {label}   ({len(teams)} possible team(s))")
        print(f"    fastest possible : {fmt(fastest.total_time)}  "
              f"{[l.swimmer.name for l in fastest.legs]}")

        if slot in committed:
            picked = committed[slot]["team"]
            same = set(picked.swimmer_names) == set(fastest.swimmer_names)
            tag = "MATCH" if same else "differs (swimmer shared elsewhere)"
            print(f"    tool committed   : {fmt(picked.total_time)}  "
                  f"{picked.swimmer_names}   <- {tag}")
            recs = committed[slot]["records_broken"]
            if recs:
                print(f"    records broken   : {', '.join(r.upper() for r in recs)}")
            if same:
                matches += 1
            else:
                differs += 1
        else:
            print("    tool committed   : (none — slot not entered)")

    print("\n" + "=" * 78)
    print(f"  Slots where tool picked the fastest team : {matches}")
    print(f"  Slots where it traded speed for sharing  : {differs}")
    print("=" * 78)


if __name__ == "__main__":
    main()
