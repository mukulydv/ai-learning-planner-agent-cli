"""Deterministic schedule generation.

Sequencing micro-tasks into calendar days is arithmetic, not language —
so it is done in plain Python rather than by an LLM. The LLM-facing logic
(time parsing, decomposition, review) lives in the agents package.
"""
import datetime
from typing import List

from schemas import MicroTask, Milestone, ScheduleDay, ScheduledTask, TimeAllocation


def generate_schedule(
    tasks: List[MicroTask],
    allocation: TimeAllocation,
    start_date: datetime.date,
) -> List[ScheduleDay]:
    """Sequences micro-tasks into a day-wise chronological plan.

    Splits a task across days when it exceeds the remaining daily capacity.
    """
    schedule: List[ScheduleDay] = []
    current_date = start_date

    weekday_limit_mins = int(allocation.weekday_hours * 60)
    weekend_limit_mins = int(allocation.weekend_hours * 60)

    if weekday_limit_mins <= 0 and weekend_limit_mins <= 0:
        raise ValueError("Both weekday and weekend availability are zero; cannot build a schedule.")

    task_queue = [
        {
            "title": t.title,
            "description": t.description,
            "remaining_mins": t.estimated_duration_minutes,
            "priority": t.priority,
            "sequence": t.sequence,
            "milestone_id": t.milestone_id,
        }
        for t in tasks
    ]

    while task_queue:
        is_weekend = current_date.weekday() in (5, 6)
        daily_limit = weekend_limit_mins if is_weekend else weekday_limit_mins

        if daily_limit <= 0:
            schedule.append(ScheduleDay(
                date=current_date,
                day_name=current_date.strftime("%A"),
                is_weekend=is_weekend,
                allocated_tasks=[],
                limit_minutes=0,
                used_minutes=0,
                notes="Rest Day (No availability)",
            ))
            current_date += datetime.timedelta(days=1)
            continue

        day_tasks: List[ScheduledTask] = []
        used_mins = 0

        while task_queue and used_mins < daily_limit:
            current_task = task_queue[0]
            remaining_cap = daily_limit - used_mins

            if current_task["remaining_mins"] <= remaining_cap:
                day_tasks.append(ScheduledTask(
                    title=current_task["title"],
                    description=current_task["description"],
                    duration_minutes=current_task["remaining_mins"],
                    priority=current_task["priority"],
                    sequence=current_task["sequence"],
                    milestone_id=current_task["milestone_id"],
                    part=None,
                ))
                used_mins += current_task["remaining_mins"]
                task_queue.pop(0)
            else:
                allocated_chunk = remaining_cap
                if allocated_chunk > 0:
                    day_tasks.append(ScheduledTask(
                        title=current_task["title"],
                        description=current_task["description"],
                        duration_minutes=allocated_chunk,
                        priority=current_task["priority"],
                        sequence=current_task["sequence"],
                        milestone_id=current_task["milestone_id"],
                        part="Partially completed - remaining shifted to next study day",
                    ))
                    used_mins += allocated_chunk
                    current_task["remaining_mins"] -= allocated_chunk
                break

        schedule.append(ScheduleDay(
            date=current_date,
            day_name=current_date.strftime("%A"),
            is_weekend=is_weekend,
            allocated_tasks=day_tasks,
            limit_minutes=daily_limit,
            used_minutes=used_mins,
            notes="",
        ))
        current_date += datetime.timedelta(days=1)

    return schedule


def format_schedule_markdown(
    schedule: List[ScheduleDay],
    milestones: List[Milestone] = None,
    sources: List[str] = None,
) -> str:
    """Formats milestones and the day-wise schedule into readable Markdown."""
    md = ["# Chronological Study & Preparation Schedule", ""]

    if sources:
        md.append("### Sources Consulted (via FAISS retrieval)")
        md.extend(f"- {s}" for s in sources)
        md.append("")

    if milestones:
        md.append("### Milestones")
        for m in milestones:
            md.append(f"{m.sequence}. **{m.title}** — {m.description}")
        md.append("")

    md.append("| Date | Day | Tasks | Duration | Capacity Limit | Notes |")
    md.append("| --- | --- | --- | --- | --- | --- |")

    for day in schedule:
        date_str = day.date.strftime("%Y-%m-%d")
        limit_str = f"{day.limit_minutes / 60:.1f} hrs"

        if not day.allocated_tasks:
            md.append(f"| {date_str} | {day.day_name} | *Rest / Catch-up* | 0 mins | {limit_str} | {day.notes or 'No tasks allocated'} |")
            continue

        task_entries = []
        duration_entries = []
        for t in day.allocated_tasks:
            part_suffix = f" ({t.part})" if t.part else ""
            task_entries.append(f"**{t.title}** (Seq {t.sequence}): {t.description}{part_suffix}")
            duration_entries.append(f"{t.duration_minutes} mins")

        tasks_cell = "<br><br>".join(task_entries)
        durations_cell = "<br>".join(duration_entries)
        md.append(f"| {date_str} | {day.day_name} | {tasks_cell} | {durations_cell} | {limit_str} | {day.notes} |")

    return "\n".join(md)
