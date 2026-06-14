import os
import datetime
from typing import List, Tuple, Dict, Any
from pydantic import BaseModel, Field, field_validator, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# =====================================================================
# 1. Schemas & Guardrails
# =====================================================================

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


class MicroTask(BaseModel):
    task_id: str = Field(description="Unique short identifier (e.g. task_01)")
    title: str = Field(description="Clear, action-oriented name of the micro-task")
    description: str = Field(description="Detailed explanation of what needs to be done")
    estimated_duration_minutes: int = Field(description="Estimated duration of the task in minutes")
    priority: str = Field(description="Priority level: High, Medium, or Low")
    sequence: int = Field(description="The execution sequence order (1-indexed)")

    @field_validator('estimated_duration_minutes')
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Estimated duration must be a positive integer greater than 0.")
        if v > 480: # 8 hours
            raise ValueError("A single micro-task should not exceed 480 minutes (8 hours). Please decompose it further.")
        return v


class DecomposedTasks(BaseModel):
    goal: str = Field(description="The user's original learning or preparation goal")
    tasks: List[MicroTask] = Field(description="Ordered list of micro-tasks to achieve the goal")

    @field_validator('tasks')
    @classmethod
    def validate_tasks(cls, v: List[MicroTask]) -> List[MicroTask]:
        if not v:
            raise ValueError("Must decompose into at least one micro-task.")
        
        # Check for sequence uniqueness and order
        sequences = [t.sequence for t in v]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Each micro-task must have a unique sequence number.")
        return sorted(v, key=lambda x: x.sequence)

# =====================================================================
# 2. Time-Allocation Parser
# =====================================================================

def parse_time_allocation(user_input: str, llm: ChatGoogleGenerativeAI) -> TimeAllocation:
    """Parses natural language availability into a structured TimeAllocation model."""
    parser_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an assistant that extracts daily study/work capacity from user descriptions.\n"
            "Extract daily limits for weekdays (Monday-Friday) and weekends (Saturday-Sunday) in hours.\n"
            "If only one limit is given, assume it applies to all days.\n"
            "If no hours are specified, default to 2.0 hours for weekdays and 4.0 hours for weekends.\n"
            "Adhere strictly to the requested schema."
        )),
        ("human", "User availability input: {user_input}")
    ])
    
    structured_llm = llm.with_structured_output(TimeAllocation)
    chain = parser_prompt | structured_llm
    
    # Run parsing and validate
    parsed: TimeAllocation = chain.invoke({"user_input": user_input})
    return parsed

# =====================================================================
# 3. Task-Decomposition Engine
# =====================================================================

def decompose_goal(
    goal: str, 
    context: str, 
    llm: ChatGoogleGenerativeAI, 
    feedback_notes: str = ""
) -> DecomposedTasks:
    """Decomposes a goal into sequential micro-tasks using LLM structured output.
    
    Optionally accepts external context and previous feedback to refine decomposition.
    """
    system_instructions = (
        "You are an expert curriculum developer and task planning agent.\n"
        "Your job is to break down the user's primary goal into small, concrete, and sequential micro-tasks.\n"
        "Each task should have a clear title, description, order (sequence), priority, and estimated duration in minutes.\n"
        "Keep each micro-task duration between 30 and 180 minutes. If a task takes longer, split it into smaller tasks.\n"
        "Integrate details from the user's uploaded context (e.g. skills they already have or background context) if provided.\n"
        "Do not repeat topics the user already knows well as per the context, focus on bridging gaps.\n"
    )
    
    if feedback_notes:
        system_instructions += f"\nCRITICAL: Address the following user feedback/modifications in the task list:\n{feedback_notes}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_instructions),
        ("human", "Goal: {goal}\n\nContext:\n{context}")
    ])
    
    structured_llm = llm.with_structured_output(DecomposedTasks)
    chain = prompt | structured_llm
    
    decomposed: DecomposedTasks = chain.invoke({"goal": goal, "context": context})
    return decomposed

# =====================================================================
# 4. Calendar/Schedule Generator
# =====================================================================

