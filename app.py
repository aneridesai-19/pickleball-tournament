import itertools
import random
from typing import List
import json
from pathlib import Path

import streamlit as st
import pandas as pd
STATE_FILE = Path(__file__).with_name(".tournament_state.json")


import io

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except Exception:  # pragma: no cover
    # If reportlab isn't installed yet, PDF export will be disabled gracefully.
    colors = None  # type: ignore[assignment]
    landscape = letter = None  # type: ignore[assignment]
    getSampleStyleSheet = None  # type: ignore[assignment]
    Paragraph = SimpleDocTemplate = Spacer = Table = TableStyle = None  # type: ignore[assignment]


def init_session_state() -> None:
    if "step" not in st.session_state:
        st.session_state.step = 1
    if "participants_raw" not in st.session_state:
        st.session_state.participants_raw = ""
    if "participants" not in st.session_state:
        st.session_state.participants: List[str] = []
    if "teams" not in st.session_state:
        st.session_state.teams: List[List[str]] = []
    if "groups" not in st.session_state:
        st.session_state.groups: List[List[List[str]]] = []
    if "schedule" not in st.session_state:
        st.session_state.schedule: List[dict] = []
    if "state_loaded" not in st.session_state:
        st.session_state.state_loaded = False

    # Restore persisted app state once per Streamlit session.
    if not st.session_state.state_loaded:
        load_persisted_state()
        st.session_state.state_loaded = True


def reset_all() -> None:
    st.session_state.step = 1
    st.session_state.participants_raw = ""
    st.session_state.participants = []
    st.session_state.teams = []
    st.session_state.groups = []
    st.session_state.schedule = []
    clear_persisted_state()


def load_persisted_state() -> None:
    if not STATE_FILE.exists():
        return

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    st.session_state.step = data.get("step", 1)
    st.session_state.participants_raw = data.get("participants_raw", "")
    st.session_state.participants = data.get("participants", [])
    st.session_state.teams = data.get("teams", [])
    st.session_state.groups = data.get("groups", [])
    st.session_state.schedule = data.get("schedule", [])


def save_persisted_state() -> None:
    data = {
        "step": st.session_state.get("step", 1),
        "participants_raw": st.session_state.get("participants_raw", ""),
        "participants": st.session_state.get("participants", []),
        "teams": st.session_state.get("teams", []),
        "groups": st.session_state.get("groups", []),
        "schedule": st.session_state.get("schedule", []),
    }
    try:
        STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        # Best-effort persistence; app should still work without filesystem access.
        pass


def clear_persisted_state() -> None:
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except Exception:
        pass


def parse_participants(raw: str) -> List[str]:
    # Split on newlines or commas and strip whitespace
    if not raw:
        return []
    tokens = []
    for line in raw.splitlines():
        for part in line.replace(";", ",").split(","):
            name = part.strip()
            if name:
                tokens.append(name)
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for name in tokens:
        if name.lower() not in seen:
            seen.add(name.lower())
            unique.append(name)
    return unique


def parse_participants_from_excel(uploaded_file) -> List[str]:
    if uploaded_file is None:
        return []

    df = pd.read_excel(uploaded_file)
    if df.empty:
        return []

    # Use first non-empty column as participant names
    target_col = None
    for col in df.columns:
        if df[col].notna().any():
            target_col = col
            break
    if target_col is None:
        return []

    seen = set()
    participants = []
    for value in df[target_col].tolist():
        if pd.isna(value):
            continue
        name = str(value).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        participants.append(name)
    return participants


def create_teams(participants: List[str]) -> List[List[str]]:
    # Shuffle participants so team pairings are random each time
    shuffled = participants[:]
    random.shuffle(shuffled)

    teams: List[List[str]] = []
    i = 0
    n = len(shuffled)
    while i + 1 < n:
        teams.append([shuffled[i], shuffled[i + 1]])
        i += 2
    # If odd number of players, keep last one as a single-member team
    if i < n:
        teams.append([shuffled[i]])
    return teams


