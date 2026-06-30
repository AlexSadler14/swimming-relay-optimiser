"""
Interactive relay-team editor (Tkinter).

Opens a window showing the optimiser's plan. Each leg has a dropdown to swap in
another valid swimmer or blank it out; times and record deltas update live;
conflicts are highlighted; and the whole board can be reverted to the optimal
plan or re-optimised. Built on the pure logic in relay_eval.py.

Entry point: launch_gui(...). Wired up from main.py.
"""
import os
import copy
from dataclasses import dataclass, field

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config
from models import RelayTeam, RelayLeg
from record_fetcher import RecordsFetcher
from scorer import Scorer
from config import RELAY_EVENTS, GENDER_KEYS
import optimiser
import reporter
from reporter import _GENDER_LABEL, _EVENT_LABEL
from timefmt import fmt_time, fmt_split
from relay_eval import (
    evaluate_team, candidate_swimmers, detect_conflicts, TeamSnapshot,
    leg_strokes, leg_split_time,
)

# ---- colours ----
C_BREAK   = "#E2EFDA"   # green  -- breaks a record
C_CONFLICT = "#F8CBAD"  # red    -- duplicate swimmer / duplicate bracket
C_WARN    = "#FFE699"   # amber  -- bracket changed / mixed imbalance / incomplete
C_NEUTRAL = "#FFFFFF"
C_LEGBAD  = "#F4B6A8"   # red leg row
C_CARD_BORDER = "#BFBFBF"

C_UNDER = "#2E7D32"     # green text -- under the record (faster)
C_OVER  = "#C00000"     # red text   -- over the record (slower)
C_MUTED = "#666666"     # grey label text
C_EVENT_HEAD = "#44546A"  # event grouping bar
C_EVENT_TEXT = "#FFFFFF"
C_GENDER_HEAD = "#8497B0"  # gender sub-bar (men / women / mixed)
C_GENDER_TEXT = "#FFFFFF"

# British -> European -> World, the order the user reads record times in.
_LEVEL_DISPLAY_ORDER = ["british", "european", "world"]
_LEVEL_SHORT = {"british": "British", "european": "European", "world": "World"}

BLANK_LABEL = "— (empty) —"


# ===========================================================================
# Editable board model (no Tk -- unit-testable)
# ===========================================================================

@dataclass
class EditableLeg:
    stroke: str                       # fixed for this leg position
    swimmer: object = None            # Swimmer | None


@dataclass
class EditableTeam:
    event: str
    gender: str
    original_bracket: str
    legs: list                        # list[EditableLeg], length 4
    original_swimmers: list = field(default_factory=list)   # snapshot for revert

    def current_swimmers(self) -> list:
        return [leg.swimmer for leg in self.legs]

    def revert(self):
        for leg, sw in zip(self.legs, self.original_swimmers):
            leg.swimmer = sw


# event display order for the board
_EVENT_ORDER = {ev: i for i, ev in enumerate(RELAY_EVENTS)}
_GENDER_ORDER = {g: i for i, g in enumerate(GENDER_KEYS)}


def build_board(committed: dict, swimmers: list) -> list:
    """Turn the optimiser's committed dict into a list of EditableTeam, ordered
    for display (event, then gender, then age bracket)."""
    teams = []
    for (event, gender, age_cat), v in committed.items():
        team = v["team"]
        strokes = leg_strokes(event)
        # team.legs are already in leg-stroke order (medley) / time order (free);
        # align EditableLeg strokes to the fixed leg positions for this event.
        legs = [EditableLeg(stroke=strokes[i], swimmer=team.legs[i].swimmer)
                for i in range(4)]
        teams.append(EditableTeam(
            event=event, gender=gender, original_bracket=age_cat, legs=legs,
            original_swimmers=[leg.swimmer for leg in team.legs],
        ))
    teams.sort(key=lambda t: (_EVENT_ORDER.get(t.event, 99),
                              _GENDER_ORDER.get(t.gender, 99),
                              t.original_bracket))
    return teams


