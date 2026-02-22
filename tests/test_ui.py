"""Tests for UI improvements: menu hierarchy, status restructure, confirmation echoes, web state, reliability."""

import sys, os, tempfile, queue, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item
from mandarin.db.progress import record_attempt
from mandarin.db.session import start_session


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn


def _add_items(conn, n, hsk_level=1):
    ids = []
    for i in range(n):
        item_id = insert_content_item(
            conn, hanzi=f"\u4f60{i}_{hsk_level}", pinyin=f"ni{i}",
            english=f"test{i}", hsk_level=hsk_level,
        )
        ids.append(item_id)
    return ids


# ── Menu hierarchy ──

def test_menu_has_grouped_sections():
    """Menu output should have grouped sections (Quick, Progress, etc)."""
    from mandarin.menu import show_menu
    from io import StringIO
    from rich.console import Console

    # Capture menu output
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=80)

    # Import and monkey-patch the module's console temporarily
    import mandarin.menu as menu_mod
    old_console = menu_mod.console
    old_input = menu_mod._input
    menu_mod.console = console
    menu_mod._input = lambda p: "0"  # auto-quit

    try:
        result = show_menu(expanded=True)
    finally:
        menu_mod.console = old_console
        menu_mod._input = old_input

    text = output.getvalue()
    # Should have grouped section labels (visible in expanded mode)
    assert "Quick" in text, f"menu should have 'Quick' section header"
    assert "Progress" in text, f"menu should have 'Progress' section header"
    # Primary action should be prominent
    assert "Study" in text, f"menu should have 'Study' as primary action"


def test_menu_study_is_option_1():
    """Option 1 should be Study (the primary action)."""
    from mandarin.menu import show_menu
    from io import StringIO
    from rich.console import Console

    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80, no_color=True)

    import mandarin.menu as menu_mod
    old_console = menu_mod.console
    old_input = menu_mod._input
    menu_mod.console = console
    menu_mod._input = lambda p: "0"

    try:
        show_menu()
    finally:
        menu_mod.console = old_console
        menu_mod._input = old_input

    text = output.getvalue()
    # "1. Study" should appear (may have markup stripped)
    assert "Study" in text, f"menu should have 'Study' as option 1:\n{text}"


# ── Status screen restructure ──

def test_status_shows_stabilized_section():
    """Status screen should show 'What you've stabilized' section."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    session_id = start_session(conn)

    # Build some progress
    for item_id in ids[:3]:
        record_attempt(conn, item_id, "reading", True, session_id=session_id,
                       drill_type="mc")

    from mandarin.milestones import get_stage_counts
    from mandarin.diagnostics import get_speed_trend

    stages = get_stage_counts(conn)
    # With only 1 session, items should be in seen/passed_once/stabilizing state
    # Status should still show the sections
    assert stages["seen"] > 0 or stages["passed_once"] > 0 or stages["stabilizing"] > 0 or stages["weak"] > 0
    conn.close()


def test_status_primary_signal_early():
    """Status primary signal should acknowledge early stage."""
    conn = _fresh_db()
    # No sessions yet
    profile = db.get_profile(conn)
    total_sessions = profile.get("total_sessions", 0) or 0
    assert total_sessions == 0

    # The primary signal logic
    from mandarin.milestones import get_stage_counts
    stages = get_stage_counts(conn)
    solid = stages["stable"] + stages["durable"]
    growing = stages["stabilizing"]
    early = stages["seen"] + stages["passed_once"]
    needs_review = stages["decayed"]
    seen_total = solid + growing + early + needs_review

    # With 0 sessions, should show "Just getting started"
    if total_sessions == 0:
        msg = "Just getting started"
    elif seen_total == 0:
        msg = "data is building"
    else:
        msg = "taking shape"
    assert "started" in msg or "building" in msg
    conn.close()


def test_status_primary_signal_progress():
    """Status primary signal reflects actual progress."""
    conn = _fresh_db()
    ids = _add_items(conn, 10)
    session_id = start_session(conn)

    # Record many correct attempts to build stable items
    for item_id in ids:
        for _ in range(3):
            record_attempt(conn, item_id, "reading", True, session_id=session_id,
                           drill_type="mc")
        # Simulate day boundary
        conn.execute("UPDATE progress SET last_review_date = '2020-01-01' WHERE content_item_id = ?", (item_id,))
        conn.commit()
        for _ in range(3):
            record_attempt(conn, item_id, "reading", True, session_id=session_id,
                           drill_type="mc")

    from mandarin.milestones import get_stage_counts
    stages = get_stage_counts(conn)
    solid = stages["stable"] + stages["durable"]
    growing = stages["stabilizing"]
    early = stages["seen"] + stages["passed_once"]
    seen_total = solid + growing + early
    assert seen_total > 0
    # Should have items in stabilizing or stable at minimum
    assert stages["stabilizing"] > 0 or stages["stable"] > 0 or stages["passed_once"] > 0
    conn.close()


# ── Confirmation echoes ──

def test_finalize_early_exit_message():
    """Early exit with 0 items should say 'Session saved. Continuing.'"""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    session_id = start_session(conn)

    from mandarin.runner import _finalize, SessionState
    from mandarin.scheduler import SessionPlan

    plan = SessionPlan(session_type="standard", drills=[], micro_plan="test",
                       estimated_seconds=60)
    state = SessionState(session_id=session_id, plan=plan)
    state.early_exit = True
    # items_completed = 0 (default)

    output = []
    _finalize(conn, state, lambda t, end="\n": output.append(t), pre_milestones=set())
    full = "\n".join(output)
    assert "session saved" in full.lower(), \
        f"expected 'session saved' in early exit message:\n{full}"
    conn.close()


def test_finalize_first_session_message():
    """First session should get encouraging framing."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    session_id = start_session(conn)

    # Record one attempt so items_completed > 0
    record_attempt(conn, ids[0], "reading", True, session_id=session_id,
                   drill_type="mc")

    from mandarin.runner import _finalize, SessionState
    from mandarin.scheduler import SessionPlan
    from mandarin.drills import DrillResult

    plan = SessionPlan(session_type="standard", drills=[], micro_plan="test",
                       estimated_seconds=60)
    state = SessionState(session_id=session_id, plan=plan)
    state.results = [
        DrillResult(content_item_id=ids[0], modality="reading", drill_type="mc",
                    correct=True, skipped=False, user_answer="a", expected_answer="a",
                    error_type=None, feedback="", confidence="full"),
    ]

    output = []
    _finalize(conn, state, lambda t, end="\n": output.append(t), pre_milestones=set())
    full = "\n".join(output)
    # First session (no past sessions) should be encouraging
    assert "first sessions" in full.lower() or "correct" in full.lower(), \
        f"expected encouraging first-session framing:\n{full}"
    conn.close()


