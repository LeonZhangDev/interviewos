"""FSRS-4.5 spaced-repetition scheduler with a 5-grade extension.

Implements the FSRS-4.5 memory model (stability S, difficulty D) with the
official default parameters from the open-spaced-repetition algorithm wiki:

- S_0(G)   = w[G-1]                                   (initial stability)
- D_0(G)   = w4 - (G-3) * w5                          (initial difficulty)
- D'(D,G)  = w7*D_0(3) + (1-w7) * (D - w6*(G-3))      (difficulty update, mean reversion)
- R(t,S)   = (1 + FACTOR * t/S)^DECAY                 (forgetting curve)
- S'_r     = S * (e^w8 * (11-D) * S^-w9 * (e^(w10*(1-R)) - 1) * mult + 1)
- S'_f     = w11 * D^-w12 * ((S+1)^w13 - 1) * e^(w14*(1-R))
- I(r,S)   = S/FACTOR * (r^(1/DECAY) - 1)             (interval at retention r)

DECAY = -0.5 and FACTOR = 19/81, so R(S,S) = 0.9 and I(0.9,S) = S.

The product keeps a 5-grade UI (1 不会 .. 5 很熟). FSRS grades are treated
as continuous in [1, 4]: {1: 1.0, 2: 2.0, 3: 3.0, 4: 3.5, 5: 4.0}. Between
integer anchors, initial stability interpolates geometrically and the
hard/easy multiplier applies in log space, so integer grades reproduce
canonical FSRS-4.5 exactly while grade 4 sits between Good and Easy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

DECAY = -0.5
FACTOR = 19.0 / 81.0
DEFAULT_W = (
    0.4872, 1.4003, 3.7145, 13.8206,  # w0-w3   initial stability (Again/Hard/Good/Easy)
    5.1618, 1.2298,                    # w4-w5   initial difficulty base/slope
    0.8975, 0.031,                     # w6-w7   difficulty damping / mean reversion
    1.6474, 0.1367, 1.0461,            # w8-w10  recall stability growth
    2.1072, 0.0793, 0.3246, 1.587,     # w11-w14 post-lapse stability
    0.2272, 2.8755,                    # w15-w16 hard penalty / easy bonus
)
REQUEST_RETENTION = 0.9
MAX_INTERVAL_DAYS = 365
MIN_STABILITY = 0.1

GRADE_TO_RATING = {1: 1.0, 2: 2.0, 3: 3.0, 4: 3.5, 5: 4.0}


@dataclass
class ReviewOutcome:
    stability: float
    difficulty: float
    retrievability: float  # recall probability just before this review
    interval_days: int
    is_new: bool
    failed: bool


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def init_stability(rating: float) -> float:
    """S_0(G): geometric interpolation between the w[0..3] anchors."""
    if rating <= 1.0:
        return max(DEFAULT_W[0], MIN_STABILITY)
    if rating >= 4.0:
        return max(DEFAULT_W[3], MIN_STABILITY)
    lower = math.floor(rating) - 1
    frac = rating - math.floor(rating)
    a, b = DEFAULT_W[lower], DEFAULT_W[lower + 1]
    return max(math.exp(math.log(a) * (1.0 - frac) + math.log(b) * frac), MIN_STABILITY)


def init_difficulty(rating: float) -> float:
    return clamp(DEFAULT_W[4] - (rating - 3.0) * DEFAULT_W[5], 1.0, 10.0)


def next_difficulty(difficulty: float, rating: float) -> float:
    d0_good = DEFAULT_W[4]  # D_0(3) = w4, the mean-reversion target
    delta = difficulty - DEFAULT_W[6] * (rating - 3.0)
    return clamp(DEFAULT_W[7] * d0_good + (1.0 - DEFAULT_W[7]) * delta, 1.0, 10.0)


def retrievability(elapsed_days: float, stability: float) -> float:
    if elapsed_days <= 0 or stability <= 0:
        return 1.0
    return (1.0 + FACTOR * elapsed_days / stability) ** DECAY


def interval_days(stability: float, retention: float = REQUEST_RETENTION) -> int:
    raw = stability / FACTOR * (retention ** (1.0 / DECAY) - 1.0)
    return int(clamp(round(raw), 1, MAX_INTERVAL_DAYS))


def _hard_easy_multiplier(rating: float) -> float:
    """w15 hard penalty / w16 easy bonus in log space; integer ratings
    reproduce the canonical step functions exactly."""
    if rating <= 2.0:
        return DEFAULT_W[15]
    if rating >= 4.0:
        return DEFAULT_W[16]
    if rating < 3.0:
        return math.exp(math.log(DEFAULT_W[15]) * (3.0 - rating))
    return math.exp(math.log(DEFAULT_W[16]) * (rating - 3.0))


def next_recall_stability(difficulty: float, stability: float, r: float, rating: float) -> float:
    inc = (
        math.exp(DEFAULT_W[8])
        * (11.0 - difficulty)
        * stability ** (-DEFAULT_W[9])
        * (math.exp(DEFAULT_W[10] * (1.0 - r)) - 1.0)
        * _hard_easy_multiplier(rating)
    )
    return max(stability * (1.0 + inc), MIN_STABILITY)


def post_lapse_stability(difficulty: float, stability: float, r: float) -> float:
    value = (
        DEFAULT_W[11]
        * difficulty ** (-DEFAULT_W[12])
        * ((stability + 1.0) ** DEFAULT_W[13] - 1.0)
        * math.exp(DEFAULT_W[14] * (1.0 - r))
    )
    return max(value, MIN_STABILITY)


def elapsed_days(last_review_at: datetime | None, now: datetime) -> float:
    if last_review_at is None:
        return 0.0
    return max((now - last_review_at).total_seconds() / 86400.0, 0.0)


def schedule_review(
    grade: int,
    *,
    stability: float | None = None,
    difficulty: float | None = None,
    last_review_at: datetime | None = None,
    now: datetime,
) -> ReviewOutcome:
    """Compute the post-review FSRS memory state and next interval.

    A topic is new when it has no FSRS state (stability 0/None) or has
    never actually been reviewed (last_review_at None, e.g. seeded mastery
    estimates) — the first real review then initializes stability and
    difficulty from the grade alone. Grade 1 counts as a lapse and uses
    the post-lapse stability formula.
    """
    if grade not in GRADE_TO_RATING:
        raise ValueError(f"grade must be 1-5, got {grade!r}")
    rating = GRADE_TO_RATING[grade]
    is_new = not stability or stability <= 0 or last_review_at is None
    failed = grade == 1

    if is_new:
        new_stability = init_stability(rating)
        new_difficulty = init_difficulty(rating)
        r = 1.0
    else:
        assert stability is not None and difficulty is not None
        r = retrievability(elapsed_days(last_review_at, now), stability)
        if failed:
            new_stability = post_lapse_stability(difficulty, stability, r)
        else:
            new_stability = next_recall_stability(difficulty, stability, r, rating)
        new_difficulty = next_difficulty(difficulty, rating)

    new_stability = round(clamp(new_stability, MIN_STABILITY, MAX_INTERVAL_DAYS), 2)
    return ReviewOutcome(
        stability=new_stability,
        difficulty=round(new_difficulty, 2),
        retrievability=round(r, 4),
        interval_days=interval_days(new_stability),
        is_new=is_new,
        failed=failed,
    )


def grade_from_score(score: float) -> int:
    """Map an AI / exercise score (0-100) onto the 5-grade scale."""
    if score < 40:
        return 1
    if score < 60:
        return 2
    if score < 80:
        return 3
    if score < 95:
        return 4
    return 5


def legacy_state(score: float, legacy_interval: int) -> tuple[float, float]:
    """Seed FSRS state for rows written by the fixed 1/3/7/14-day scheduler.

    I(r=0.9, S) = S makes the legacy interval a serviceable stability
    estimate; difficulty maps the 0-100 mastery score onto the 1-10 FSRS
    scale (score 50 -> 5.0, 100 -> 1.0).
    """
    interval = legacy_interval if legacy_interval and legacy_interval > 0 else 1
    stability = round(clamp(float(interval), MIN_STABILITY, MAX_INTERVAL_DAYS), 2)
    difficulty = round(clamp(10.0 - score / 10.0, 1.0, 10.0), 2)
    return stability, difficulty
