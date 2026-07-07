"""Pydantic schemas shared by all agents.

These models double as structured-output contracts for the LLM and as
validation guardrails: any LLM response that violates a validator raises
ValidationError, which the calling agent catches and retries with stricter
formatting instructions.
"""
import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class TimeAllocation(BaseModel):
    weekday_hours: float = Field(description="Daily time limit in hours for weekdays (Monday to Friday)")
    weekend_hours: float = Field(description="Daily time limit in hours for weekends (Saturday and Sunday)")
    additional_notes: str = Field(default="", description="Any other specific constraints or notes regarding availability")

    @field_validator('weekday_hours', 'weekend_hours')
    @classmethod
    def validate_hours(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Hours cannot be negative.")
        if v > 16.0:
            raise ValueError("Hours cannot exceed 16.0 per day to keep scheduling realistic.")
        return v


class Milestone(BaseModel):
    milestone_id: str = Field(description="Unique short identifier (e.g. m_01)")
    title: str = Field(description="Outcome-oriented name of the milestone (e.g. 'Core LangChain fluency')")
    description: str = Field(description="What the learner can do once this milestone is reached")
    sequence: int = Field(description="The order in which milestones should be achieved (1-indexed)")


class MicroTask(BaseModel):
    task_id: str = Field(description="Unique short identifier (e.g. task_01)")
    milestone_id: str = Field(description="The milestone_id this task contributes to")
    title: str = Field(description="Clear, action-oriented name of the micro-task")
    description: str = Field(description="Detailed explanation of what needs to be done")
    estimated_duration_minutes: int = Field(description="Estimated duration of the task in minutes")
    priority: str = Field(description="Priority level: High, Medium, or Low")
    sequence: int = Field(description="The execution sequence order across the whole plan (1-indexed)")

    @field_validator('estimated_duration_minutes')
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Estimated duration must be a positive integer greater than 0.")
        if v > 480:  # 8 hours
            raise ValueError("A single micro-task should not exceed 480 minutes (8 hours). Please decompose it further.")
        return v


class LearningPlan(BaseModel):
    """Structured output of the decomposer agent: milestones plus the
    micro-tasks that ladder up to them."""
    goal: str = Field(description="The user's original learning or preparation goal")
    milestones: List[Milestone] = Field(description="Ordered list of 2-6 milestones that mark measurable progress toward the goal")
    tasks: List[MicroTask] = Field(description="Ordered list of micro-tasks; every task must reference one of the milestones")

    @field_validator('milestones')
    @classmethod
    def validate_milestones(cls, v: List[Milestone]) -> List[Milestone]:
        if not v:
            raise ValueError("Must define at least one milestone.")
        sequences = [m.sequence for m in v]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Each milestone must have a unique sequence number.")
        return sorted(v, key=lambda m: m.sequence)

    @field_validator('tasks')
    @classmethod
    def validate_tasks(cls, v: List[MicroTask]) -> List[MicroTask]:
        if not v:
            raise ValueError("Must decompose into at least one micro-task.")
        sequences = [t.sequence for t in v]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Each micro-task must have a unique sequence number.")
        return sorted(v, key=lambda t: t.sequence)

    @model_validator(mode='after')
    def validate_task_milestone_links(self) -> 'LearningPlan':
        milestone_ids = {m.milestone_id for m in self.milestones}
        orphans = [t.task_id for t in self.tasks if t.milestone_id not in milestone_ids]
        if orphans:
            raise ValueError(
                f"Tasks {orphans} reference unknown milestone_ids. "
                f"Every task's milestone_id must be one of: {sorted(milestone_ids)}."
            )
        return self


class PlanReview(BaseModel):
    """Structured output of the reviewer agent's quality critique."""
    approved: bool = Field(description="True if the plan is coherent, realistic and well-sequenced; False if it needs revision")
    issues: List[str] = Field(default_factory=list, description="Concrete problems found in the plan (empty when approved)")
    revision_instructions: str = Field(default="", description="Actionable instructions for the decomposer agent to fix the issues (empty when approved)")


class ScheduledTask(BaseModel):
    title: str
    description: str
    duration_minutes: int
    priority: str
    sequence: int
    milestone_id: str = ""
    part: Optional[str] = None


class ScheduleDay(BaseModel):
    date: datetime.date
    day_name: str
    is_weekend: bool
    allocated_tasks: List[ScheduledTask]
    limit_minutes: int
    used_minutes: int
    notes: str = ""
