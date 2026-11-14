from __future__ import annotations

import random
import re
from datetime import date as Date, datetime, time as Time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import KRDError

CLOCK_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def timezone(name: str | None, fallback: str = "Asia/Shanghai") -> ZoneInfo:
    candidate = fallback if not name or name == "system" else name
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise KRDError("invalid_timezone", f"Unknown IANA timezone: {candidate}") from exc


def parse_clock(value: str) -> tuple[int, int]:
    match = CLOCK_RE.fullmatch(str(value or ""))
    if not match:
        raise KRDError("invalid_time", f"Expected HH:MM, got {value!r}")
    return int(match.group(1)), int(match.group(2))


def parse_date(value: str) -> Date:
    try:
        return Date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise KRDError("invalid_date", f"Expected YYYY-MM-DD, got {value!r}") from exc


def local_datetime(day: str, clock: str, tz_name: str, *, fold: int = 0) -> datetime:
    tz = timezone(tz_name)
    hour, minute = parse_clock(clock)
    naive = datetime.combine(parse_date(day), Time(hour, minute))
    aware = naive.replace(tzinfo=tz, fold=fold)
    # A nonexistent wall time does not survive a UTC round trip unchanged.
    roundtrip = datetime.fromtimestamp(aware.timestamp(), tz).replace(tzinfo=None)
    if roundtrip != naive:
        raise KRDError("nonexistent_local_time", f"{day} {clock} does not exist in {tz.key}")
    return aware


def to_utc(day: str, clock: str, tz_name: str) -> float:
    return local_datetime(day, clock, tz_name).timestamp()


def window_utc(day: str, start: str, end: str, tz_name: str) -> tuple[float, float]:
    first = local_datetime(day, start, tz_name)
    last = local_datetime(day, end, tz_name)
    if last <= first:
        last = local_datetime(str(parse_date(day) + timedelta(days=1)), end, tz_name)
    if last <= first:
        raise KRDError("invalid_window", "Window end must be after window start")
    return first.timestamp(), last.timestamp()


def next_daily(after: float, clock: str, tz_name: str) -> float:
    tz = timezone(tz_name)
    current = datetime.fromtimestamp(after, tz)
    day = current.date().isoformat()
    candidate = local_datetime(day, clock, tz_name)
    if candidate.timestamp() <= after:
        candidate = local_datetime(str(current.date() + timedelta(days=1)), clock, tz_name)
    return candidate.timestamp()


def subtract_window(start: float, end: float, blocked: list[tuple[float, float]]) -> list[tuple[float, float]]:
    segments = [(start, end)]
    for block_start, block_end in blocked:
        remaining = []
        for left, right in segments:
            if block_end <= left or block_start >= right:
                remaining.append((left, right))
                continue
            if left < block_start:
                remaining.append((left, min(right, block_start)))
            if right > block_end:
                remaining.append((max(left, block_end), right))
        segments = [(a, b) for a, b in remaining if b > a]
    return segments


def compiled_windows(day: str, definitions: list[dict], tz_name: str) -> list[tuple[float, float]]:
    result = []
    for item in definitions:
        result.append(window_utc(day, str(item["start"]), str(item["end"]), tz_name))
    return result


def sample_window(schedule: dict, day: str, tz_name: str, rng: random.Random) -> list[float]:
    start, end = window_utc(day, schedule["start"], schedule["end"], tz_name)
    count = int(schedule.get("occurrences", 1))
    mode = schedule.get("window_mode", "single_random")
    if count < 1 or count > 100:
        raise KRDError("invalid_occurrences", "occurrences must be between 1 and 100")
    if mode == "single_random" or count == 1:
        return [rng.uniform(start, end)]
    intervals = schedule.get("interval_minutes") or [5, 30]
    minimum, maximum = float(intervals[0]) * 60, float(intervals[1]) * 60
    if minimum <= 0 or maximum < minimum:
        raise KRDError("invalid_interval", "Expected 0 < interval_minutes[0] <= interval_minutes[1]")
    if (count - 1) * minimum > end - start:
        raise KRDError("window_capacity", "The requested occurrences and minimum interval do not fit this window")
    latest_first = end - (count - 1) * minimum
    points = [rng.uniform(start, latest_first)]
    for index in range(1, count):
        remaining = count - index - 1
        low = points[-1] + minimum
        high = points[-1] + maximum
        high = min(high, end - remaining * minimum)
        if high < low:
            raise KRDError("window_sampling", "Unable to sample a valid random sequence without dropping occurrences")
        points.append(rng.uniform(low, high))
    return points