def create_groups(teams: List[List[str]], num_groups: int = 4) -> List[List[List[str]]]:
    """
    Split teams into a fixed number of groups (default 3),
    distributing them as evenly as possible.
    """
    if num_groups <= 0:
        return [teams]

    groups: List[List[List[str]]] = [[] for _ in range(num_groups)]
    for idx, team in enumerate(teams):
        groups[idx % num_groups].append(team)
    # Remove any empty trailing groups if there were fewer teams
    groups = [g for g in groups if g]
    return groups


def create_round_robin_schedule(groups: List[List[List[str]]]) -> List[dict]:
    """
    Build a round-robin schedule per group so that
    no team has two consecutive matches in time.

    We generate proper "rounds" (time slots) inside each group where
    each team appears at most once per round, then flatten by round.
    """
    def slot_to_time(slot_num: int, start_hour: int = 12, start_minute: int = 0, interval_minutes: int = 30) -> str:
        total_minutes = start_hour * 60 + start_minute + slot_num * interval_minutes
        hour_24 = (total_minutes // 60) % 24
        minute = total_minutes % 60
        ampm = "AM" if hour_24 < 12 else "PM"
        hour_12 = hour_24 % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{minute:02d} {ampm}"

    all_matches: List[dict] = []
    group_matches_map: dict[int, List[dict]] = {}

    for gi, group in enumerate(groups, start=1):
        team_indices = list(range(len(group)))
        if len(team_indices) < 2:
            continue

        # For odd team counts, add a dummy "bye" so algorithm works cleanly.
        has_bye = False
        if len(team_indices) % 2 == 1:
            team_indices.append(-1)
            has_bye = True

        n = len(team_indices)
        num_rounds = n - 1

        current = team_indices[:]
        group_match_rows: List[dict] = []

        for _ in range(num_rounds):
            round_pairs = []
            for i in range(n // 2):
                a = current[i]
                b = current[n - 1 - i]
                if a == -1 or b == -1:
                    continue
                round_pairs.append((a, b))

            for _, (a_idx, b_idx) in enumerate(round_pairs, start=1):
                team_a = " & ".join(group[a_idx])
                team_b = " & ".join(group[b_idx])
                group_match_rows.append(
                    {
                        "Round": "Round 1",
                        "Group": f"Group {gi}",
                        "Team A": team_a,
                        "Team B": team_b,
                    }
                )

            # Rotate teams for next round (circle method)
            fixed = current[0]
            rest = current[1:]
            rest = [rest[-1], *rest[:-1]]
            current = [fixed, *rest]
        group_matches_map[gi] = group_match_rows

    # Fixed-court queues:
    # - Court 1 queue interleaves Group 1 and Group 2 matches.
    # - Court 2 queue interleaves Group 3 and Group 4 matches.
    # This preserves "each group plays only within its own group"
    # and ensures no group match gets dropped.
    court1_queue: List[dict] = []
    court2_queue: List[dict] = []

    for i in range(max(len(group_matches_map.get(1, [])), len(group_matches_map.get(2, [])))):
        if i < len(group_matches_map.get(1, [])):
            court1_queue.append(group_matches_map[1][i])
        if i < len(group_matches_map.get(2, [])):
            court1_queue.append(group_matches_map[2][i])

    for i in range(max(len(group_matches_map.get(3, [])), len(group_matches_map.get(4, [])))):
        if i < len(group_matches_map.get(3, [])):
            court2_queue.append(group_matches_map[3][i])
        if i < len(group_matches_map.get(4, [])):
            court2_queue.append(group_matches_map[4][i])

    total_slots = max(len(court1_queue), len(court2_queue))
    for slot_num in range(total_slots):
        time_label = slot_to_time(slot_num)

        if slot_num < len(court1_queue):
            row_c1 = court1_queue[slot_num]
            row_c1["Match Time"] = time_label
            row_c1["Court"] = "Court 1"
            all_matches.append(row_c1)

        if slot_num < len(court2_queue):
            row_c2 = court2_queue[slot_num]
            row_c2["Match Time"] = time_label
            row_c2["Court"] = "Court 2"
            all_matches.append(row_c2)

    return all_matches


def create_full_schedule(groups: List[List[List[str]]]) -> List[dict]:
    """
    Full Round 1 schedule including intra-group round-robin,
    followed by semi-finals and final (group-winner placeholders).
    """
    schedule = create_round_robin_schedule(groups)

    # Semi-finals and final are fixed at 4:00pm and 4:30pm respectively.
    # We assume 4 groups (as per the UI). If fewer groups exist,
    # we still show the placeholders for missing groups.
    group_count = len(groups)

    def winner_text(gi: int) -> str:
        # gi is 1-based
        return f"Group {gi} winner"

    # Semi-final 1: Group 1 winner vs Group 2 winner (4:00 PM)
    schedule.append(
        {
            "Round": "Semi-final1",
            "Match Time": "4:00 PM",
            "Group": "",
            "Court": "Court 1",
            "Team A": winner_text(1),
            "Team B": winner_text(2),
        }
    )

    # Semi-final 2: Group 3 winner vs Group 4 winner (4:00 PM)
    schedule.append(
        {
            "Round": "Semi-final2",
            "Match Time": "4:00 PM",
            "Group": "",
            "Court": "Court 2",
            "Team A": winner_text(3),
            "Team B": winner_text(4),
        }
    )

    # Final: Semi-final 1 winner vs Semi-final 2 winner (4:30 PM)
    schedule.append(
        {
            "Round": "Final",
            "Match Time": "4:30 PM",
            "Group": "",
            "Court": "Court 1",
            "Team A": "Semi-final1 winner",
            "Team B": "Semi-final2 winner",
        }
    )

    # Add 1-based index as the first column.
    schedule = [{"Index": i, **row} for i, row in enumerate(schedule, start=1)]

    return schedule


def apply_custom_theme() -> None:
    # Black and green theme via custom CSS
    st.markdown(
        """
        <style>
        :root {
            --primary-green: #00ff7f;
            --accent-green: #00c06a;
            --bg-dark: #050608;
            --bg-card: #111418;
            --text-main: #f5f7fa;
            --text-muted: #9ca3af;
        }

        .stApp {
            background: radial-gradient(circle at top left, #10141a 0, #020306 40%, #000000 100%);
            color: var(--text-main);
        }

        /* Remove default white top bar / header */
        header[data-testid="stHeader"] {
            background: linear-gradient(90deg, #020617, #020617) !important;
            box-shadow: none !important;
        }
        header[data-testid="stHeader"] * {
            color: var(--text-main) !important;
        }

        /* Hide generic top progress / status bar block */
        div[role="progressbar"] {
            display: none !important;
        }

        /* Global text color overrides */
        [data-testid="block-container"] {
            color: var(--text-main);
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, #020617, #020617 40%, #000000 100%);
            border-right: 1px solid rgba(15, 23, 42, 0.9);
        }
        section[data-testid="stSidebar"] * {
            color: var(--text-main) !important;
        }

        h1, h2, h3 {
            color: var(--primary-green) !important;
        }

        .step-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.3rem 0.75rem;
            border-radius: 999px;
            border: 1px solid rgba(0, 255, 127, 0.4);
            background: linear-gradient(90deg, rgba(0, 255, 127, 0.07), rgba(0, 255, 127, 0.02));
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
        }

        .step-badge-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--primary-green);
            box-shadow: 0 0 10px rgba(0, 255, 127, 0.7);
        }

        .card {
            background: radial-gradient(circle at top left, #1a222f, #050608);
            border-radius: 18px;
            padding: 1.2rem 1.3rem;
            border: 1px solid rgba(148, 163, 184, 0.35);
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
        }

        .card h3 {
            margin-top: 0.2rem;
            margin-bottom: 0.5rem;
        }

        .stat-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(148, 163, 184, 0.35);
            font-size: 0.72rem;
            color: var(--text-muted);
        }

        .stat-dot {
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: var(--accent-green);
        }

        .team-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(148, 163, 184, 0.4);
            font-size: 0.75rem;
            color: var(--text-main);
        }

        div[data-testid="stForm"] {
            background: transparent;
        }

        /* Buttons (all buttons share same style) */
        button,
        .stButton>button,
        form button,
        button[kind],
        button[data-testid],
        div[role="button"] > button {
            border-radius: 999px !important;
            border: none !important;
            padding: 0.45rem 1.4rem !important;
            background: linear-gradient(135deg, #00ff7f, #00c06a) !important;
            color: #020617 !important;
            font-weight: 600 !important;
            letter-spacing: 0.03em !important;
            box-shadow: 0 12px 25px rgba(0, 255, 127, 0.4) !important;
        }
        button:hover,
        .stButton>button:hover,
        form button:hover,
        div[role="button"] > button:hover {
            filter: brightness(1.05) !important;
            box-shadow: 0 16px 32px rgba(0, 255, 127, 0.55) !important;
        }

        /* Tables */
        .stDataFrame, .stTable {
            border-radius: 14px;
            overflow: hidden;
            background-color: #020617 !important;
            color: var(--text-main) !important;
        }

        /* Inputs: text, text area, select */
        textarea, input, select {
            background-color: #020617 !important;
            color: var(--text-main) !important;
            border-radius: 0.6rem !important;
            border: 1px solid rgba(148, 163, 184, 0.5) !important;
        }
        textarea::placeholder, input::placeholder {
            color: var(--text-muted) !important;
        }
        /* Field labels like "Player names" */
        label, label p, label span {
            color: var(--text-main) !important;
        }

        /* Table / dataframe theme */
        .stDataFrame [role="grid"],
        .stTable table {
            background-color: #020617 !important;
            color: var(--text-main) !important;
        }
        .stDataFrame [role="columnheader"],
        .stDataFrame [role="rowheader"],
        .stTable thead tr th {
            background-color: #020617 !important;
            color: var(--primary-green) !important;
            border-bottom: 1px solid rgba(148, 163, 184, 0.4) !important;
        }
        .stDataFrame [role="cell"],
        .stTable tbody tr td {
            color: var(--text-main) !important;
            border-bottom: 1px solid rgba(30, 41, 59, 0.8) !important;
        }

        /* Markdown lists */
        ul, ol {
            color: var(--text-main);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:0.75rem;">
            <div>
                <h1 style="margin:0;">Pickleball Match Scheduler</h1>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### Tournament steps")
        current = st.session_state.step
        steps = [
            (1, "Enter participants"),
            (2, "View teams"),
            (3, "Create groups"),
            (4, "Round 1 schedule"),
        ]
        for idx, label in steps:
            status = "✅" if current > idx else ("🟢" if current == idx else "⚪")
            st.write(f"{status} Step {idx}: {label}")

        st.markdown("---")
        if st.button("Clear & start over", use_container_width=True):
            reset_all()
            st.rerun()


def page_enter_participants() -> None:
    st.subheader("Step 1 · Enter participants")
    st.caption("Upload an Excel sheet with participant names in one column.")

    with st.form("participants_form"):
        uploaded_file = st.file_uploader(
            "Upload participants Excel file",
            type=["xlsx", "xls"],
            help="First non-empty column will be used as participant names.",
        )
        submitted = st.form_submit_button("Create teams")

    if submitted:
        participants = parse_participants_from_excel(uploaded_file)
        st.session_state.participants_raw = ""
        st.session_state.participants = participants
        st.session_state.teams = create_teams(participants)
        st.session_state.groups = []
        st.session_state.schedule = []

        if not participants:
            st.warning("Please upload a valid Excel file with at least two participant names.")
            return

        if len(participants) < 2:
            st.warning("You need at least 2 participants in the Excel file to form a team.")
            return

        # Move to teams screen where pairs are shown
        st.session_state.step = 2
        st.rerun()


def page_teams() -> None:
    if not st.session_state.teams:
        st.info("No teams found yet. Please create teams first.")
        st.session_state.step = 1
        st.rerun()

    st.subheader("Step 2 · Teams")

    teams = st.session_state.teams
    with st.container():
        cols = st.columns(2)
        with cols[0]:
            st.markdown(
                f'<div class="stat-chip"><span class="stat-dot"></span>'
                f"{len(st.session_state.participants)} players</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(
                f'<div style="text-align:right;" class="stat-chip"><span class="stat-dot"></span>'
                f"{len(teams)} teams</div>",
                unsafe_allow_html=True,
            )

        st.write("")
        for idx, team in enumerate(teams, start=1):
            team_label = " & ".join(team)
            solo_note = " (single player, will still be scheduled)" if len(team) == 1 else ""
            st.markdown(f"- **Team {idx}:** {team_label}{solo_note}")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("⬅ Back to participants"):
            st.session_state.step = 1
            st.rerun()
    with col_next:
        if st.session_state.groups:
            # Groups are already created; keep them stable across navigation.
            if st.button("View groups"):
                st.session_state.step = 3
                st.rerun()
        else:
            if st.button("Create groups"):
                shuffled_teams = st.session_state.teams[:]
                random.shuffle(shuffled_teams)
                st.session_state.groups = create_groups(shuffled_teams, num_groups=4)
                # New groups -> new schedule is required
                st.session_state.schedule = []
                st.session_state.step = 3
                st.rerun()


def page_groups() -> None:
    if not st.session_state.teams:
        st.info("No teams found yet. Please create teams first.")
        st.session_state.step = 1
        st.rerun()

    st.subheader("Step 3 · Group teams")

    # Use existing groups if already created; otherwise create once
    if st.session_state.groups:
        groups = st.session_state.groups
    else:
        num_groups = 4
        shuffled_teams = st.session_state.teams[:]
        random.shuffle(shuffled_teams)
        groups = create_groups(shuffled_teams, num_groups=num_groups)
        st.session_state.groups = groups
        # New groups -> new schedule is required
        st.session_state.schedule = []

    total_groups = len(groups)
    st.markdown(
        f'<div class="stat-chip"><span class="stat-dot"></span>'
        f"{len(st.session_state.teams)} teams → {total_groups} groups</div>",
        unsafe_allow_html=True,
    )

    for gi, group in enumerate(groups, start=1):
        st.markdown(f"#### Group {gi}")
        for ti, team in enumerate(group, start=1):
            team_label = " & ".join(team)
            st.markdown(f"- **Team {ti}:** {team_label}")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("⬅ Back to teams"):
            st.session_state.step = 2
            st.rerun()
    with col_next:
        if st.button("View Round 1 schedule"):
            st.session_state.step = 4
            st.rerun()


def page_schedule() -> None:
    if not st.session_state.groups:
        if st.session_state.teams:
            # If groups were not explicitly created yet, create them once (randomized)
            shuffled_teams = st.session_state.teams[:]
            random.shuffle(shuffled_teams)
            st.session_state.groups = create_groups(shuffled_teams, num_groups=4)
            st.session_state.schedule = []
        else:
            st.info("No groups defined yet. Please start by entering participants.")
            st.session_state.step = 1
            st.rerun()

    st.subheader("Step 4 · Tournament schedule (Round 1 + Knockouts)")

    if (
        not st.session_state.schedule
        or "Index" not in (st.session_state.schedule[0] if st.session_state.schedule else {})
        or "Court" not in (st.session_state.schedule[0] if st.session_state.schedule else {})
        or not any(str(row.get("Round", "")).startswith("Semi-final") for row in st.session_state.schedule)
    ):
        st.session_state.schedule = create_full_schedule(st.session_state.groups)

    schedule = st.session_state.schedule
    if not schedule:
        st.warning("Not enough teams to generate any matches.")
        return

    st.markdown(
        f'<div class="stat-chip"><span class="stat-dot"></span>'
        f"{len(schedule)} matches scheduled across {len(st.session_state.groups)} groups</div>",
        unsafe_allow_html=True,
    )

    # Show schedule as a themed table without extra empty lines
    st.table(schedule)

    # Export as PDF
    if colors is None:
        st.info("Install `reportlab` to enable PDF export.")
    else:
        def build_pdf_bytes(teams_rows: List[List[str]], groups_rows: List[List[List[str]]], schedule_rows: List[dict]) -> bytes:
            # Column order for schedule section
            schedule_columns = ["Index", "Round", "Match Time", "Court", "Group", "Team A", "Team B"]

            styles = getSampleStyleSheet()
            header_style = styles["Heading4"]
            header_style.textColor = colors.black
            header_style.fontName = "Helvetica-Bold"

            cell_style = styles["BodyText"]
            cell_style.fontSize = 8
            cell_style.leading = 9
            cell_style.textColor = colors.black
            cell_style.spaceAfter = 0

            def esc(text: str) -> str:
                # ReportLab Paragraph supports a small subset of HTML-like tags.
                # Escape special characters so team names like "A & B" render safely.
                return (
                    text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )

            def make_table(data_rows: List[List[Paragraph]], col_widths: List[int]) -> Table:
                table = Table(data_rows, colWidths=col_widths, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                            ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                            ("LEFTPADDING", (0, 0), (-1, -1), 3),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                            ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]
                    )
                )
                return table

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=landscape(letter),
                leftMargin=18,
                rightMargin=18,
                topMargin=18,
                bottomMargin=18,
            )

            elements = []

            # Section 1: Teams
            elements.append(Paragraph("Team List", header_style))
            team_data: List[List[Paragraph]] = [[Paragraph("Team", header_style), Paragraph("Members", header_style)]]
            for idx, team in enumerate(teams_rows, start=1):
                team_data.append(
                    [
                        Paragraph(esc(f"Team {idx}"), cell_style),
                        Paragraph(esc(" & ".join(team)), cell_style),
                    ]
                )
            elements.append(make_table(team_data, [90, 568]))
            elements.append(Spacer(1, 12))

            # Section 2: Groups
            elements.append(Paragraph("Group List", header_style))
            group_data: List[List[Paragraph]] = [[Paragraph("Group", header_style), Paragraph("Teams", header_style)]]
            for gi, group in enumerate(groups_rows, start=1):
                teams_text = ", ".join([" & ".join(team) for team in group])
                group_data.append(
                    [
                        Paragraph(esc(f"Group {gi}"), cell_style),
                        Paragraph(esc(teams_text), cell_style),
                    ]
                )
            elements.append(make_table(group_data, [90, 568]))
            elements.append(Spacer(1, 12))

            # Section 3: Match schedule
            elements.append(Paragraph("Match Schedule", header_style))
            schedule_data: List[List[Paragraph]] = [[Paragraph(col, header_style) for col in schedule_columns]]
            for row in schedule_rows:
                schedule_data.append([Paragraph(esc(str(row.get(col, ""))), cell_style) for col in schedule_columns])
            elements.append(make_table(schedule_data, [30, 62, 70, 48, 58, 190, 190]))

            doc.build(elements)
            return buffer.getvalue()

        pdf_bytes = build_pdf_bytes(st.session_state.teams, st.session_state.groups, schedule)
        st.download_button(
            label="Export schedule PDF",
            data=pdf_bytes,
            file_name="pickleball_round1_schedule.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    col_back, col_clear = st.columns(2)
    with col_back:
        if st.button("⬅ Back to groups"):
            st.session_state.step = 3
            st.rerun()
    with col_clear:
        if st.button("Clear tournament & restart"):
            reset_all()
            st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Pickleball Tournament Scheduler",
        page_icon="🎾",
        layout="wide",
    )

    init_session_state()
    apply_custom_theme()
    render_sidebar()
    render_header()

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    step = st.session_state.step
    if step == 1:
        page_enter_participants()
    elif step == 2:
        page_teams()
    elif step == 3:
        page_groups()
    else:
        page_schedule()
    st.markdown("</div>", unsafe_allow_html=True)

    # Persist current state so browser refresh keeps progress.
    save_persisted_state()


if __name__ == "__main__":
    main()