def board_snapshots(board: list, fetcher) -> list:
    """Evaluate every team and return (evals, snapshots) for conflict detection."""
    evals, snaps = [], []
    for t in board:
        ev = evaluate_team(t.current_swimmers(), t.event, t.gender, fetcher,
                           original_bracket=t.original_bracket)
        evals.append(ev)
        snaps.append(TeamSnapshot(t.event, t.gender, ev.age_category,
                                  t.current_swimmers()))
    return evals, snaps


def board_to_committed(board: list, fetcher) -> tuple:
    """Build a committed-style dict from the current board for Excel export.

    Returns (committed, skipped) where skipped counts teams left out because they
    were incomplete, had no valid bracket, or collided on (event, gender, bracket).
    """
    scorer = Scorer(fetcher)
    committed = {}
    skipped = 0
    for t in board:
        ev = evaluate_team(t.current_swimmers(), t.event, t.gender, fetcher,
                           original_bracket=t.original_bracket)
        if not ev.complete or ev.age_category is None:
            skipped += 1
            continue
        strokes = leg_strokes(t.event)
        team = RelayTeam(
            event=t.event, age_category=ev.age_category, gender=t.gender,
            legs=[RelayLeg(swimmer=t.legs[i].swimmer, stroke=strokes[i],
                           split_time=ev.splits[i]) for i in range(4)],
            total_time=ev.total_time,
        )
        key = (t.event, t.gender, ev.age_category)
        if key in committed:
            # bracket collision -- keep the faster team, skip the slower
            if team.total_time >= committed[key]["team"].total_time:
                skipped += 1
                continue
            skipped += 1
        committed[key] = {
            "team": team,
            "score": scorer.score(team),
            "records_broken": ev.broken_levels,
        }
    return committed, skipped


# ===========================================================================
# Tkinter app
# ===========================================================================

