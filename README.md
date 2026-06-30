# Swimming Relay Optimiser

A tool for Masters swimming clubs to find the optimal relay team assignments that maximise record-breaking potential. Given a pool of swimmers with their event entries, strokes, and times, it works out which swimmers should swim in which relays to break the most records (World, European, British, and SAG) while respecting age group rules and mixed relay requirements.

## Features

- **Globally optimal assignments** using Integer Linear Programming (ILP via PuLP), with a fast greedy fallback
- **Record-aware scoring** -- prioritises teams that can break records, with margin bonuses so teams have a real buffer on race day
- **Masters age group classification** -- automatically assigns teams to the correct age bracket (100-119, 120-159, ..., 320-359) based on combined swimmer ages
- **X Group support** -- swimmers aged 18-24 are placed into the 72+ Senior Age Group (SAG) category
- **Mixed relay handling** -- enforces exactly 2 male + 2 female for mixed relays
- **Multi-stroke medley declarations** -- swimmers can declare multiple strokes for medley events (e.g. `free,back` with `22.00,26.50`) and the system picks the best assignment
- **Participation balancing** -- gently favours underused swimmers in non-competitive relays
- **Excel and CSV output** -- formatted Excel reports with colour-coded record margins, star ratings, and swimmer participation summaries

## Relay Events

| Event | Format |
|-------|--------|
| 4x50 Freestyle | 4 swimmers, 50m each |
| 4x100 Freestyle | 4 swimmers, 100m each |
| 4x200 Freestyle | 4 swimmers, 200m each |
| 4x50 Medley | Back, Breast, Fly, Free (50m each) |
| 4x100 Medley | Back, Breast, Fly, Free (100m each) |

Each event is run across men's, women's, and mixed categories.

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

Dependencies:
- **openpyxl** -- Excel file reading and writing
- **PuLP** -- ILP solver (optional; falls back to greedy method if unavailable)

For running tests:
```bash
pip install pytest
```

## Standalone app (.exe) — no Python needed

To hand the tool to someone without Python, build a single double-clickable Windows app:

1. Double-click **`Build EXE.bat`** (one-time; needs Python + internet to fetch PyInstaller).
2. It produces **`dist/Relay Optimiser.exe`** — a single file you can copy anywhere and double-click to open the editor window. No Python, no command line.

Or build it from a terminal:
```bash
pip install pyinstaller
pyinstaller --noconfirm RelayOptimiser.spec
```

The records database and the ILP solver are bundled inside the exe. (Rebuild after changing `records.json` or the code.)

## Quick Start

**Easiest (no build):** double-click **`Relay Optimiser.bat`** (or drag a swimmers CSV onto it) — needs Python installed. The interactive editor window opens; if you didn't supply a file, click **Load swimmers…** to pick one.

From a terminal:
```bash
python main.py data/swimmers_template.csv --club "My Club"
```

This loads swimmers from the template file, runs the optimiser, and opens the **interactive editor** (see below). To skip the window and write the Excel report directly, add `--excel`.

## Interactive editor (GUI)

Running `main.py` opens a window showing the optimal relay teams. From there you can fine-tune the plan by hand:

- **Swap a swimmer** — each leg has a dropdown listing every valid swimmer for that leg (entered the event, and — for medley — swims that stroke), with their split time. Times and record deltas update instantly.
- **Blank a leg** (`✕`) — remove a swimmer to an empty slot, e.g. while rearranging a mixed relay.
- **Live flags** — the editor highlights problems rather than blocking them: a swimmer used twice in the same event (red), two teams landing in the same age group (red), a mixed relay that isn't 2 men + 2 women (amber), or a swap that moves the team into a different age bracket (amber badge). Record-breaking teams are shaded green.
- **Dynamic age brackets** — swapping swimmers recomputes the team's combined-age bracket and compares against the record for that bracket.
- **Revert to optimal** — undo all manual edits.
- **Re-optimise / Course / 72+** — re-run the optimiser, switch between long/short course records, or toggle the 72+ category.
- **Export to Excel** — save the current (edited) plan as a formatted report.

## Usage

```
python main.py [swimmers_file] [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `swimmers_file` | Path to a CSV or Excel (.xlsx) file. Optional — in GUI mode you can pick one from the window |
| `--excel` | Headless mode: skip the GUI and write the Excel report directly (the original behaviour). Requires a swimmers file |
| `--gui` | Open the interactive editor (this is the default) |
| `--output PATH` | Output Excel filename for `--excel` mode (default: `results.xlsx`) |
| `--club NAME` | Club name shown in the report header |
| `--csv` | In `--excel` mode, also export a raw CSV alongside the Excel file |
| `--allow-72plus` | Enable the 72+ (Senior Age Group) relay category (off by default) |
| `--max-relays N` | Default cap on relays per swimmer |
| `--longcourse` / `--shortcourse` | Which records to compare against: short course (25m, default) or long course (50m) |

### Examples

```bash
# Open the interactive editor (default)
python main.py swimmers.csv --club "Trafford Metro SC"

# Open the editor with no file; pick one from the window
python main.py

