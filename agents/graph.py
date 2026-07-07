"""LangGraph wiring for the multi-agent planner.

Graph topology:

    START -> intake -> context -> decomposer -> scheduler -> reviewer
                                      ^                          |
                                      |     (rejected, <= budget)|
                                      +--------------------------+
                                                                 |
                                                    (approved)   v
                    +----------------------------------- human_review
                    |                  |                         |
              (adjust_time)       (feedback)                (approve)
                    v                  v                         v
                 intake           decomposer                    END

After an availability adjustment the intake agent routes straight to the
scheduler (the plan itself is unchanged), so only the calendar is rebuilt.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    context_agent,
    decomposer_agent,
    human_review,
    intake_agent,
    reviewer_agent,
    scheduler_agent,
)
from .state import PlannerState

AGENT_NODES = ["intake", "context", "decomposer", "scheduler", "reviewer", "human"]


def _route_after_intake(state: PlannerState) -> str:
    # Re-entry from adjust_time: plan already exists, only rebuild the calendar.
    return "scheduler" if state.get("plan") else "context"


def _route_after_reviewer(state: PlannerState) -> str:
    return "human" if state.get("review_approved") else "decomposer"


def _route_after_human(state: PlannerState) -> str:
    route = state.get("route", "end")
    if route in ("decomposer", "intake"):
        return route
    return END


def build_graph(checkpointer=None):
    graph = StateGraph(PlannerState)

    graph.add_node("intake", intake_agent)
    graph.add_node("context", context_agent)
    graph.add_node("decomposer", decomposer_agent)
    graph.add_node("scheduler", scheduler_agent)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("human", human_review)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _route_after_intake, {"scheduler": "scheduler", "context": "context"})
    graph.add_edge("context", "decomposer")
    graph.add_edge("decomposer", "scheduler")
    graph.add_edge("scheduler", "reviewer")
    graph.add_conditional_edges("reviewer", _route_after_reviewer, {"human": "human", "decomposer": "decomposer"})
    graph.add_conditional_edges("human", _route_after_human, {"decomposer": "decomposer", "intake": "intake", END: END})

    return graph.compile(checkpointer=checkpointer or MemorySaver())
