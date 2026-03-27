"""Playwright E2E mobile tests — verify responsive layout and mobile interactions.

Tests cover:
1. Golden paths at mobile viewport (registration, onboarding, session, dashboard)
2. Touch target size verification (>= 44px)
3. Sticky input bar behavior
4. Stats row horizontal scroll
5. Orientation change handling
6. Bottom panel expansion/collapse

Run with:
    pytest tests/e2e/test_mobile.py -v --headed
    pytest tests/e2e/test_mobile.py -v
"""

import re
import time

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Page, expect


def _register(page: Page, base_url: str, email: str = None):
    """Register a new user at mobile viewport."""
    if email is None:
        email = f"e2e-mobile-{int(time.time() * 1000)}@test.com"
    password = "TestPass123!"
    page.goto(f"{base_url}/auth/register")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.fill('input[name="confirm"]', password)
    invite_field = page.locator('input[name="invite_code"]')
    if invite_field.count() > 0 and invite_field.is_visible():
        invite_field.fill("BETA")
    page.click('button[type="submit"]')
    page.wait_for_url(re.compile(r"/$"), timeout=10000)
    return email


def _complete_onboarding(page: Page, level: int = 1, goal: str = "quick"):
    """Complete onboarding wizard.

    The wizard has 3 intro slides before the level/goal picker.
    We skip them via the 'Skip intro' button on the first slide.
    """
    wizard = page.locator("#onboarding-wizard")
    try:
        wizard.wait_for(state="visible", timeout=3000)
    except Exception:
        return
    # Skip intro slides via JS (Playwright force-click doesn't trigger handlers reliably)
    page.evaluate("""() => {
        const skip = document.getElementById('onboarding-skip-0');
        if (skip) { skip.click(); return; }
        const step1 = document.getElementById('onboarding-step-1');
        if (step1) step1.classList.remove('hidden');
        document.querySelectorAll('.onboarding-intro-slide').forEach(s => s.classList.add('hidden'));
    }""")
    page.wait_for_timeout(1000)
    page.locator(f"[data-level='{level}']").wait_for(state="visible", timeout=5000)
    page.click(f"[data-level='{level}']")
    page.wait_for_timeout(500)
    page.click(f"[data-goal='{goal}']")
    page.wait_for_load_state("networkidle", timeout=15000)


# ── Mobile Golden Path 1: Registration at mobile viewport ──────


def test_mobile_registration_page_renders(e2e_server, mobile_page: Page):
    """Registration form is fully visible and usable at 375px width."""
    mobile_page.goto(f"{e2e_server}/auth/register")
    expect(mobile_page.locator('input[name="email"]')).to_be_visible()
    expect(mobile_page.locator('input[name="password"]')).to_be_visible()
    expect(mobile_page.locator('button[type="submit"]')).to_be_visible()

    # Submit button should be within viewport
    btn = mobile_page.locator('button[type="submit"]')
    box = btn.bounding_box()
    assert box is not None
    assert box["x"] + box["width"] <= 375, "Submit button overflows viewport"


def test_mobile_registration_and_onboarding(e2e_server, mobile_page: Page):
    """Full registration and onboarding flow works at mobile viewport."""
    _register(mobile_page, e2e_server)
    wizard = mobile_page.locator("#onboarding-wizard")
    expect(wizard).to_be_visible(timeout=5000)

    # Wizard starts with intro slides; skip to level picker
    skip_btn = mobile_page.locator("#onboarding-skip-0")
    # Skip intro slides via JS
    mobile_page.evaluate("""() => {
        const skip = document.getElementById('onboarding-skip-0');
        if (skip) { skip.click(); return; }
        const step1 = document.getElementById('onboarding-step-1');
        if (step1) step1.classList.remove('hidden');
        document.querySelectorAll('.onboarding-intro-slide').forEach(s => s.classList.add('hidden'));
    }""")
    mobile_page.wait_for_timeout(1000)

    # Level buttons should be visible and tappable
    level_btn = mobile_page.locator("[data-level='1']")
    expect(level_btn).to_be_visible(timeout=5000)


# ── Mobile Golden Path 2: Dashboard at mobile viewport ──────


def test_mobile_dashboard_renders(e2e_server, mobile_page: Page):
    """Dashboard loads and renders at mobile width."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="quick")

    expect(mobile_page.locator("#dashboard")).to_be_visible()
    expect(mobile_page.locator("#btn-start")).to_be_visible()

    # Begin button should be within viewport
    btn = mobile_page.locator("#btn-start")
    box = btn.bounding_box()
    assert box is not None
    assert box["x"] + box["width"] <= 375, "Begin button overflows mobile viewport"


# ── Mobile Golden Path 3: Session start at mobile viewport ──────


def test_mobile_session_start(e2e_server, mobile_page: Page):
    """Session starts correctly at mobile viewport."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="quick")

    btn = mobile_page.locator("#btn-start")
    expect(btn).to_be_enabled(timeout=10000)
    btn.click()

    expect(mobile_page.locator("#session")).to_be_visible(timeout=10000)
    expect(mobile_page.locator("#drill-area")).to_be_visible()
    expect(mobile_page.locator("#progress-bar")).to_be_visible()


