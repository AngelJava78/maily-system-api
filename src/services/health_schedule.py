"""When the Azure database is on (spec 005, FR-033 to FR-035; research R12).

The database of the platform is stopped outside its hours by the runbook `Deploy-PgAutoShutdown.ps1`
(America/Mexico_City, Monday to Friday, 08:00 to 20:00), so a failure outside the window is
"stopped", not "down", and the health tells when it starts again. The day and the time are those of
the zone at that instant, with its rules: a zone with summer time changes its offset, and on those
days the start may not exist (the clock jumps forward) or happen twice (the clock goes back).

Pure functions: no I/O (the zone was loaded when the configuration was validated).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.config import DatabaseSchedule

# A week and one day: from the local date of the observation, a day of the schedule always comes.
_DAYS_TO_SEARCH = 8


def in_window(schedule: DatabaseSchedule, instant: datetime) -> bool:
    """Whether the database should be on at `instant`: one of its days and `[start, end)`."""
    local = instant.astimezone(schedule.zone)
    return local.weekday() in schedule.days and schedule.start <= local.time() < schedule.end


def next_start(schedule: DatabaseSchedule, instant: datetime) -> datetime:
    """The first instant after `instant` at which the window opens, in UTC."""
    first_date = instant.astimezone(schedule.zone).date()
    for offset in range(_DAYS_TO_SEARCH):
        day = first_date + timedelta(days=offset)
        if day.weekday() not in schedule.days:
            continue
        start = _local_start(schedule.zone, day, schedule.start)
        if start > instant:
            return start
    raise ValueError("A schedule always has at least one day")  # pragma: no cover


def _local_start(zone: ZoneInfo, day: date, at: time) -> datetime:
    """The instant (in UTC) at which the clock of `zone` shows `at` on `day`.

    A time that happens twice is the first one (`fold=0`). A time that does not exist is the instant
    of the jump: `fold=0` reads it with the offset of before, which gives an instant where the clock
    already shows another time.
    """
    candidate = datetime.combine(day, at, tzinfo=zone)  # fold=0
    instant = candidate.astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) == candidate.replace(tzinfo=None):
        return instant
    return _jump_before(zone, instant)


def _jump_before(zone: ZoneInfo, after: datetime) -> datetime:
    """The first second with the offset of `after`: when the clock jumped, at most a day before.

    A bisection of whole seconds: 17 steps cover a day (2^17 > 86 400).
    """
    offset = after.astimezone(zone).utcoffset()
    low = int((after - timedelta(days=1)).timestamp())  # still with the offset of before
    high = int(after.timestamp())
    while high - low > 1:
        middle = (low + high) // 2
        if datetime.fromtimestamp(middle, zone).utcoffset() == offset:
            high = middle
        else:
            low = middle
    return datetime.fromtimestamp(high, UTC)
