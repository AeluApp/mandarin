"""Tests for doctor module -- system health check."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path


# ---- TestDoctorDataFileChecks ----

def test_required_data_files_exist():
    """All files listed in REQUIRED_DATA_FILES should actually exist."""
    from mandarin.doctor import REQUIRED_DATA_FILES, DATA_DIR
    for fname in REQUIRED_DATA_FILES:
        path = DATA_DIR / fname
        assert path.exists(), f"Required data file missing: {fname}"


def test_required_data_files_valid_json():
    """All required data files should be valid JSON."""
    from mandarin.doctor import REQUIRED_DATA_FILES, DATA_DIR
    for fname in REQUIRED_DATA_FILES:
        path = DATA_DIR / fname
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, (list, dict)), \
                f"{fname} should contain a list or dict"


def test_required_data_files_meet_minimum():
    """Required data files should meet their minimum entry counts."""
    from mandarin.doctor import REQUIRED_DATA_FILES, DATA_DIR
    for fname, min_entries in REQUIRED_DATA_FILES.items():
        path = DATA_DIR / fname
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            # Data files may wrap content in a top-level key
            if isinstance(data, dict) and len(data) <= 5:
                lists = [(k, v) for k, v in data.items() if isinstance(v, list)]
                if lists:
                    _, biggest = max(lists, key=lambda x: len(x[1]))
                    count = len(biggest)
                else:
                    count = len(data)
            elif isinstance(data, list):
                count = len(data)
            else:
                count = 0
            assert count >= min_entries, \
                f"{fname} has {count} entries, expected >= {min_entries}"


# ---- TestDoctorRunChecks ----

def test_run_checks_returns_list():
    from mandarin.doctor import run_checks
    results = run_checks()
    assert isinstance(results, list)
    assert len(results) > 0


def test_check_result_format():
    from mandarin.doctor import run_checks
    results = run_checks()
    for r in results:
        assert "label" in r
        assert "ok" in r
        assert "detail" in r
        assert isinstance(r["ok"], bool)
        assert isinstance(r["label"], str)


def test_python_version_check_passes():
    from mandarin.doctor import run_checks
    results = run_checks()
    python_check = [r for r in results if "Python" in r["label"]]
    assert len(python_check) > 0
    assert python_check[0]["ok"], "Python version should pass on 3.9+"


def test_required_packages_checked():
    from mandarin.doctor import run_checks, REQUIRED_PACKAGES
    results = run_checks()
    for pkg in REQUIRED_PACKAGES:
        matching = [r for r in results if pkg in r["label"]]
        assert len(matching) > 0, f"Package '{pkg}' should be checked"


def test_data_directory_checked():
    from mandarin.doctor import run_checks
    results = run_checks()
    data_checks = [r for r in results if "Data directory" in r["label"]]
    assert len(data_checks) > 0


# ---- TestDoctorCheckHelper ----

def test_check_ok():
    from mandarin.doctor import _check
    result = _check("Test", True, "detail")
    assert result["label"] == "Test"
    assert result["ok"]
    assert result["detail"] == "detail"


def test_check_fail():
    from mandarin.doctor import _check
    result = _check("Test", False, "missing")
    assert not result["ok"]


def test_check_no_detail():
    from mandarin.doctor import _check
    result = _check("Test", True)
    assert result["detail"] == ""


# ---- TestDoctorPrintReport ----

def test_print_report_no_error():
    from mandarin.doctor import print_report
    results = [
        {"label": "Test 1", "ok": True, "detail": "good"},
        {"label": "Test 2", "ok": False, "detail": "bad"},
        {"label": "Optional: test3", "ok": False, "detail": "not installed"},
    ]
    # Should not raise
    f = io.StringIO()
    with redirect_stdout(f):
        print_report(results)
    output = f.getvalue()
    assert "1 passed" in output
    assert "1 optional missing" in output
    assert "1 failed" in output