def generate_schedule(
    tasks: List[MicroTask],
    allocation: TimeAllocation,
    start_date: datetime.date
) -> List[Dict[str, Any]]:
    """Sequences micro-tasks into a structured, day-wise chronological plan.
    
    Handles task splits if a single task exceeds the daily capacity.
    """
    schedule = []
    current_date = start_date
    
    # Convert hours to minutes
    weekday_limit_mins = int(allocation.weekday_hours * 60)
    weekend_limit_mins = int(allocation.weekend_hours * 60)
    
    task_queue = []
    # Copy tasks to a mutable queue structure (name, desc, remaining_mins, priority, original_seq)
    for t in tasks:
        task_queue.append({
            "title": t.title,
            "description": t.description,
            "remaining_mins": t.estimated_duration_minutes,
            "priority": t.priority,
            "sequence": t.sequence
        })
        
    while task_queue:
        # Determine day capacity
        is_weekend = current_date.weekday() in (5, 6) # Saturday=5, Sunday=6
        daily_limit = weekend_limit_mins if is_weekend else weekday_limit_mins
        
        # If daily limit is 0, skip this day (rest day / unavailable)
        if daily_limit <= 0:
            schedule.append({
                "date": current_date,
                "day_name": current_date.strftime("%A"),
                "is_weekend": is_weekend,
                "allocated_tasks": [],
                "limit_minutes": 0,
                "used_minutes": 0,
                "notes": "Rest Day (No availability)"
            })
            current_date += datetime.timedelta(days=1)
            continue
            
        day_tasks = []
        used_mins = 0
        
        while task_queue and used_mins < daily_limit:
            current_task = task_queue[0]
            remaining_cap = daily_limit - used_mins
            
            # If the task fits in the remaining time for the day
            if current_task["remaining_mins"] <= remaining_cap:
                day_tasks.append({
                    "title": current_task["title"],
                    "description": current_task["description"],
                    "duration_minutes": current_task["remaining_mins"],
                    "priority": current_task["priority"],
                    "sequence": current_task["sequence"],
                    "part": None
                })
                used_mins += current_task["remaining_mins"]
                task_queue.pop(0) # Fully done
            else:
                # The task is larger than the remaining capacity. Allocate what fits and split it.
                allocated_chunk = remaining_cap
                if allocated_chunk > 0:
                    day_tasks.append({
                        "title": current_task["title"],
                        "description": current_task["description"],
                        "duration_minutes": allocated_chunk,
                        "priority": current_task["priority"],
                        "sequence": current_task["sequence"],
                        "part": "Partially completed - remaining shifted to next study day"
                    })
                    used_mins += allocated_chunk
                    current_task["remaining_mins"] -= allocated_chunk
                break # Day is full, move to next day
                
        schedule.append({
            "date": current_date,
            "day_name": current_date.strftime("%A"),
            "is_weekend": is_weekend,
            "allocated_tasks": day_tasks,
            "limit_minutes": daily_limit,
            "used_minutes": used_mins,
            "notes": ""
        })
        
        current_date += datetime.timedelta(days=1)
        
    return schedule


def format_schedule_markdown(schedule: List[Dict[str, Any]], sources: List[str] = None) -> str:
    """Formats the day-wise schedule dict into a readable Markdown table representation."""
    md = []
    md.append("# Chronological Study & Preparation Schedule")
    md.append("")
    
    if sources:
        md.append("### Sources Consulted")
        for s in sources:
            md.append(f"- {s}")
        md.append("")
        
    md.append("| Date | Day | Tasks | Duration | Capacity Limit | Notes |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    
    for day in schedule:
        date_str = day["date"].strftime("%Y-%m-%d")
        day_name = day["day_name"]
        limit_str = f"{day['limit_minutes'] / 60:.1f} hrs"
        
        if not day["allocated_tasks"]:
            md.append(f"| {date_str} | {day_name} | *Rest / Catch-up* | 0 mins | {limit_str} | {day['notes'] or 'No tasks allocated'} |")
            continue
            
        # Combine multiple tasks into the cell
        task_entries = []
        duration_entries = []
        for t in day["allocated_tasks"]:
            part_suffix = f" ({t['part']})" if t['part'] else ""
            task_entries.append(f"**{t['title']}** (Seq {t['sequence']}): {t['description']}{part_suffix}")
            duration_entries.append(f"{t['duration_minutes']} mins")
            
        tasks_cell = "<br><br>".join(task_entries)
        durations_cell = "<br>".join(duration_entries)
        
        md.append(f"| {date_str} | {day_name} | {tasks_cell} | {durations_cell} | {limit_str} | {day['notes']} |")
        
    return "\n".join(md)
