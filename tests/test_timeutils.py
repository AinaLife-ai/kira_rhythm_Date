from __future__ import annotations

import random
from datetime import datetime

import pytest

from krd.models import KRDError
from krd.timeutils import compiled_windows, next_daily, sample_window, subtract_window, to_utc, window_utc


def test_cross_midnight_window():
    start, end = window_utc("2026-11-15", "23:30", "07:00", "Asia/Shanghai")
    assert end - start == 7.5 * 3600
    assert datetime.fromtimestamp(start, __import__('zoneinfo').ZoneInfo("Asia/Shanghai")).day == 15
    assert datetime.fromtimestamp(end, __import__('zoneinfo').ZoneInfo("Asia/Shanghai")).day == 16


def test_nonexistent_dst_time_rejected():
    with pytest.raises(KRDError) as error:
        to_utc("2026-03-08", "02:30", "America/New_York")
    assert error.value.code == "nonexistent_local_time"


def test_next_daily_is_future():
    now = to_utc("2026-11-15", "23:01", "Asia/Shanghai")
    due = next_daily(now, "23:00", "Asia/Shanghai")
    assert datetime.fromtimestamp(due, __import__('zoneinfo').ZoneInfo("Asia/Shanghai")).day == 16


def test_random_sequence_respects_capacity_and_intervals():
    schedule = {"start": "09:00", "end": "10:00", "occurrences": 4, "window_mode": "interval_random", "interval_minutes": [5, 10]}
    points = sample_window(schedule, "2026-11-16", "Asia/Shanghai", random.Random(7))
    assert len(points) == 4
    assert all(5 * 60 <= b - a <= 10 * 60 for a, b in zip(points, points[1:]))


def test_impossible_random_sequence_rejected():
    schedule = {"start": "09:00", "end": "09:10", "occurrences": 4, "window_mode": "interval_random", "interval_minutes": [5, 10]}
    with pytest.raises(KRDError) as error:
        sample_window(schedule, "2026-11-16", "Asia/Shanghai", random.Random(1))
    assert error.value.code == "window_capacity"


def test_blocked_interval_subtraction():
    segments = subtract_window(0, 100, [(10, 20), (50, 60)])
    assert segments == [(0, 10), (20, 50), (60, 100)]