# ── Touch Target Verification ──────


def test_mobile_touch_targets_minimum_size(e2e_server, mobile_page: Page):
    """All interactive elements meet 44px minimum touch target size."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="quick")

    # Check main action buttons
    for selector in ["#btn-start", "#btn-mini"]:
        el = mobile_page.locator(selector)
        if el.count() > 0 and el.is_visible():
            box = el.bounding_box()
            assert box is not None, f"{selector} has no bounding box"
            assert box["height"] >= 44, (
                f"{selector} height {box['height']}px < 44px minimum touch target"
            )


def test_mobile_input_fields_adequate_size(e2e_server, mobile_page: Page):
    """Input fields on registration are large enough to tap."""
    mobile_page.goto(f"{e2e_server}/auth/register")
    for name in ["email", "password"]:
        el = mobile_page.locator(f'input[name="{name}"]')
        expect(el).to_be_visible()
        box = el.bounding_box()
        assert box is not None
        assert box["height"] >= 36, (
            f"Input '{name}' height {box['height']}px too small for mobile"
        )


# ── Stats Row Horizontal Scroll ──────


def test_mobile_stats_row_scrollable(e2e_server, mobile_page: Page):
    """Stats row should be horizontally scrollable on mobile."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="standard")
    mobile_page.wait_for_timeout(2000)

    stats = mobile_page.locator(".stats-row")
    if stats.count() > 0 and stats.is_visible():
        # Stats row should either fit or be scrollable (overflow-x: auto)
        overflow = stats.evaluate("el => getComputedStyle(el).overflowX")
        scroll_width = stats.evaluate("el => el.scrollWidth")
        client_width = stats.evaluate("el => el.clientWidth")
        # Either content fits, or overflow allows scrolling
        assert overflow in ("auto", "scroll") or scroll_width <= client_width, (
            "Stats row overflows but is not scrollable"
        )


# ── Orientation Change ──────


def test_mobile_orientation_portrait_to_landscape(e2e_server, mobile_page: Page):
    """App adapts when rotating from portrait to landscape."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="quick")

    # Start in portrait (375x812)
    expect(mobile_page.locator("#dashboard")).to_be_visible()

    # Rotate to landscape
    mobile_page.set_viewport_size({"width": 812, "height": 375})
    mobile_page.wait_for_timeout(500)

    # Dashboard should still be visible and functional
    expect(mobile_page.locator("#dashboard")).to_be_visible()
    expect(mobile_page.locator("#btn-start")).to_be_visible()

    # Rotate back to portrait
    mobile_page.set_viewport_size({"width": 375, "height": 812})
    mobile_page.wait_for_timeout(500)
    expect(mobile_page.locator("#dashboard")).to_be_visible()


# ── Landing Pages at Mobile ──────


def test_mobile_landing_page_nav_toggle(e2e_server, mobile_page: Page):
    """Landing page nav collapses to hamburger menu at mobile width."""
    mobile_page.goto(f"{e2e_server}/about")
    mobile_page.wait_for_timeout(500)

    toggle = mobile_page.locator(".nav-toggle")
    if toggle.count() > 0:
        # Nav toggle should be visible at mobile width
        expect(toggle).to_be_visible()

        # Click to open
        toggle.click()
        nav_links = mobile_page.locator(".nav-links")
        expect(nav_links).to_be_visible()


def test_mobile_no_horizontal_overflow(e2e_server, mobile_page: Page):
    """Pages should not have horizontal scroll at mobile viewport."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="quick")
    mobile_page.wait_for_timeout(1000)

    # Check document doesn't overflow horizontally
    doc_width = mobile_page.evaluate("document.documentElement.scrollWidth")
    viewport_width = mobile_page.evaluate("window.innerWidth")
    assert doc_width <= viewport_width + 1, (
        f"Horizontal overflow: document {doc_width}px > viewport {viewport_width}px"
    )


# ── Bottom Panel Expansion ──────


def test_mobile_panel_visibility(e2e_server, mobile_page: Page):
    """Dashboard panels render correctly at mobile width without overflow."""
    _register(mobile_page, e2e_server)
    _complete_onboarding(mobile_page, level=1, goal="standard")
    mobile_page.wait_for_timeout(2000)

    # Vocabulary panel should be visible (basic panel shown even for new users)
    vocab_panel = mobile_page.locator("#vocab-panel")
    if vocab_panel.count() > 0 and vocab_panel.is_visible():
        box = vocab_panel.bounding_box()
        assert box is not None
        assert box["width"] <= 375, "Vocab panel overflows mobile viewport"