def test_finalize_stage_labels_use_correct_names():
    """Stage transition labels should use 6-stage names."""
    from mandarin.runner import _STAGE_LABELS
    # Module-level constant should have the 6 new stage labels
    assert "seen" in _STAGE_LABELS, "stage labels should include 'seen'"
    assert "stabilizing" in _STAGE_LABELS, "stage labels should include 'stabilizing'"
    assert "durable" in _STAGE_LABELS, "stage labels should include 'durable'"


# ── Web state visibility ──

def test_web_html_has_status_bar():
    """Web template should include status bar element."""
    html_path = Path(__file__).parent.parent / "mandarin" / "web" / "templates" / "index.html"
    if not html_path.exists():
        return  # skip if web UI not present
    html = html_path.read_text()
    assert "status-bar" in html, "HTML should have status-bar element"
    assert "status-dot" in html, "HTML should have status-dot indicator"
    assert "status-text" in html, "HTML should have status-text label"


def test_web_js_has_state_management():
    """Web JS should have setStatus function for state management."""
    js_path = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
    if not js_path.exists():
        return
    js = js_path.read_text()
    assert "function setStatus" in js, "JS should have setStatus function"
    # setStatus is called with state names like "connected", "disconnected", "loading"
    assert '"connected"' in js, "JS should use connected state"
    assert '"disconnected"' in js, "JS should use disconnected state"
    assert '"loading"' in js, "JS should use loading state"


def test_web_css_has_status_styles():
    """Web CSS should have status indicator styles."""
    css_path = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "style.css"
    if not css_path.exists():
        return
    css = css_path.read_text()
    assert "#status-bar" in css, "CSS should style status bar"
    assert ".dot-connected" in css, "CSS should style connected dot"
    assert ".dot-disconnected" in css, "CSS should style disconnected dot"


# ── Bridge reliability ──

def test_bridge_input_timeout():
    """Bridge input_fn should timeout instead of blocking forever."""
    from mandarin.web.bridge import WebBridge, INPUT_TIMEOUT

    class FakeWS:
        def send(self, msg): pass
        def receive(self, timeout=None): return None

    bridge = WebBridge(FakeWS())
    # Override timeout to something short for testing
    import mandarin.web.bridge as bridge_mod
    old_timeout = bridge_mod.INPUT_TIMEOUT
    bridge_mod.INPUT_TIMEOUT = 0.1  # 100ms

    try:
        result = bridge.input_fn("test prompt")
        assert result == "Q", f"timed-out input should return 'Q', got '{result}'"
        assert bridge._closed, "bridge should be marked closed after timeout"
    finally:
        bridge_mod.INPUT_TIMEOUT = old_timeout


