"""FSRS-4.5 spaced repetition: scheduler unit properties, API integration,
tenant isolation of review history, legacy backfill and migration parity.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config

from app.config import settings
from app.timeutil import utc_now
from app.fsrs import (
    DEFAULT_W,
    grade_from_score,
    init_stability,
    interval_days,
    legacy_state,
    post_lapse_stability,
    retrievability,
    schedule_review,
)

from tests.conftest import BACKEND_DIR, db_insert, db_scalar


NOW = datetime(2026, 1, 10, 12, 0, 0)


# ---------------------------------------------------------------------------
# Scheduler unit properties
# ---------------------------------------------------------------------------

def test_forgetting_curve_anchors():
    assert retrievability(0, 3.71) == 1.0
    assert abs(retrievability(3.71, 3.71) - 0.9) < 1e-9
    r7 = retrievability(7, 3.71)
    r14 = retrievability(14, 3.71)
    assert 0.5 < r7 < 0.9
    assert r14 < r7


def test_interval_at_default_retention_equals_stability():
    assert interval_days(1.0) == 1
    assert interval_days(3.71) == 4
    assert interval_days(13.82) == 14
    assert interval_days(100.0) == 100
    assert interval_days(0.03) == 1      # clamped to >= 1 day
    assert interval_days(10_000.0) == 365  # clamped to <= 365 days


def test_integer_ratings_reproduce_canonical_fsrs():
    assert init_stability(1.0) == DEFAULT_W[0]
    assert init_stability(2.0) == DEFAULT_W[1]
    assert init_stability(3.0) == DEFAULT_W[2]
    assert init_stability(4.0) == DEFAULT_W[3]
    # UI grade 4 sits at rating 3.5: geometric midpoint between Good and Easy
    assert init_stability(3.5) == pytest.approx(math.sqrt(DEFAULT_W[2] * DEFAULT_W[3]), rel=1e-6)


def test_new_topic_interval_monotone_in_grade():
    intervals = [schedule_review(g, now=NOW).interval_days for g in (1, 2, 3, 4, 5)]
    assert intervals == sorted(intervals)
    assert intervals[0] <= 2   # "不会" -> review again almost immediately
    assert intervals[-1] >= 7  # "很熟" -> at least a week
    assert intervals[-1] == round(DEFAULT_W[3])


def test_recall_interval_monotone_in_grade():
    base = dict(stability=10.0, difficulty=5.0, last_review_at=NOW - timedelta(days=7))
    intervals = [schedule_review(g, now=NOW, **base).interval_days for g in (1, 2, 3, 4, 5)]
    assert intervals == sorted(intervals)
    assert intervals[4] > intervals[0]


def test_failure_reduces_stability_success_grows_it():
    base = dict(stability=10.0, difficulty=5.0, last_review_at=NOW - timedelta(days=7))
    failure = schedule_review(1, now=NOW, **base)
    success = schedule_review(3, now=NOW, **base)
    assert failure.failed and not success.failed
    assert failure.stability < 10.0
    assert success.stability > 10.0


def test_consecutive_good_reviews_grow_stability_and_interval():
    t = datetime(2026, 1, 1)
    last_review = None
    stability = None
    previous = None
    for _ in range(5):
        outcome = schedule_review(3, stability=stability, difficulty=5.0, last_review_at=last_review, now=t)
        if previous is not None:
            assert outcome.stability > previous.stability
            assert outcome.interval_days >= previous.interval_days
        previous = outcome
        stability = outcome.stability
        last_review = t
        t += timedelta(days=outcome.interval_days)
    assert previous.interval_days >= 20  # a mature topic reaches monthly intervals


def test_difficulty_direction_and_bounds():
    hard = schedule_review(1, now=NOW)  # new topic, "不会"
    easy = schedule_review(5, now=NOW)
    assert hard.difficulty > easy.difficulty
    assert 1.0 <= hard.difficulty <= 10.0
    assert 1.0 <= easy.difficulty <= 10.0

    difficulty, stability, last_review = 5.0, 10.0, NOW - timedelta(days=10)
    for _ in range(30):
        outcome = schedule_review(1, stability=stability, difficulty=difficulty, last_review_at=last_review, now=NOW)
        assert 1.0 <= outcome.difficulty <= 10.0
        difficulty, stability, last_review = outcome.difficulty, outcome.stability, NOW


def test_spacing_effect_recall():
    soon = schedule_review(3, stability=10.0, difficulty=5.0, last_review_at=NOW - timedelta(days=1), now=NOW)
    late = schedule_review(3, stability=10.0, difficulty=5.0, last_review_at=NOW - timedelta(days=30), now=NOW)
    # canonical FSRS-4.5: lower retrievability -> larger stability increment
    assert late.retrievability < soon.retrievability
    assert late.stability > soon.stability


def test_same_day_recall_keeps_stability():
    outcome = schedule_review(3, stability=10.0, difficulty=5.0, last_review_at=NOW, now=NOW)
    assert outcome.retrievability == 1.0
    assert outcome.stability == 10.0
    assert outcome.interval_days == 10


def test_post_lapse_matches_formula():
    r = 0.9
    expected = (
        DEFAULT_W[11]
        * 5.0 ** (-DEFAULT_W[12])
        * ((10.0 + 1.0) ** DEFAULT_W[13] - 1.0)
        * math.exp(DEFAULT_W[14] * (1 - r))
    )
    assert post_lapse_stability(5.0, 10.0, r) == pytest.approx(expected, rel=1e-9)


def test_grade_from_score_boundaries():
    assert grade_from_score(0) == 1
    assert grade_from_score(39.9) == 1
    assert grade_from_score(40) == 2
    assert grade_from_score(59.9) == 2
    assert grade_from_score(60) == 3
    assert grade_from_score(79.9) == 3
    assert grade_from_score(80) == 4
    assert grade_from_score(94.9) == 4
    assert grade_from_score(95) == 5
    assert grade_from_score(100) == 5


def test_grade_validation():
    for bad in (0, 6, -1):
        with pytest.raises(ValueError):
            schedule_review(bad, now=NOW)


def test_legacy_state_mapping():
    assert legacy_state(50, 7) == (7.0, 5.0)
    assert legacy_state(100, 0) == (1.0, 1.0)
    assert legacy_state(0, 400) == (365.0, 10.0)


# ---------------------------------------------------------------------------
# Migration parity / backfill
# ---------------------------------------------------------------------------

def _migrated_db_path() -> str:
    return settings.database_url.removeprefix("sqlite+aiosqlite:///")


def test_fsrs_columns_present(migrated_database):
    conn = sqlite3.connect(_migrated_db_path())
    try:
        mastery_columns = {row[1] for row in conn.execute("PRAGMA table_info(mastery)")}
        assert {"stability", "difficulty", "reps", "lapses", "last_review_at"} <= mastery_columns
        log_columns = {row[1] for row in conn.execute("PRAGMA table_info(review_logs)")}
        assert {
            "id", "mastery_id", "user_id", "topic", "grade", "source", "score",
            "stability", "difficulty", "retrievability", "elapsed_days",
            "scheduled_days", "reviewed_at",
        } == log_columns
    finally:
        conn.close()


def test_0004_backfills_legacy_rows(tmp_path, monkeypatch):
    """Rows written by the fixed-interval scheduler are upgraded in place:
    stability <- legacy interval, difficulty <- 0-100 score, reps <- 1 and a
    plausible last_review_at (due_at - interval) so maturity survives."""
    db_file = tmp_path / "backfill.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(cfg, "0003_v08_auth_lifecycle")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO mastery (topic, score, due_at, interval_days, user_id) "
            "VALUES ('Legacy / Topic', 50, '2026-08-25 00:00:00', 7, NULL)"
        )
        conn.execute(
            "INSERT INTO mastery (topic, score, due_at, interval_days, user_id) "
            "VALUES ('Unreviewed / Topic', 95, '2026-08-30 00:00:00', 1, NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_file)
    try:
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT topic, stability, difficulty, reps, lapses, last_review_at FROM mastery"
            )
        }
        stability, difficulty, reps, lapses, last_review_at = rows["Legacy / Topic"]
        assert stability == 7.0
        assert difficulty == 5.0
        assert (reps, lapses) == (1, 0)
        assert last_review_at == "2026-08-18 00:00:00"  # due_at - 7 days
        assert rows["Unreviewed / Topic"][:4] == (1.0, 1.0, 1, 0)
        review_logs_exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='review_logs'"
        ).fetchone()[0]
        assert review_logs_exists == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

def _answer_first_question(client, headers) -> dict:
    questions = client.get("/api/questions", headers=headers).json()
    q = questions[0]
    response = client.post(
        f"/api/questions/{q['id']}/answers",
        json={"content": q["answer"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _weakness_by_topic(client, headers) -> dict:
    return {x["topic"]: x for x in client.get("/api/learning/weakness", headers=headers).json()}


def test_seeded_mastery_has_fsrs_state(client, make_user):
    user = make_user()
    weakness = client.get("/api/learning/weakness", headers=user["headers"]).json()
    assert len(weakness) >= 9
    for item in weakness:
        assert item["stability"] > 0
        assert 1.0 <= item["difficulty"] <= 10.0
        assert 0.0 <= item["retrievability"] <= 1.0
        assert item["reps"] == 0


def test_answer_updates_fsrs_state_and_logs(client, make_user):
    user = make_user()
    saved = _answer_first_question(client, user["headers"])
    topic = saved["mastery"]["topic"]

    item = _weakness_by_topic(client, user["headers"])[topic]
    assert item["reps"] == 1
    assert item["lapses"] == 0
    assert item["stability"] > 0
    assert 1.0 <= item["difficulty"] <= 10.0
    assert 0.0 <= item["retrievability"] <= 1.0
    assert item["interval_days"] >= 1
    assert item["last_review_at"] is not None

    history = client.get(f"/api/learning/{topic}/history", headers=user["headers"]).json()
    assert len(history) == 1
    entry = history[0]
    assert entry["source"] == "answer"
    assert entry["grade"] == grade_from_score(saved["score"])
    assert entry["scheduled_days"] >= 1
    assert entry["elapsed_days"] == 0.0  # seeded row counts as a first review
    assert entry["stability"] == item["stability"]
    assert entry["reviewed_at"].startswith("20")


def test_manual_review_uses_fsrs(client, make_user):
    user = make_user()
    saved = _answer_first_question(client, user["headers"])
    topic = saved["mastery"]["topic"]
    stability_before = _weakness_by_topic(client, user["headers"])[topic]["stability"]

    lapse = client.post(f"/api/learning/{topic}/review?grade=1", headers=user["headers"])
    assert lapse.status_code == 200
    data = lapse.json()
    assert data["interval_days"] <= 3  # post-lapse: review again almost immediately
    assert data["lapses"] == 1
    assert data["reps"] == 2
    assert data["stability"] < stability_before
    assert 1.0 <= data["difficulty"] <= 10.0

    strong = client.post(f"/api/learning/{topic}/review?grade=5", headers=user["headers"])
    assert strong.status_code == 200
    strong_data = strong.json()
    assert strong_data["interval_days"] >= data["interval_days"]
    assert strong_data["reps"] == 3

    # grade bounds are enforced by the query validator
    assert client.post(f"/api/learning/{topic}/review?grade=0", headers=user["headers"]).status_code == 422
    assert client.post(f"/api/learning/{topic}/review?grade=6", headers=user["headers"]).status_code == 422
    assert client.post("/api/learning/No Such Topic/review?grade=3", headers=user["headers"]).status_code == 404


def test_review_history_tenant_isolation(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    saved = _answer_first_question(client, alice["headers"])
    topic = saved["mastery"]["topic"]

    alice_history = client.get(f"/api/learning/{topic}/history", headers=alice["headers"])
    assert alice_history.status_code == 200
    assert len(alice_history.json()) == 1

    # Bob owns the seeded mastery row for the same topic but sees no reviews,
    # and his manual grade cannot touch Alice's FSRS state.
    bob_history = client.get(f"/api/learning/{topic}/history", headers=bob["headers"])
    assert bob_history.status_code == 200
    assert bob_history.json() == []

    assert client.post(f"/api/learning/{topic}/review?grade=1", headers=bob["headers"]).status_code == 200
    bob_item = _weakness_by_topic(client, bob["headers"])[topic]
    alice_item = _weakness_by_topic(client, alice["headers"])[topic]
    assert bob_item["lapses"] == 1
    assert bob_item["reps"] == 1
    assert alice_item["lapses"] == 0
    assert alice_item["reps"] == 1


def test_legacy_row_without_timestamp_starts_as_new(client, make_user):
    """A pre-FSRS row without review timestamps (not covered by the 0004
    backfill) safely starts FSRS as a new topic on its first review."""
    user = make_user("carol")
    user_id = db_scalar("SELECT id FROM users WHERE username = ?", ("carol",))
    db_insert(
        "INSERT INTO mastery (user_id, topic, score, due_at, interval_days, stability, difficulty, reps, lapses, last_review_at) "
        "VALUES (?, 'Legacy / Topic', 50, '2026-01-01 00:00:00', 7, 0, 0, 0, 0, NULL)",
        (user_id,),
    )

    review = client.post("/api/learning/Legacy / Topic/review?grade=3", headers=user["headers"])
    assert review.status_code == 200
    data = review.json()
    assert data["interval_days"] == 4  # new-topic Good anchor, not the legacy 7d
    assert data["reps"] == 1
    assert data["stability"] > 0

    history = client.get("/api/learning/Legacy / Topic/history", headers=user["headers"]).json()
    assert len(history) == 1
    assert history[0]["scheduled_days"] == 7  # legacy interval still recorded
    assert history[0]["elapsed_days"] == 0.0
    assert history[0]["source"] == "manual"


def test_backfilled_legacy_row_keeps_maturity(client, make_user):
    """A row that went through the 0004-style backfill (FSRS state + review
    timestamp) keeps its stability and grows on an overdue success."""
    user = make_user("dave")
    user_id = db_scalar("SELECT id FROM users WHERE username = ?", ("dave",))
    last_review = (utc_now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    db_insert(
        "INSERT INTO mastery (user_id, topic, score, due_at, interval_days, stability, difficulty, reps, lapses, last_review_at) "
        "VALUES (?, 'Mature / Topic', 50, '2026-01-01 00:00:00', 7, 7.0, 5.0, 1, 0, ?)",
        (user_id, last_review),
    )

    review = client.post("/api/learning/Mature / Topic/review?grade=3", headers=user["headers"])
    assert review.status_code == 200
    data = review.json()
    # 20 days elapsed on S=7 -> spacing effect grows stability well past 7d
    assert data["stability"] > 20.0
    assert data["interval_days"] > 7
    assert data["reps"] == 2

    history = client.get("/api/learning/Mature / Topic/history", headers=user["headers"]).json()
    assert history[0]["scheduled_days"] == 7
    assert 19.0 <= history[0]["elapsed_days"] <= 21.0
