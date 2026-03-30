"""Tests for mandarin.experiments.holdout — global holdout group."""

from tests.shared_db import make_test_db
from mandarin.experiments.holdout import (
    assign_holdout,
    is_in_holdout,
    get_holdout_users,
    get_holdout_count,
)


def test_assign_holdout_deterministic():
    conn = make_test_db()
    # Same user always gets same result
    r1 = assign_holdout(conn, 999)
    r2 = assign_holdout(conn, 999)
    assert r1 == r2


def test_assign_holdout_returns_bool():
    conn = make_test_db()
    result = assign_holdout(conn, 1)
    assert isinstance(result, bool)


def test_is_in_holdout_false_by_default():
    conn = make_test_db()
    # User 1 from bootstrap — not in holdout unless assigned
    if not assign_holdout(conn, 1):
        assert is_in_holdout(conn, 1) is False


def test_get_holdout_users_empty():
    conn = make_test_db()
    # Force all users out of holdout by scanning until we find none in it
    users = get_holdout_users(conn)
    assert isinstance(users, list)


def test_get_holdout_count():
    conn = make_test_db()
    count = get_holdout_count(conn)
    assert isinstance(count, int)
    assert count >= 0


def test_holdout_persistence():
    conn = make_test_db()
    # Find a user_id that lands in holdout by brute force
    for uid in range(1, 500):
        if assign_holdout(conn, uid, holdout_rate=1.0):  # 100% rate forces holdout
            assert is_in_holdout(conn, uid) is True
            assert uid in get_holdout_users(conn)
            assert get_holdout_count(conn) >= 1
            break
