"""Shared LangGraph state passed between agents."""
from typing import List, Optional
from typing_extensions import TypedDict

from schemas import LearningPlan, ScheduleDay, TimeAllocation


class PlannerState(TypedDict, total=False):
    # Inputs
    goal: str
    raw_availability: str
    start_date: str          # ISO date string (YYYY-MM-DD)
    use_context: bool

    # Intake agent output
    allocation: Optional[TimeAllocation]

    # Context agent (RAG) output
    retrieved_context: str
    context_summary: str
    sources: List[str]

    # Decomposer agent output
    plan: Optional[LearningPlan]

    # Scheduler agent output
    schedule: List[ScheduleDay]
    schedule_markdown: str

    # Reviewer agent output
    review_approved: bool
    reviewer_notes: str
    auto_revision_count: int

    # Human-in-the-loop
    feedback_notes: str
    approved: bool
    route: str               # set by human_review to steer the next hop
