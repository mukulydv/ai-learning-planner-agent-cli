"""Agent node implementations for the multi-agent planner graph.

Each node is a specialised agent with a single responsibility:

- intake_agent:     parses natural-language availability into TimeAllocation
- context_agent:    RAG — ingests documents into FAISS, retrieves chunks
                    relevant to the goal and summarises the learner profile
- decomposer_agent: decomposes the goal into milestones + micro-tasks
- scheduler_agent:  deterministic calendar allocation (no LLM)
- reviewer_agent:   critiques the draft plan; can send it back for revision
- human_review:     LangGraph interrupt() for human-in-the-loop feedback

Every node emits custom stream events via get_stream_writer() so the CLI
and the dashboard can visualise which agent is working in real time.
"""
import datetime
import os
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from pydantic import ValidationError

import rag
from planner import format_schedule_markdown, generate_schedule
from schemas import LearningPlan, PlanReview, TimeAllocation
from .state import PlannerState

LLM_MODEL = "gemini-2.5-flash"
MAX_STRUCTURED_OUTPUT_ATTEMPTS = 3
MAX_AUTO_REVISIONS = 1

_llm: Optional[ChatGoogleGenerativeAI] = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment or .env file.")
        _llm = ChatGoogleGenerativeAI(model=LLM_MODEL, api_key=api_key)
    return _llm


def _emit(agent: str, status: str, message: str = "") -> None:
    """Publish a custom stream event for live agent visualisation."""
    writer = get_stream_writer()
    if writer:
        writer({"agent": agent, "status": status, "message": message})


def _invoke_structured(chain, inputs: dict, agent: str):
    """Invoke a structured-output chain with validation guardrails.

    Retries on ValidationError so a malformed LLM response never propagates
    into the rest of the pipeline.
    """
    last_error = None
    for attempt in range(1, MAX_STRUCTURED_OUTPUT_ATTEMPTS + 1):
        try:
            result = chain.invoke(inputs)
            if result is None:
                raise ValueError("LLM returned no structured output.")
            return result
        except (ValidationError, ValueError) as e:
            last_error = e
            _emit(agent, "retrying",
                  f"Structured output failed validation (attempt {attempt}/{MAX_STRUCTURED_OUTPUT_ATTEMPTS}); retrying.")
    raise last_error


# ---------------------------------------------------------------------
# Intake agent
# ---------------------------------------------------------------------

def intake_agent(state: PlannerState) -> dict:
    _emit("intake", "started", "Parsing time availability with Gemini...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an assistant that extracts daily study/work capacity from user descriptions.\n"
            "Extract daily limits for weekdays (Monday-Friday) and weekends (Saturday-Sunday) in hours.\n"
            "If only one limit is given, assume it applies to all days.\n"
            "If no hours are specified, default to 2.0 hours for weekdays and 4.0 hours for weekends.\n"
            "Adhere strictly to the requested schema."
        )),
        ("human", "User availability input: {user_input}"),
    ])
    chain = prompt | get_llm().with_structured_output(TimeAllocation)
    allocation: TimeAllocation = _invoke_structured(
        chain, {"user_input": state["raw_availability"]}, "intake")
    _emit("intake", "completed",
          f"Weekdays {allocation.weekday_hours:.1f}h/day, weekends {allocation.weekend_hours:.1f}h/day.")
    return {"allocation": allocation}


# ---------------------------------------------------------------------
# Context agent (RAG)
# ---------------------------------------------------------------------

def context_agent(state: PlannerState) -> dict:
    if not state.get("use_context", True):
        _emit("context", "skipped", "External context disabled by user.")
        return {"retrieved_context": "", "context_summary": "", "sources": []}

    _emit("context", "started", "Ingesting documents into FAISS vector store...")
    store, sources = rag.ingest()
    if store is None:
        _emit("context", "completed", "No context documents found; continuing without RAG context.")
        return {"retrieved_context": "", "context_summary": "", "sources": []}

    _emit("context", "working",
          f"Indexed {len(sources)} document(s). Retrieving chunks relevant to the goal...")
    query = (
        f"Skills, experience and prior knowledge relevant to the learning goal: {state['goal']}"
    )
    retrieved = rag.retrieve(store, query, k=6)

    _emit("context", "working", "Summarising learner profile from retrieved chunks...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a learner-profile analyst. From the retrieved resume/skills excerpts below, "
            "summarise in under 150 words: (1) skills the learner already has that relate to the goal, "
            "(2) apparent gaps to close to reach the goal. Be concrete; do not invent skills."
        )),
        ("human", "Goal: {goal}\n\nRetrieved excerpts:\n{retrieved}"),
    ])
    summary = (prompt | get_llm()).invoke({"goal": state["goal"], "retrieved": retrieved}).content

    _emit("context", "completed", f"Learner profile built from {len(sources)} source(s).")
    return {"retrieved_context": retrieved, "context_summary": summary, "sources": sources}


# ---------------------------------------------------------------------
# Decomposer agent
# ---------------------------------------------------------------------

