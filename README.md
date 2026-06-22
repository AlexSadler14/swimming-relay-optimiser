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

## Quick Start

```bash
python main.py data/swimmers_template.csv --output results.xlsx --club "My Club"
```

This loads swimmers from the template file, runs the optimiser, prints a summary to the console, and exports a formatted Excel report.

## Usage

```
python main.py <swimmers_file> [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `swimmers_file` | Path to a CSV or Excel (.xlsx) file containing swimmer data |
| `--output PATH` | Output Excel file path (default: `results.xlsx`) |
| `--club NAME` | Club name shown in the report header |
| `--csv` | Also export a raw CSV alongside the Excel file |
| `--method {ilp,greedy}` | Optimisation method (default: `ilp`) |

### Examples

```bash
# Basic run with default settings
python main.py swimmers.csv

# Full options
python main.py swimmers.csv --output relay_plan.xlsx --club "Trafford Metro SC" --csv --method ilp

# Quick greedy run (faster, not globally optimal)
python main.py swimmers.csv --method greedy
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

The file `data/records.json` contains 357 relay records compiled from official sources:
- **World Records** (FINA Masters)
- **European Records** (European Aquatics Masters)
- **British Records** (Swim England Masters)
- **SAG Records** (Senior Age Group / 72+)

Records are for long course (50m pool) relays. To update records, edit `data/records.json` directly -- each entry has `level`, `event`, `age_category`, `gender`, and `time` (in seconds).

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
├── main.py                 # CLI entry point, input parsing
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
│   └── reporter.py         # Console summary and Excel/CSV export
│
├── tests/
│   └── test_optimiser.py   # 41 unit tests
│
└── data/
    ├── records.json            # 357 compiled relay records
    └── swimmers_template.csv   # Example input with 8 swimmers
```
