"""FastAPI backend for the Multi-Agent Orchestrator dashboard.

Runs the LangGraph planner in worker threads and streams every agent event
over Server-Sent Events so the Angular dashboard can visualise, live, which
sub-agent is currently handling the task.

Endpoints:
    POST /api/sessions                 start a planning run
    GET  /api/sessions/{id}/events     SSE stream of agent events
    POST /api/sessions/{id}/resume     answer a human-in-the-loop interrupt

Set SIMULATE=1 (or omit GEMINI_API_KEY) to run in simulation mode: the same
event protocol is emitted from a scripted pipeline, so the dashboard can be
demoed without burning Gemini quota.
"""
import asyncio
import datetime
import json
import os
import queue
import re
import threading
import time
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from planner import format_schedule_markdown, generate_schedule
from schemas import LearningPlan, MicroTask, Milestone, TimeAllocation

SIMULATE = os.environ.get("SIMULATE") == "1" or not os.environ.get("GEMINI_API_KEY")

app = FastAPI(title="AI Learning Planner — Multi-Agent Orchestrator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_graph = None
_graph_lock = threading.Lock()


def get_graph():
    global _graph
    with _graph_lock:
        if _graph is None:
            from agents import build_graph
            _graph = build_graph()
        return _graph


class Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.config = {"configurable": {"thread_id": session_id}}
        self.status = "running"          # running | waiting_human | done | error
        self.simulated = SIMULATE
        # Simulation-only state
        self.sim: Dict[str, Any] = {}

    def emit(self, event_type: str, **data):
        self.events.put({"type": event_type, "ts": time.time(), **data})


SESSIONS: Dict[str, Session] = {}


class StartRequest(BaseModel):
    goal: str
    weekday_availability: str = "2 hours"
    weekend_availability: str = "4 hours"
    start_date: Optional[str] = None
    use_context: bool = True


class ResumeRequest(BaseModel):
    action: str                       # approve | feedback | adjust_time
    feedback: str = ""
    weekday_availability: str = ""
    weekend_availability: str = ""


# ---------------------------------------------------------------------
# Real pipeline (LangGraph)
# ---------------------------------------------------------------------

def _state_snapshot(session: Session) -> dict:
    """Serialise the parts of graph state the dashboard renders."""
    values = get_graph().get_state(session.config).values
    plan = values.get("plan")
    allocation = values.get("allocation")
    return {
        "schedule_markdown": values.get("schedule_markdown", ""),
        "milestones": [m.model_dump() for m in plan.milestones] if plan else [],
        "tasks": [t.model_dump() for t in plan.tasks] if plan else [],
        "schedule": [d.model_dump(mode="json") for d in values.get("schedule", [])],
        "sources": values.get("sources", []),
        "allocation": allocation.model_dump() if allocation else None,
    }


def _run_graph(session: Session, payload):
    try:
        interrupted = False
        for mode, chunk in get_graph().stream(
            payload, config=session.config, stream_mode=["custom", "updates"]
        ):
            if mode == "custom":
                session.emit("agent_event", **chunk)
            elif mode == "updates" and "__interrupt__" in chunk:
                interrupted = True
        if interrupted:
            session.status = "waiting_human"
            session.emit("interrupt", **_state_snapshot(session))
        else:
            session.status = "done"
            session.emit("done", **_state_snapshot(session))
    except Exception as e:
        session.status = "error"
        session.emit("error", message=str(e))


# ---------------------------------------------------------------------
# Simulation pipeline (same event protocol, no LLM calls)
# ---------------------------------------------------------------------

def _parse_hours(text: str, default: float) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not match:
        return default
    value = float(match.group(1))
    if "min" in (text or "").lower():
        value /= 60.0
    return max(0.0, min(value, 16.0))


def _sim_plan(goal: str) -> LearningPlan:
    milestones = [
        Milestone(milestone_id="m_01", title="Foundations locked in",
                  description=f"Understand the core concepts behind: {goal}", sequence=1),
        Milestone(milestone_id="m_02", title="Hands-on fluency",
                  description="Build small working examples end to end", sequence=2),
        Milestone(milestone_id="m_03", title="Capstone ready",
                  description="Ship a portfolio-grade project and review it", sequence=3),
    ]
    raw_tasks = [
        ("Survey the landscape", "Read the official docs overview and map the key concepts.", 60, "High", "m_01"),
        ("Set up the environment", "Install tooling, create a starter project, run a hello-world.", 45, "High", "m_01"),
        ("Core concepts deep-dive", "Work through the fundamentals with notes and flashcards.", 120, "High", "m_01"),
        ("Guided tutorial build", "Follow an end-to-end tutorial, typing every line yourself.", 150, "Medium", "m_02"),
        ("Rebuild without the tutorial", "Recreate the tutorial project from memory; note the gaps.", 120, "High", "m_02"),
        ("Explore the ecosystem", "Evaluate 2-3 common libraries/patterns used in production.", 90, "Medium", "m_02"),
        ("Design the capstone", "Scope a small but real project; write a one-page design.", 60, "Medium", "m_03"),
        ("Build the capstone", "Implement the project in vertical slices.", 180, "High", "m_03"),
        ("Polish and publish", "Write the README, record a demo, push to GitHub.", 90, "Low", "m_03"),
    ]
    tasks = [
        MicroTask(task_id=f"task_{i:02d}", milestone_id=m, title=t, description=d,
                  estimated_duration_minutes=mins, priority=p, sequence=i)
        for i, (t, d, mins, p, m) in enumerate(raw_tasks, 1)
    ]
    return LearningPlan(goal=goal, milestones=milestones, tasks=tasks)


def _sim_snapshot(session: Session) -> dict:
    plan: LearningPlan = session.sim["plan"]
    allocation: TimeAllocation = session.sim["allocation"]
    start_date: datetime.date = session.sim["start_date"]
    schedule = generate_schedule(plan.tasks, allocation, start_date)
    sources = session.sim["sources"]
    return {
        "schedule_markdown": format_schedule_markdown(schedule, plan.milestones, sources),
        "milestones": [m.model_dump() for m in plan.milestones],
        "tasks": [t.model_dump() for t in plan.tasks],
        "schedule": [d.model_dump(mode="json") for d in schedule],
        "sources": sources,
        "allocation": allocation.model_dump(),
    }


def _sim_emit_sequence(session: Session, steps):
    for agent, status, message, delay in steps:
        session.emit("agent_event", agent=agent, status=status, message=message)
        time.sleep(delay)


def _run_simulation(session: Session, req: StartRequest):
    try:
        allocation = TimeAllocation(
            weekday_hours=_parse_hours(req.weekday_availability, 2.0),
            weekend_hours=_parse_hours(req.weekend_availability, 4.0),
        )
        start_date = datetime.date.fromisoformat(req.start_date) if req.start_date else datetime.date.today()
        sources = ["Reume_contents.txt", "skills.pdf"] if req.use_context else []
        session.sim = {"allocation": allocation, "start_date": start_date, "sources": sources}

        _sim_emit_sequence(session, [
            ("intake", "started", "Parsing time availability with Gemini...", 1.2),
            ("intake", "completed",
             f"Weekdays {allocation.weekday_hours:.1f}h/day, weekends {allocation.weekend_hours:.1f}h/day.", 0.4),
            ("context", "started", "Ingesting documents into FAISS vector store...", 1.6),
            ("context", "working", f"Indexed {len(sources)} document(s). Retrieving chunks relevant to the goal...", 1.2),
            ("context", "working", "Summarising learner profile from retrieved chunks...", 1.4),
            ("context", "completed", f"Learner profile built from {len(sources)} source(s).", 0.4),
            ("decomposer", "started", "Decomposing goal into milestones and micro-tasks...", 2.4),
            ("decomposer", "completed", "Produced 3 milestones and 9 micro-tasks.", 0.4),
            ("scheduler", "started", "Allocating micro-tasks onto the calendar...", 1.0),
            ("scheduler", "completed", "Scheduled 9 tasks across the calendar.", 0.4),
            ("reviewer", "started", "Critiquing draft plan for coherence and realism...", 1.8),
            ("reviewer", "completed", "Plan passed automated review.", 0.4),
            ("human", "waiting", "Waiting for human review of the draft plan...", 0.1),
        ])

        session.sim["plan"] = _sim_plan(req.goal)
        session.status = "waiting_human"
        session.emit("interrupt", **_sim_snapshot(session))
    except Exception as e:
        session.status = "error"
        session.emit("error", message=str(e))


def _resume_simulation(session: Session, req: ResumeRequest):
    try:
        if req.action == "approve":
            _sim_emit_sequence(session, [
                ("human", "completed", "Plan approved by human reviewer.", 0.5),
            ])
            session.status = "done"
            session.emit("done", **_sim_snapshot(session))
            return

        if req.action == "adjust_time":
            _sim_emit_sequence(session, [
                ("human", "completed", "Availability change received; routing back to intake.", 0.6),
                ("intake", "started", "Parsing updated time availability...", 1.2),
                ("intake", "completed", "Updated allocation parsed.", 0.4),
                ("scheduler", "started", "Rebuilding calendar with new capacities...", 1.2),
                ("scheduler", "completed", "Calendar rebuilt.", 0.4),
                ("reviewer", "started", "Re-checking plan against new availability...", 1.2),
                ("reviewer", "completed", "Plan passed automated review.", 0.4),
                ("human", "waiting", "Waiting for human review of the draft plan...", 0.1),
            ])
            session.sim["allocation"] = TimeAllocation(
                weekday_hours=_parse_hours(req.weekday_availability, 2.0),
                weekend_hours=_parse_hours(req.weekend_availability, 4.0),
            )
        else:  # feedback
            _sim_emit_sequence(session, [
                ("human", "completed", "Change request received; routing back to decomposer.", 0.6),
                ("decomposer", "started", "Applying revision feedback to the task breakdown...", 2.2),
                ("decomposer", "completed", "Revised plan produced.", 0.4),
                ("scheduler", "started", "Re-allocating micro-tasks onto the calendar...", 1.0),
                ("scheduler", "completed", "Calendar rebuilt.", 0.4),
                ("reviewer", "started", "Critiquing revised plan...", 1.6),
                ("reviewer", "completed", "Plan passed automated review.", 0.4),
                ("human", "waiting", "Waiting for human review of the draft plan...", 0.1),
            ])
            plan: LearningPlan = session.sim["plan"]
            note = (req.feedback or "requested changes").strip()
            extra = MicroTask(
                task_id=f"task_{len(plan.tasks) + 1:02d}",
                milestone_id=plan.milestones[-1].milestone_id,
                title="Feedback follow-up",
                description=f"Added per your feedback: {note}",
                estimated_duration_minutes=60,
                priority="High",
                sequence=plan.tasks[-1].sequence + 1,
            )
            session.sim["plan"] = LearningPlan(
                goal=plan.goal, milestones=plan.milestones, tasks=[*plan.tasks, extra])

        session.status = "waiting_human"
        session.emit("interrupt", **_sim_snapshot(session))
    except Exception as e:
        session.status = "error"
        session.emit("error", message=str(e))


# ---------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------

@app.post("/api/sessions")
def start_session(req: StartRequest):
    if not req.goal.strip():
        raise HTTPException(status_code=422, detail="Goal cannot be empty.")

    session = Session(str(uuid.uuid4()))
    SESSIONS[session.id] = session

    if session.simulated:
        target, args = _run_simulation, (session, req)
    else:
        payload = {
            "goal": req.goal.strip(),
            "raw_availability": f"Weekdays: {req.weekday_availability}. Weekends: {req.weekend_availability}.",
            "start_date": req.start_date or datetime.date.today().isoformat(),
            "use_context": req.use_context,
            "feedback_notes": "",
            "auto_revision_count": 0,
        }
        target, args = _run_graph, (session, payload)

    threading.Thread(target=target, args=args, daemon=True).start()
    return {"session_id": session.id, "simulated": session.simulated}


@app.post("/api/sessions/{session_id}/resume")
def resume_session(session_id: str, req: ResumeRequest):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session.")
    if session.status != "waiting_human":
        raise HTTPException(status_code=409, detail=f"Session is not waiting for human input (status: {session.status}).")

    session.status = "running"
    if session.simulated:
        threading.Thread(target=_resume_simulation, args=(session, req), daemon=True).start()
    else:
        from langgraph.types import Command
        resume_value = {"action": req.action}
        if req.action == "feedback":
            resume_value["feedback"] = req.feedback
        elif req.action == "adjust_time":
            resume_value["raw_availability"] = (
                f"Weekdays: {req.weekday_availability}. Weekends: {req.weekend_availability}."
            )
        threading.Thread(target=_run_graph, args=(session, Command(resume=resume_value)), daemon=True).start()
    return {"status": "resumed"}


@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session.")

    async def event_stream():
        while True:
            try:
                event = session.events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("done", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/health")
def health():
    return {"status": "ok", "simulated": SIMULATE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