def decomposer_agent(state: PlannerState) -> dict:
    _emit("decomposer", "started", "Decomposing goal into milestones and micro-tasks...")

    system_instructions = (
        "You are an expert curriculum developer and task planning agent.\n"
        "Break the user's goal into 2-6 outcome-oriented milestones, then into small, concrete, "
        "sequential micro-tasks. Every micro-task must reference the milestone_id it contributes to.\n"
        "Each task needs a clear title, description, sequence, priority and estimated duration in minutes.\n"
        "Keep each micro-task duration between 30 and 180 minutes; split anything longer.\n"
        "Use the learner profile to skip topics the learner already knows and focus on bridging gaps.\n"
    )
    feedback_parts = []
    if state.get("feedback_notes"):
        feedback_parts.append(f"USER FEEDBACK (must address):\n{state['feedback_notes']}")
    if state.get("reviewer_notes"):
        feedback_parts.append(f"REVIEWER INSTRUCTIONS (must address):\n{state['reviewer_notes']}")
    if feedback_parts:
        system_instructions += "\nCRITICAL revision requirements:\n" + "\n\n".join(feedback_parts)
        _emit("decomposer", "working", "Applying revision feedback to the task breakdown...")

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_instructions),
        ("human", (
            "Goal: {goal}\n\n"
            "Learner profile summary:\n{context_summary}\n\n"
            "Relevant retrieved excerpts:\n{retrieved_context}"
        )),
    ])
    chain = prompt | get_llm().with_structured_output(LearningPlan)
    plan: LearningPlan = _invoke_structured(chain, {
        "goal": state["goal"],
        "context_summary": state.get("context_summary", "(none)"),
        "retrieved_context": state.get("retrieved_context", "(none)"),
    }, "decomposer")

    _emit("decomposer", "completed",
          f"Produced {len(plan.milestones)} milestones and {len(plan.tasks)} micro-tasks.")
    # Reviewer notes are consumed by this revision; clear them.
    return {"plan": plan, "reviewer_notes": ""}


# ---------------------------------------------------------------------
# Scheduler agent (deterministic)
# ---------------------------------------------------------------------

def scheduler_agent(state: PlannerState) -> dict:
    _emit("scheduler", "started", "Allocating micro-tasks onto the calendar...")
    start_date = datetime.date.fromisoformat(state["start_date"])
    plan = state["plan"]
    schedule = generate_schedule(plan.tasks, state["allocation"], start_date)
    markdown = format_schedule_markdown(schedule, plan.milestones, state.get("sources") or [])
    _emit("scheduler", "completed", f"Scheduled {len(plan.tasks)} tasks across {len(schedule)} days.")
    return {"schedule": schedule, "schedule_markdown": markdown}


# ---------------------------------------------------------------------
# Reviewer agent
# ---------------------------------------------------------------------

def reviewer_agent(state: PlannerState) -> dict:
    auto_revisions = state.get("auto_revision_count", 0)
    if auto_revisions >= MAX_AUTO_REVISIONS:
        _emit("reviewer", "completed", "Auto-revision budget exhausted; forwarding plan for human review.")
        return {"review_approved": True}

    _emit("reviewer", "started", "Critiquing draft plan for coherence and realism...")
    plan = state["plan"]
    plan_summary = "\n".join(
        f"- [{t.sequence}] {t.title} ({t.estimated_duration_minutes} min, {t.priority}, milestone {t.milestone_id})"
        for t in plan.tasks
    )
    milestone_summary = "\n".join(f"- {m.milestone_id}: {m.title}" for m in plan.milestones)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a strict quality reviewer for study plans. Approve the plan unless there is a "
            "clear problem: illogical ordering, missing prerequisite topics for the goal, duplicated "
            "work, or unrealistic durations. If you reject, give short actionable revision instructions."
        )),
        ("human", (
            "Goal: {goal}\n\nMilestones:\n{milestones}\n\nTasks:\n{tasks}\n\n"
            "Learner profile:\n{context_summary}"
        )),
    ])
    chain = prompt | get_llm().with_structured_output(PlanReview)
    try:
        review: PlanReview = _invoke_structured(chain, {
            "goal": state["goal"],
            "milestones": milestone_summary,
            "tasks": plan_summary,
            "context_summary": state.get("context_summary", "(none)"),
        }, "reviewer")
    except (ValidationError, ValueError):
        # Reviewer is advisory; never block the pipeline on its failure.
        _emit("reviewer", "completed", "Reviewer unavailable; forwarding plan for human review.")
        return {"review_approved": True}

    if review.approved:
        _emit("reviewer", "completed", "Plan passed automated review.")
        return {"review_approved": True}

    _emit("reviewer", "completed",
          f"Plan rejected ({len(review.issues)} issue(s)); sending back to decomposer for revision.")
    return {
        "review_approved": False,
        "reviewer_notes": review.revision_instructions or "; ".join(review.issues),
        "auto_revision_count": auto_revisions + 1,
    }


# ---------------------------------------------------------------------
# Human-in-the-loop node
# ---------------------------------------------------------------------

def human_review(state: PlannerState) -> dict:
    _emit("human", "waiting", "Waiting for human review of the draft plan...")
    decision = interrupt({
        "schedule_markdown": state.get("schedule_markdown", ""),
        "options": ["approve", "feedback", "adjust_time"],
    })

    action = (decision or {}).get("action", "approve")
    if action == "feedback":
        _emit("human", "completed", "Change request received; routing back to decomposer.")
        return {"feedback_notes": decision.get("feedback", ""), "approved": False,
                "auto_revision_count": 0, "route": "decomposer"}
    if action == "adjust_time":
        _emit("human", "completed", "Availability change received; routing back to intake.")
        return {"raw_availability": decision.get("raw_availability", ""), "approved": False,
                "route": "intake"}
    _emit("human", "completed", "Plan approved by human reviewer.")
    return {"approved": True, "route": "end"}
