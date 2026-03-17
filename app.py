import itertools
import random
from typing import List

import streamlit as st


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


def reset_all() -> None:
    st.session_state.step = 1
    st.session_state.participants_raw = ""
    st.session_state.participants = []
    st.session_state.teams = []
    st.session_state.groups = []


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
    all_matches: List[dict] = []

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
        round_num = 1

        for _ in range(num_rounds):
            round_pairs = []
            for i in range(n // 2):
                a = current[i]
                b = current[n - 1 - i]
                if a == -1 or b == -1:
                    continue
                round_pairs.append((a, b))

            for match_index, (a_idx, b_idx) in enumerate(round_pairs, start=1):
                team_a = " & ".join(group[a_idx])
                team_b = " & ".join(group[b_idx])
                all_matches.append(
                    {
                        "Round": round_num,
                        "Group": f"Group {gi}",
                        "Match #": match_index,
                        "Team A": team_a,
                        "Team B": team_b,
                    }
                )

            # Rotate teams for next round (circle method)
            fixed = current[0]
            rest = current[1:]
            rest = [rest[-1], *rest[:-1]]
            current = [fixed, *rest]
            round_num += 1

    # Sort by round then group for a clean global schedule
    all_matches.sort(key=lambda m: (m["Round"], m["Group"], m["Match #"]))
    return all_matches


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
    st.caption(
        "Paste or type one participant per line, or separate names with commas. "
        "Teams of two will be created automatically."
    )

    with st.form("participants_form"):
        participants_raw = st.text_area(
            "Player names",
            value=st.session_state.participants_raw,
            height=200,
            placeholder="Example:\nAlex\nJordan\nSam\nPriya\n...",
        )
        submitted = st.form_submit_button("Create teams")

    if submitted:
        participants = parse_participants(participants_raw)
        st.session_state.participants_raw = participants_raw
        st.session_state.participants = participants
        st.session_state.teams = create_teams(participants)
        st.session_state.groups = []

        if not participants:
            st.warning("Please enter at least two participant names.")
            return

        if len(participants) < 2:
            st.warning("You need at least 2 participants to form a team.")
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
    st.caption("These are the randomly generated doubles teams from your participant list.")

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
        if st.button("Create groups"):
            shuffled_teams = st.session_state.teams[:]
            random.shuffle(shuffled_teams)
            st.session_state.teams = shuffled_teams
            st.session_state.groups = create_groups(shuffled_teams, num_groups=4)
            st.session_state.step = 3
            st.rerun()


def page_groups() -> None:
    if not st.session_state.teams:
        st.info("No teams found yet. Please create teams first.")
        st.session_state.step = 1
        st.rerun()

    st.subheader("Step 3 · Group teams")
    st.caption("Teams are divided into exactly **4 groups** (as evenly as possible).")

    # Use existing groups if already created; otherwise create once
    if st.session_state.groups:
        groups = st.session_state.groups
    else:
        num_groups = 4
        groups = create_groups(st.session_state.teams, num_groups=num_groups)
        st.session_state.groups = groups

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
            st.session_state.teams = shuffled_teams
            st.session_state.groups = create_groups(shuffled_teams, num_groups=4)
        else:
            st.info("No groups defined yet. Please start by entering participants.")
            st.session_state.step = 1
            st.rerun()

    st.subheader("Step 4 · Round 1 schedule")
    st.caption("Each group plays a full round-robin: every team faces every other team in its group once.")

    schedule = create_round_robin_schedule(st.session_state.groups)
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


if __name__ == "__main__":
    main()