class RelayEditorApp:
    def __init__(self, root, swimmers, fetcher, *, course="long_course",
                 club="", allow_72plus=False, max_relays=None,
                 swimmers_path=None, load_swimmers_fn=None):
        self.root = root
        self.swimmers = swimmers
        self.fetcher = fetcher
        self.course = course
        self.club = club
        self.allow_72plus = allow_72plus
        self.max_relays = max_relays
        self.swimmers_path = swimmers_path
        self._load_swimmers_fn = load_swimmers_fn   # callable(path) -> list[Swimmer]

        self.committed = {}
        self.board = []
        self._fastest_cache = []   # cached fastest-per-event rows (recomputed on re-solve)

        root.title("Swimming Relay Optimiser")
        root.geometry("1080x780")
        self._build_toolbar()
        self._build_scroll_area()
        self._build_statusbar()

        if self.swimmers:
            self.run_optimisation()
        else:
            self._set_status("Load a swimmers file to begin.")

    # ---- layout scaffolding -------------------------------------------------

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="Load swimmers…", command=self.on_load).pack(side="left")

        ttk.Label(bar, text="   Course:").pack(side="left")
        self.course_var = tk.StringVar(
            value="Short course" if self.course == "short_course" else "Long course")
        cc = ttk.Combobox(bar, textvariable=self.course_var, width=13, state="readonly",
                          values=["Long course", "Short course"])
        cc.pack(side="left")
        cc.bind("<<ComboboxSelected>>", lambda e: self.on_course_change())

        self.x72_var = tk.BooleanVar(value=self.allow_72plus)
        ttk.Checkbutton(bar, text="72+ category", variable=self.x72_var,
                        command=self.on_72_toggle).pack(side="left", padx=(10, 0))

        ttk.Label(bar, text="   Club:").pack(side="left")
        self.club_var = tk.StringVar(value=self.club)
        ttk.Entry(bar, textvariable=self.club_var, width=18).pack(side="left")

        ttk.Button(bar, text="Re-run optimiser", command=self.on_reoptimise).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Undo edits", command=self.on_revert).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Export to Excel…", command=self.on_export).pack(side="right")

    def _build_scroll_area(self):
        container = ttk.Frame(self.root)
        container.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(container, highlightthickness=0, background="#F2F2F2")
        vbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas, padding=8)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._inner_id, width=e.width))
        # mouse wheel
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w", padding=(8, 3)).pack(side="bottom", fill="x")

    def _set_status(self, text):
        self.status_var.set(text)

    # ---- optimisation / data ------------------------------------------------

    def run_optimisation(self):
        config.ALLOW_72_PLUS_CATEGORY = self.allow_72plus
        if self.max_relays is not None:
            for s in self.swimmers:
                if s.max_relays is None:
                    s.max_relays = self.max_relays
        self.fetcher = RecordsFetcher(course=self.course)
        self.committed = optimiser.run(self.swimmers, self.fetcher)
        self.board = build_board(self.committed, self.swimmers)
        # Fastest-per-event reference ignores the one-relay rule and manual edits,
        # so it only changes when the pool / course / 72+ changes -- cache it.
        self._fastest_cache = list(
            reporter.fastest_reference_rows(self.swimmers, self.fetcher))
        self.render(preserve_scroll=False)

    def _has_edits(self) -> bool:
        return any(t.current_swimmers() != t.original_swimmers for t in self.board)

    # ---- toolbar handlers ---------------------------------------------------

    def on_load(self):
        if self._load_swimmers_fn is None:
            messagebox.showerror("Unavailable", "No swimmer loader is configured.")
            return
        path = filedialog.askopenfilename(
            title="Select swimmers file",
            filetypes=[("Swimmer data", "*.csv *.xlsx"), ("All files", "*.*")])
        if not path:
            return
        try:
            swimmers = self._load_swimmers_fn(path)
        except Exception as exc:  # noqa: BLE001 -- surface any load error to the user
            messagebox.showerror("Could not load file", str(exc))
            return
        if not swimmers:
            messagebox.showwarning("No swimmers", "No swimmers were loaded from that file.")
            return
        self.swimmers = swimmers
        self.swimmers_path = path
        self.run_optimisation()
        self._set_status(f"Loaded {len(swimmers)} swimmers from {os.path.basename(path)}.")

    def on_course_change(self):
        new = "short_course" if self.course_var.get() == "Short course" else "long_course"
        if new == self.course:
            return
        if self._has_edits() and not self._confirm_discard("change course"):
            # revert the dropdown
            self.course_var.set("Short course" if self.course == "short_course" else "Long course")
            return
        self.course = new
        if self.swimmers:
            self.run_optimisation()

    def on_72_toggle(self):
        if self._has_edits() and not self._confirm_discard("toggle the 72+ category"):
            self.x72_var.set(self.allow_72plus)
            return
        self.allow_72plus = self.x72_var.get()
        if self.swimmers:
            self.run_optimisation()

    def on_reoptimise(self):
        if self._has_edits() and not self._confirm_discard("re-run the optimiser"):
            return
        if self.swimmers:
            self.run_optimisation()
            self._set_status("Re-ran the optimiser.")

    def on_revert(self):
        for t in self.board:
            t.revert()
        self.render()
        self._set_status("Undid manual edits — back to the optimal plan.")

    def on_export(self):
        if not self.board:
            messagebox.showinfo("Nothing to export", "There are no teams to export yet.")
            return
        committed, skipped = board_to_committed(self.board, self.fetcher)
        if not committed:
            messagebox.showwarning("Nothing to export",
                                   "No complete, valid teams to export.")
            return
        default = "relay_plan.xlsx"
        path = filedialog.asksaveasfilename(
            title="Export to Excel", defaultextension=".xlsx",
            initialfile=default, filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        try:
            reporter.export_excel(committed, self.fetcher, path,
                                  club_name=self.club_var.get(), swimmers=self.swimmers)
        except PermissionError:
            messagebox.showerror("Could not save",
                                 "Could not write the file -- is it open in Excel?")
            return
        msg = f"Exported {len(committed)} teams to {os.path.basename(path)}."
        if skipped:
            msg += f"\n{skipped} incomplete/invalid/duplicate team(s) were skipped."
        messagebox.showinfo("Export complete", msg)
        self._set_status(msg.replace("\n", "  "))

    def _confirm_discard(self, action: str) -> bool:
        return messagebox.askyesno(
            "Discard manual edits?",
            f"You have manual changes. To {action} the plan must be rebuilt, "
            "discarding them.\n\nContinue?")

    # ---- rendering ----------------------------------------------------------

    def render(self, preserve_scroll=True):
        # Remember where the user was scrolled so an edit doesn't jump them away.
        scroll_pos = self.canvas.yview()[0] if preserve_scroll else 0.0
        for child in self.inner.winfo_children():
            child.destroy()

        evals, snaps = board_snapshots(self.board, self.fetcher)
        conflicts = detect_conflicts(snaps)
        leg_conflicts = conflicts["leg_conflicts"]
        bracket_collisions = conflicts["bracket_collisions"]

        n_breaks = sum(1 for ev in evals if ev.broken_levels)
        n_conf = len({ti for ti, _ in leg_conflicts}) + len(bracket_collisions)

        current_event = None
        current_gender = None
        for ti, (team, ev) in enumerate(zip(self.board, evals)):
            if team.event != current_event:
                current_event = team.event
                current_gender = None
                self._render_event_header(_EVENT_LABEL.get(team.event, team.event))
            if team.gender != current_gender:
                current_gender = team.gender
                self._render_gender_header(_GENDER_LABEL[team.gender])
            self._render_card(ti, team, ev, leg_conflicts, bracket_collisions)

        self._render_participation(evals)
        self._render_fastest_reference()

        edits = "  |  edited" if self._has_edits() else ""
        self._set_status(
            f"{len(self.board)} teams   •   {n_breaks} record-breaking   "
            f"•   {n_conf} flagged{edits}")
        # Recompute the scroll region for the rebuilt content, then restore position.
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(scroll_pos)

    def _card_colour(self, ti, ev, bracket_collisions, has_leg_conflict):
        if has_leg_conflict or ti in bracket_collisions or "no_valid_bracket" in ev.flags:
            return C_CONFLICT
        if "mixed_needs_2m2f" in ev.flags or "bracket_changed" in ev.flags \
                or "incomplete" in ev.flags:
            return C_WARN
        if ev.broken_levels:
            return C_BREAK
        return C_NEUTRAL

    def _render_card(self, ti, team, ev, leg_conflicts, bracket_collisions):
        has_leg_conflict = any(t == ti for t, _ in leg_conflicts)
        bg = self._card_colour(ti, ev, bracket_collisions, has_leg_conflict)

        card = tk.Frame(self.inner, bg=bg, highlightbackground=C_CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="x", pady=5, padx=2)

        # ---- header ----
        bracket = ev.age_category or team.original_bracket
        combined = sum(s.age for s in team.current_swimmers() if s is not None)
        title = (f"{_GENDER_LABEL[team.gender]} {_EVENT_LABEL.get(team.event, team.event)}"
                 f"  [{bracket}]   combined age {combined}")
        head = tk.Frame(card, bg=bg)
        head.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(head, text=title, bg=bg, font=("Segoe UI", 11, "bold"),
                 anchor="w").pack(side="left")

        # ---- record times + estimated time row ----
        #   British | European | World  (record time + signed delta)   ->  ESTIMATED
        recrow = tk.Frame(card, bg=bg)
        recrow.pack(fill="x", padx=8, pady=(2, 0))
        for lv in _LEVEL_DISPLAY_ORDER:
            self._level_cell(recrow, bg, lv, ev)
        # estimated time (big bold) with the record it breaks just to its left
        est = fmt_time(ev.total_time) if (ev.complete and ev.total_time is not None) else "—"
        tk.Label(recrow, text=est, bg=bg, font=("Segoe UI", 15, "bold"),
                 ).pack(side="right", padx=(8, 4))
        tk.Label(recrow, text="Estimated", bg=bg, fg=C_MUTED,
                 font=("Segoe UI", 9)).pack(side="right")
        if ev.broken_levels:
            top = ev.broken_levels[0]
            tk.Label(recrow, text=f"  breaks {_LEVEL_SHORT[top]} record  ", bg="#70AD47",
                     fg="white", font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 12))

        # ---- warnings line ----
        notes = []
        if "incomplete" in ev.flags:
            notes.append("incomplete")
        if "no_valid_bracket" in ev.flags:
            notes.append("no valid age bracket")
        if "mixed_needs_2m2f" in ev.flags:
            notes.append("mixed needs exactly 2M + 2F")
        if "bracket_changed" in ev.flags:
            notes.append(f"moved {team.original_bracket} → {ev.age_category}")
        if has_leg_conflict:
            notes.append("swimmer used twice in this event")
        if ti in bracket_collisions:
            notes.append("another team is in this same age group")
        if notes:
            tk.Label(card, text="⚠ " + "; ".join(notes), bg=bg, fg="#9C2A00",
                     font=("Segoe UI", 9, "italic"), anchor="w").pack(fill="x", padx=8)

        # ---- legs ----
        body = tk.Frame(card, bg=bg)
        body.pack(fill="x", padx=8, pady=(2, 8))
        for li, leg in enumerate(team.legs):
            self._render_leg(body, ti, li, team, leg, ev, (ti, li) in leg_conflicts)

    def _level_cell(self, parent, bg, level, ev):
        """One 'British 1:41.17 -0.40' cell; delta green if under, red if over."""
        rec = ev.records.get(level, {})
        rec_time = rec.get("record_time")
        cell = tk.Frame(parent, bg=bg)
        cell.pack(side="left", padx=(0, 16))
        tk.Label(cell, text=_LEVEL_SHORT[level], bg=bg, fg=C_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(cell, text=(fmt_time(rec_time) if rec_time is not None else "—"),
                 bg=bg, font=("Consolas", 10)).pack(side="left", padx=(4, 0))
        # signed delta: team_time - record_time. Negative = under (faster) = green.
        if ev.complete and ev.age_category is not None and rec_time is not None \
                and ev.total_time is not None:
            diff = ev.total_time - rec_time
            colour = C_UNDER if diff < 0 else C_OVER
            tk.Label(cell, text=f"{diff:+.2f}", bg=bg, fg=colour,
                     font=("Consolas", 10, "bold")).pack(side="left", padx=(4, 0))

    def _render_leg(self, parent, ti, li, team, leg, ev, is_conflict):
        rowbg = C_LEGBAD if is_conflict else parent["bg"]
        row = tk.Frame(parent, bg=rowbg)
        row.pack(fill="x", pady=1)

        # stroke label
        tk.Label(row, text=leg.stroke.capitalize(), width=8, anchor="w",
                 bg=rowbg, font=("Segoe UI", 10)).pack(side="left")

        # candidate dropdown
        cands = candidate_swimmers(self.swimmers, team.event, team.gender,
                                   leg.stroke, allow_72plus=self.allow_72plus)
        disp_to_sw = {BLANK_LABEL: None}
        values = [BLANK_LABEL]
        for s in cands:
            t = leg_split_time(s, team.event, team.gender, leg.stroke)
            label = f"{s.name}  ({s.age}{s.gender}, {fmt_split(t)})"
            disp_to_sw[label] = s
            values.append(label)
        # ensure current swimmer is shown even if filtered out
        cur_label = BLANK_LABEL
        if leg.swimmer is not None:
            t = leg_split_time(leg.swimmer, team.event, team.gender, leg.stroke)
            cur_label = f"{leg.swimmer.name}  ({leg.swimmer.age}{leg.swimmer.gender}, " \
                        f"{fmt_split(t) if t is not None else '--'})"
            if cur_label not in disp_to_sw:
                disp_to_sw[cur_label] = leg.swimmer
                values.insert(1, cur_label)

        var = tk.StringVar(value=cur_label)
        combo = ttk.Combobox(row, textvariable=var, values=values, state="readonly",
                             width=34)
        combo.pack(side="left", padx=(0, 6))

        def on_select(event=None, _li=li, _team=team, _map=disp_to_sw, _var=var):
            _team.legs[_li].swimmer = _map.get(_var.get())
            self.render()
        combo.bind("<<ComboboxSelected>>", on_select)

        # split time
        split = ev.splits[li]
        tk.Label(row, text=(fmt_split(split) if split is not None else "—"),
                 width=9, anchor="w", bg=rowbg, font=("Consolas", 10)).pack(side="left")

        # remove-to-blank button
        def on_remove(_li=li, _team=team):
            _team.legs[_li].swimmer = None
            self.render()
        ttk.Button(row, text="✕", width=3, command=on_remove).pack(side="left")

    # ---- swimmer participation (live) --------------------------------------

    def _render_participation(self, evals):
        """List every swimmer in the data and which relays they're currently in,
        including swimmers used in zero relays. Rebuilt on every edit."""
        # name -> list of slot labels (from the current board)
        used = {}
        for team, ev in zip(self.board, evals):
            bracket = ev.age_category or team.original_bracket
            label = (f"{_GENDER_LABEL[team.gender]} "
                     f"{_EVENT_LABEL.get(team.event, team.event)} [{bracket}]")
            for leg in team.legs:
                if leg.swimmer is not None:
                    used.setdefault(leg.swimmer.name, []).append(label)

        # include every swimmer in the data (so 0-count swimmers still appear)
        rows = []
        for s in self.swimmers:
            events = sorted(used.get(s.name, []))
            rows.append((s, events))
        # most-used first, then alphabetical
        rows.sort(key=lambda r: (-len(r[1]), r[0].name))

        panel = tk.Frame(self.inner, bg="#FFFFFF", highlightbackground=C_CARD_BORDER,
                         highlightthickness=1)
        panel.pack(fill="x", pady=(12, 6), padx=2)
        tk.Label(panel, text="Swimmer participation", bg="#D9E1F2",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")

        for s, events in rows:
            count = len(events)
            # "signed up" = distinct (event, gender) entries; multiple medley
            # strokes for the same relay are one entry, so len(entries) is correct.
            signed_up = len(s.entries)
            over_cap = s.max_relays is not None and count > s.max_relays
            rowbg = "#FFFFFF"
            line = tk.Frame(panel, bg=rowbg)
            line.pack(fill="x", padx=8, pady=1)
            tk.Label(line, text=f"{s.name}  ({s.age}{s.gender})", bg=rowbg,
                     font=("Segoe UI", 10), width=24, anchor="w").pack(side="left")
            tk.Label(line, text=f"{count} of {signed_up} signed up", bg=rowbg,
                     fg=("#000000" if count else C_MUTED),
                     font=("Segoe UI", 10, "bold"), width=16, anchor="w").pack(side="left")
            # max-relays cap shown as a small pill (red if exceeded)
            if s.max_relays is not None:
                tk.Label(line, text=f" max {s.max_relays} ",
                         bg=(C_OVER if over_cap else "#D9D9D9"),
                         fg=("white" if over_cap else "#333333"),
                         font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
            detail = ",  ".join(events) if events else "(not used)"
            tk.Label(line, text=detail, bg=rowbg,
                     fg=("#000000" if count else C_MUTED),
                     font=("Segoe UI", 9), anchor="w", justify="left").pack(side="left")

    # ---- event grouping header --------------------------------------------

    def _render_event_header(self, text):
        bar = tk.Frame(self.inner, bg=C_EVENT_HEAD)
        bar.pack(fill="x", pady=(12, 2), padx=2)
        tk.Label(bar, text=f"  {text}", bg=C_EVENT_HEAD, fg=C_EVENT_TEXT,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")

    def _render_gender_header(self, text):
        # Nested under the event bar: one relay per swimmer applies within this
        # (event, gender) block, so no name should repeat inside it.
        bar = tk.Frame(self.inner, bg=C_GENDER_HEAD)
        bar.pack(fill="x", pady=(4, 2), padx=(14, 2))
        tk.Label(bar, text=f"  {text}", bg=C_GENDER_HEAD, fg=C_GENDER_TEXT,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")

    # ---- fastest possible team per event (reference) ----------------------

    def _render_fastest_reference(self):
        """Best possible team for each event/gender/age in isolation (ignores the
        one-relay-per-swimmer rule), with green/red signed deltas per record."""
        if not self._fastest_cache:
            return
        panel = tk.Frame(self.inner, bg="#FFFFFF", highlightbackground=C_CARD_BORDER,
                         highlightthickness=1)
        panel.pack(fill="x", pady=(14, 8), padx=2)
        tk.Label(panel, text="Fastest possible team per event  (reference — ignores "
                             "the one-relay-per-swimmer rule)", bg="#D9E1F2",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")

        current_event = None
        for event, gender, age_cat, team, beaten, note in self._fastest_cache:
            if event != current_event:
                current_event = event
                tk.Label(panel, text=_EVENT_LABEL.get(event, event), bg="#FFFFFF",
                         fg=C_EVENT_HEAD, font=("Segoe UI", 10, "bold"),
                         anchor="w").pack(fill="x", padx=8, pady=(6, 0))

            row = tk.Frame(panel, bg="#FFFFFF")
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(row, text=f"{_GENDER_LABEL[gender]}  [{age_cat}]", bg="#FFFFFF",
                     font=("Segoe UI", 10), width=18, anchor="w").pack(side="left")
            tk.Label(row, text=team.format_time(), bg="#FFFFFF",
                     font=("Segoe UI", 11, "bold"), width=9, anchor="w").pack(side="left")
            for lvl in _LEVEL_DISPLAY_ORDER:
                rec = self.fetcher.get_record(lvl, event, age_cat, gender)
                cell = tk.Frame(row, bg="#FFFFFF")
                cell.pack(side="left", padx=(0, 12))
                tk.Label(cell, text=_LEVEL_SHORT[lvl], bg="#FFFFFF", fg=C_MUTED,
                         font=("Segoe UI", 8)).pack(side="left")
                if rec is not None:
                    diff = team.total_time - rec.time   # -ve = under (faster)
                    tk.Label(cell, text=f"{diff:+.2f}", bg="#FFFFFF",
                             fg=(C_UNDER if diff < 0 else C_OVER),
                             font=("Consolas", 9, "bold")).pack(side="left", padx=(3, 0))
                else:
                    tk.Label(cell, text="—", bg="#FFFFFF", fg=C_MUTED,
                             font=("Consolas", 9)).pack(side="left", padx=(3, 0))
            names = ", ".join(leg.swimmer.name for leg in team.legs)
            tk.Label(row, text=names, bg="#FFFFFF", fg="#333333",
                     font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(6, 0))


def launch_gui(swimmers, fetcher, *, course="long_course", club="",
               allow_72plus=False, max_relays=None, swimmers_path=None,
               load_swimmers_fn=None):
    """Open the editor window and run the Tk main loop."""
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")   # nicer on Windows; fall back silently
    except tk.TclError:
        pass
    RelayEditorApp(root, swimmers, fetcher, course=course, club=club,
                   allow_72plus=allow_72plus, max_relays=max_relays,
                   swimmers_path=swimmers_path, load_swimmers_fn=load_swimmers_fn)
    root.mainloop()