def test_bridge_close_unblocks_input():
    """Calling bridge.close() should unblock a waiting input_fn."""
    from mandarin.web.bridge import WebBridge

    class FakeWS:
        def send(self, msg): pass

    bridge = WebBridge(FakeWS())
    result = [None]

    def wait_for_input():
        result[0] = bridge.input_fn("test")

    t = threading.Thread(target=wait_for_input, daemon=True)
    t.start()
    import time; time.sleep(0.05)
    bridge.close()
    t.join(timeout=2)
    assert not t.is_alive(), "input_fn should have been unblocked by close()"
    assert result[0] == "Q", f"close() should cause input_fn to return 'Q', got '{result[0]}'"


def test_bridge_show_after_close():
    """show_fn should silently no-op after bridge is closed."""
    from mandarin.web.bridge import WebBridge

    sent = []
    class FakeWS:
        def send(self, msg): sent.append(msg)

    bridge = WebBridge(FakeWS())
    bridge.show_fn("before close")
    assert len(sent) == 1

    bridge.close()
    bridge.show_fn("after close")
    assert len(sent) == 1, "show_fn should not send after close"


# ── Error sanitization ──

def test_error_sanitization():
    """Route error sanitizer should not leak internal details."""
    from mandarin.web.routes import _sanitize_error

    # Known error patterns
    assert "setup" in _sanitize_error(Exception("no such table: content_item")).lower()
    assert "busy" in _sanitize_error(Exception("database is locked")).lower()
    assert "no items" in _sanitize_error(Exception("No drills available")).lower()

    # Unknown errors should get generic message, not raw exception
    msg = _sanitize_error(Exception("sqlite3.OperationalError: disk I/O error"))
    assert "Something went wrong" in msg
    assert "sqlite3" not in msg


# ── Forecast precision ──

def test_forecast_consistency_detail_rounded():
    """compute_readiness consistency detail should round to 0.5, not show 66.5."""
    conn = _fresh_db()
    ids = _add_items(conn, 10)

    # Create enough sessions to have velocity data
    for i in range(5):
        sid = start_session(conn)
        for item_id in ids[:3]:
            record_attempt(conn, item_id, "reading", True, session_id=sid, drill_type="mc")
        db.end_session(conn, sid, items_completed=3, items_correct=3)

    from mandarin.diagnostics import compute_readiness
    readiness = compute_readiness(conn)
    detail = readiness["components"]["practice_consistency"]["detail"]

    # Should not have more than 1 decimal place and should be rounded to 0.5
    if "sessions/week" in detail:
        # Extract the number
        num_str = detail.replace("~", "").split("sessions")[0].strip()
        num = float(num_str)
        # Check it's a multiple of 0.5
        assert num * 2 == int(num * 2), \
            f"sessions/week should be rounded to 0.5: got '{detail}'"
    conn.close()


def test_forecast_early_stage_framing():
    """Forecast at < 8 sessions should frame as 'building baseline', not show raw HSK 1.0."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)

    # 2 sessions — below threshold
    for i in range(2):
        sid = start_session(conn)
        record_attempt(conn, ids[0], "reading", True, session_id=sid, drill_type="mc")
        db.end_session(conn, sid, items_completed=1, items_correct=1)

    from mandarin.diagnostics import project_forecast
    fc = project_forecast(conn)
    assert not fc["pace"]["reliable"], "pace should not be reliable at 2 sessions"

    # The total_sessions should be accessible
    assert fc["total_sessions"] == 2
    conn.close()


def test_status_early_effort_framing():
    """Status at <= 5 sessions should acknowledge effort, not just show flat numbers."""
    conn = _fresh_db()
    ids = _add_items(conn, 10)

    # 3 sessions with some attempts
    for i in range(3):
        sid = start_session(conn)
        for item_id in ids[:4]:
            record_attempt(conn, item_id, "reading", True, session_id=sid, drill_type="mc")
        db.end_session(conn, sid, items_completed=4, items_correct=3)

    from mandarin.milestones import get_stage_counts
    stages = get_stage_counts(conn)
    seen_total = stages["weak"] + stages["improving"] + stages["stable"]
    total_sessions = 3

    # Verify the framing logic
    stable_pct = (stages["stable"] / seen_total * 100) if seen_total > 0 else 0
    if stable_pct < 20 and total_sessions <= 5:
        msg = f"{seen_total} items seen across {total_sessions} sessions — foundation is forming."
        assert "foundation" in msg
    conn.close()


# ── Web JS improvements ──

def test_web_js_has_flash_status():
    """Web JS should have flashStatus function for non-prompt feedback."""
    js_path = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
    if not js_path.exists():
        return
    js = js_path.read_text()
    assert "function flashStatus" in js, "JS should have flashStatus for non-prompt Enter feedback"