# Headless: write the Excel report directly, plus a CSV
python main.py swimmers.csv --excel --output relay_plan.xlsx --csv
```

## Input Format

The input file (CSV or Excel) uses a per-event entry system. Each swimmer declares which events they want to enter, what stroke they'll swim, and their time.

### Base Columns

| Column | Description | Example |
|--------|-------------|---------|
| `name` | Swimmer's name | `Tom Harrison` |
| `age` | Swimmer's age (15-110) | `28` |
| `gender` | `M` or `F` | `M` |

### Event Columns

For each event-gender combination, there are columns to declare entry:

**Freestyle events** (2 columns per event-gender):

| Column | Values |
|--------|--------|
| `mens_4x50_free` | `y` or `n` (entering?) |
| `mens_4x50_free_time` | Time, e.g. `22.00` or `1:54.20` |

Same pattern for `womens_4x50_free`, `mixed_4x50_free`, and all freestyle distances (4x50, 4x100, 4x200).

**Medley events** (3 columns per event-gender):

| Column | Values |
|--------|--------|
| `mens_4x50_medley` | `y` or `n` (entering?) |
| `mens_4x50_medley_stroke` | `back`, `breast`, `fly`, or `free` |
| `mens_4x50_medley_time` | Time for that stroke |

Same pattern for `womens_4x50_medley`, `mixed_4x50_medley`, and 4x100 medley.

### Y/N Rules

- `y` = entering this event (case-insensitive)
- `n` or blank = not entering
- If `y`, the time (and stroke for medley) must be provided
- All event-gender columns are present for every swimmer, even if they're ineligible (e.g. a male swimmer puts `n` for all women's events)

### Multiple Strokes for Medley

A swimmer can declare multiple strokes for a medley event by comma-separating:

```
stroke: free,back
time:   22.00,26.50
```

The system will try both options and pick the assignment that minimises total team time. The number of strokes and times must match.

### Time Format

- `SS.ss` e.g. `28.50` (seconds with 2 decimal places)
- `M:SS.ss` e.g. `1:05.23` (minutes:seconds)
- Times must be between 10s and 20 minutes

### Example

See `data/swimmers_template.csv` for a complete example with 8 swimmers across all events.

## Output

### Console

Prints a summary showing:
- Medley stroke coverage (how many swimmers declared each stroke per medley event)
- Number of relay teams found
- Records potentially broken at each level (World, European, British)
- Detailed team listings with swimmer names, strokes, and margins vs records
- Swimmer participation summary

### Excel Report

A formatted workbook containing:
- Records-broken-at-a-glance summary
- One table per relay team with swimmer names, ages, combined age, estimated time, record comparisons with colour-coded margins (green = breaking, red = missing), and star ratings
- Swimmer participation section showing how many events each swimmer is in

### CSV (optional)

Raw data with one row per relay leg, suitable for further analysis in a spreadsheet.

## How the Optimiser Works

### Scoring Hierarchy

The optimiser uses a multi-level scoring system where record-breaking always takes priority:

1. **Record weights** (100 - 10,000 points) -- breaking a World record scores 10,000, European 1,000, British 100. Margin bonuses reward breaking records by larger amounts
2. **Participation base** (1 point) -- every valid team gets 1 point
3. **Speed tiebreaker** (~0.01 - 0.12 points) -- when no records are at stake, faster teams are preferred
4. **Participation bonus** (~0.0 - 0.12 points) -- in non-competitive relays (>10s from all records), underused swimmers get a small boost

### ILP Method (Default)

Uses Integer Linear Programming to find the globally optimal assignment. Constraints:
- At most one team per (event, gender, age group) slot
- Each swimmer in at most one team per (event, gender) pair

### Greedy Method

Ranks all candidate teams by score and commits them one at a time, skipping any that conflict with already-committed teams. Faster but not guaranteed to find the global optimum.

## Records Database

The file `data/records.json` holds relay records compiled from official sources, for **both** long course (50m pool) and short course (25m pool):
- **World Records** (World Aquatics Masters)
- **European Records** (European Aquatics Masters)
- **British Records** (Swim England Masters)
- **SAG Records** (Senior Age Group / 72+)

The JSON is split into `long_course` and `short_course` sections, each containing `world` / `european` / `british` levels keyed by `gender` -> `age_category` -> `event`. The optimiser compares against the short-course set by default; pass `--longcourse` to use the 50m-pool records instead. **Make sure the swimmer times in your input file are for the same course you select.**

SAG (72+) records are published long course only, so the same SAG figures are used for both courses. To update records, edit `data/records.json` directly (`null` means no record set / N/T).

## Configuration

Scoring weights and thresholds can be adjusted in `config.py`:

```python
SCORING_WEIGHTS = {
    "world":         10000,
    "european":      1000,
    "british":       100,
    "participation": 1,
}
COMPETITIVE_THRESHOLD_SECS = 10.0   # seconds from record to be "competitive"
PARTICIPATION_WEIGHT = 0.03         # strength of participation bonus
```

## Running Tests

```bash
pytest tests/ -v
```

The test suite contains 41 tests covering constraint satisfaction, scoring logic, medley stroke assignment, edge cases, and participation balancing.

## Project Structure

```
Swimming Relay Optimiser/
├── main.py                 # Entry point: GUI by default, --excel for headless
├── Relay Optimiser.bat     # Double-click launcher (opens the GUI)
├── config.py               # Events, scoring weights, age brackets, column mappings
├── requirements.txt        # Python dependencies
│
├── src/
│   ├── models.py           # Data classes (Swimmer, RelayTeam, Record, etc.)
│   ├── age_category.py     # Age group classification & X Group rules
│   ├── relay_builder.py    # Generates valid relay team combinations
│   ├── scorer.py           # Scores teams against records
│   ├── record_fetcher.py   # Loads and indexes records from JSON
│   ├── optimiser.py        # ILP and greedy optimisation methods
│   ├── reporter.py         # Console summary and Excel/CSV export
│   ├── timefmt.py          # Shared time formatters
│   ├── relay_eval.py       # Pure logic backing the GUI (eval, candidates, conflicts)
│   └── relay_gui.py        # Interactive Tkinter editor
│
├── tests/
│   ├── test_optimiser.py   # Optimiser unit tests
│   └── test_relay_eval.py  # GUI logic unit tests
│
└── data/
    ├── records.json            # compiled relay records (long + short course)
    └── swimmers_template.csv   # Example input with 8 swimmers
```
