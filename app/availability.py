from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import AvailabilitySlot, Task

KINDS = ("busy", "meeting", "focus", "off")

DAY_START_HOUR = 8
DAY_END_HOUR = 22  # exclusive → сетка рисует 8..21 (14 строк)


@dataclass
class RenderedSlot:
    start_at: datetime
    end_at: datetime
    kind: str
    note: Optional[str]
    slot_id: Optional[int]  # None для авто-слотов из дедлайнов
    editable: bool
    source: str  # "manual" | "deadline"


def week_start(anchor: date) -> date:
    return anchor - timedelta(days=anchor.weekday())


def week_days(anchor: date) -> List[date]:
    start = week_start(anchor)
    return [start + timedelta(days=i) for i in range(7)]


def get_manual_slots(db: Session, user_id: int, start: datetime, end: datetime) -> List[AvailabilitySlot]:
    return (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.user_id == user_id,
            AvailabilitySlot.start_at < end,
            AvailabilitySlot.end_at > start,
        )
        .order_by(AvailabilitySlot.start_at)
        .all()
    )


def get_deadline_slots(db: Session, user_id: int, start: datetime, end: datetime) -> List[RenderedSlot]:
    rows = (
        db.query(Task)
        .filter(
            Task.assignee_id == user_id,
            Task.ended_at.isnot(None),
            Task.ended_at >= start,
            Task.ended_at < end,
        )
        .all()
    )
    out: List[RenderedSlot] = []
    for t in rows:
        dl = t.ended_at
        slot_start = dl.replace(hour=9, minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(hours=1)
        note = f"Дедлайн: {t.name}"
        out.append(RenderedSlot(
            start_at=slot_start,
            end_at=slot_end,
            kind="meeting",
            note=note,
            slot_id=None,
            editable=False,
            source="deadline",
        ))
    return out


def render_week(db: Session, user_id: int, anchor: date, viewer_is_self: bool) -> dict:
    days = week_days(anchor)
    start_dt = datetime.combine(days[0], time.min)
    end_dt = datetime.combine(days[-1] + timedelta(days=1), time.min)

    manual = get_manual_slots(db, user_id, start_dt, end_dt)
    rendered: List[RenderedSlot] = [
        RenderedSlot(
            start_at=s.start_at,
            end_at=s.end_at,
            kind=s.kind,
            note=s.note,
            slot_id=s.id,
            editable=viewer_is_self,
            source="manual",
        )
        for s in manual
    ]
    rendered.extend(get_deadline_slots(db, user_id, start_dt, end_dt))

    hours = list(range(DAY_START_HOUR, DAY_END_HOUR))
    grid: List[List[List[RenderedSlot]]] = [
        [[] for _ in hours] for _ in days
    ]
    for rs in rendered:
        s = rs.start_at
        e = rs.end_at
        for di, day in enumerate(days):
            day_start = datetime.combine(day, time(DAY_START_HOUR))
            day_end = datetime.combine(day, time(DAY_END_HOUR))
            if e <= day_start or s >= day_end:
                continue
            seg_start = max(s, day_start)
            seg_end = min(e, day_end)
            start_h = seg_start.hour
            end_h = seg_end.hour + (1 if seg_end.minute > 0 else 0)
            for h in range(start_h, min(end_h, DAY_END_HOUR)):
                idx = h - DAY_START_HOUR
                if 0 <= idx < len(hours):
                    grid[di][idx].append(rs)

    return {
        "days": days,
        "hours": hours,
        "grid": grid,
        "slots": rendered,
    }


@dataclass
class CalendarEvent:
    kind: str  # "deadline" | "slot"
    name: str
    color: Optional[str]
    task_id: Optional[int]
    start_at: datetime
    end_at: Optional[datetime]


def month_bounds(anchor: date) -> tuple[date, date]:
    first = anchor.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return first, nxt


def month_grid(anchor: date) -> List[List[date]]:
    first, nxt = month_bounds(anchor)
    grid_start = first - timedelta(days=first.weekday())
    weeks: List[List[date]] = []
    cur = grid_start
    while cur < nxt or len(weeks) < 6:
        week = [cur + timedelta(days=i) for i in range(7)]
        weeks.append(week)
        cur += timedelta(days=7)
        if len(weeks) >= 6 and cur >= nxt:
            break
    return weeks


def render_month(db: Session, user_id: int, anchor: date) -> dict:
    first, nxt = month_bounds(anchor)
    grid = month_grid(anchor)
    grid_start = grid[0][0]
    grid_end = grid[-1][-1] + timedelta(days=1)

    start_dt = datetime.combine(grid_start, time.min)
    end_dt = datetime.combine(grid_end, time.min)

    by_day: dict[date, list[CalendarEvent]] = {}

    tasks = (
        db.query(Task)
        .filter(
            Task.assignee_id == user_id,
            Task.ended_at.isnot(None),
            Task.ended_at >= start_dt,
            Task.ended_at < end_dt,
        )
        .all()
    )
    for t in tasks:
        d = t.ended_at.date()
        by_day.setdefault(d, []).append(CalendarEvent(
            kind="deadline",
            name=t.name,
            color=t.color,
            task_id=t.id,
            start_at=t.ended_at,
            end_at=None,
        ))

    slots = get_manual_slots(db, user_id, start_dt, end_dt)
    for s in slots:
        d = s.start_at.date()
        by_day.setdefault(d, []).append(CalendarEvent(
            kind="slot",
            name=s.note or s.kind,
            color=None,
            task_id=None,
            start_at=s.start_at,
            end_at=s.end_at,
        ))

    for d in by_day:
        by_day[d].sort(key=lambda e: e.start_at)

    return {
        "weeks": grid,
        "events_by_day": by_day,
        "month_first": first,
    }


def add_slot(db: Session, user_id: int, start_at: datetime, end_at: datetime, kind: str, note: Optional[str]) -> AvailabilitySlot:
    if kind not in KINDS:
        kind = "busy"
    slot = AvailabilitySlot(
        user_id=user_id,
        start_at=start_at,
        end_at=end_at,
        kind=kind,
        note=note or None,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def delete_slot(db: Session, slot_id: int, user_id: int) -> bool:
    slot = db.get(AvailabilitySlot, slot_id)
    if slot is None or slot.user_id != user_id:
        return False
    db.delete(slot)
    db.commit()
    return True
