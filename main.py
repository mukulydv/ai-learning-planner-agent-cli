import datetime
import os
import uuid

from colorama import Fore, Style, init
from dotenv import load_dotenv

# Initialize colorama for colored console output
init(autoreset=True)

# Load environment variables before importing the agents (they read GEMINI_API_KEY)
load_dotenv()

from langgraph.types import Command

from agents import build_graph

AGENT_LABELS = {
    "intake": "INTAKE AGENT",
    "context": "CONTEXT AGENT (RAG)",
    "decomposer": "DECOMPOSER AGENT",
    "scheduler": "SCHEDULER AGENT",
    "reviewer": "REVIEWER AGENT",
    "human": "HUMAN-IN-THE-LOOP",
}

AGENT_COLORS = {
    "intake": Fore.BLUE,
    "context": Fore.CYAN,
    "decomposer": Fore.MAGENTA,
    "scheduler": Fore.GREEN,
    "reviewer": Fore.YELLOW,
    "human": Fore.WHITE,
}


def print_banner():
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}┌─────────────────────────────────────────────────────────┐
│           {Fore.YELLOW}AI LEARNING PLANNER — MULTI-AGENT CLI{Fore.CYAN}         │
│   LangGraph Orchestration · FAISS RAG · HITL Refinement  │
└─────────────────────────────────────────────────────────┘
"""
    print(banner)


def stream_until_interrupt(graph, config, payload):
    """Streams the graph, printing live agent events.

    Returns the interrupt payload when the graph pauses for human review,
    or None when the run finished.
    """
    interrupt_payload = None
    for mode, chunk in graph.stream(payload, config=config, stream_mode=["custom", "updates"]):
        if mode == "custom":
            agent = chunk.get("agent", "?")
            status = chunk.get("status", "")
            message = chunk.get("message", "")
            color = AGENT_COLORS.get(agent, Fore.WHITE)
            label = AGENT_LABELS.get(agent, agent.upper())
            print(f"{color}[{label}] {Style.BRIGHT}{status.upper():<10}{Style.NORMAL} {message}")
        elif mode == "updates" and "__interrupt__" in chunk:
            interrupt_payload = chunk["__interrupt__"][0].value
    return interrupt_payload


def main():
    print_banner()

    if not os.environ.get("GEMINI_API_KEY"):
        print(f"{Fore.RED}Error: GEMINI_API_KEY not found in environment or .env file.")
        return

    graph = build_graph()

    while True:  # Outer questionnaire loop ("start over" re-enters here)
        print(f"\n{Fore.GREEN}[1/3] PLAN DETAILS & GOALS")
        goal = input("What is your main preparation or learning goal? (e.g. 'Learn LangChain'): ").strip()
        while not goal:
            goal = input(f"{Fore.RED}Goal cannot be empty. Please enter your goal: ").strip()

        print(f"\n{Fore.GREEN}[2/3] TIME AVAILABILITY")
        weekday_input = input("Daily study limit for Weekdays (e.g. '2.5 hours', '120 mins') [default: 2 hours]: ").strip() or "2.0 hours"
        weekend_input = input("Daily study limit for Weekends (e.g. '4 hours', '240 mins') [default: 4 hours]: ").strip() or "4.0 hours"

        print(f"\n{Fore.GREEN}[3/3] EXTERNAL SKILLS & CONTEXT")
        load_context_opt = input("Ingest 'source_for_context' folder into the FAISS index? (y/n) [default: y]: ").strip().lower()
        use_context = load_context_opt not in ('n', 'no')

        start_date_str = input("Enter start date (YYYY-MM-DD) [default: today]: ").strip()
        try:
            start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else datetime.date.today()
        except ValueError:
            print(f"{Fore.YELLOW}Invalid format. Defaulting to today's date.")
            start_date = datetime.date.today()

        # Each planning session is a fresh LangGraph thread.
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        payload = {
            "goal": goal,
            "raw_availability": f"Weekdays: {weekday_input}. Weekends: {weekend_input}.",
            "start_date": start_date.isoformat(),
            "use_context": use_context,
            "feedback_notes": "",
            "auto_revision_count": 0,
        }

        print(f"\n{Fore.MAGENTA}{Style.BRIGHT}⚙️ Launching multi-agent orchestration...\n")

        try:
            interrupt_payload = stream_until_interrupt(graph, config, payload)
        except Exception as e:
            print(f"\n{Fore.RED}Error running the agent pipeline: {e}")
            input("Press Enter to try adjusting inputs...")
            continue

        # HITL loop: the graph pauses at the human node until approve.
        while interrupt_payload is not None:
            print(f"\n{Fore.GREEN}{Style.BRIGHT}=== DRAFT STUDY PLAN ===")
            print(interrupt_payload.get("schedule_markdown", "(no schedule produced)"))
            print(f"{Fore.GREEN}{Style.BRIGHT}========================\n")

            print(f"{Fore.YELLOW}{Style.BRIGHT}HUMAN-IN-THE-LOOP INTERCEPTOR")
            print("Choose an option:")
            print(f" [1] {Fore.GREEN}Approve and Finalize this plan")
            print(f" [2] {Fore.CYAN}Request changes to the tasks (Feedback Refinement Loop)")
            print(f" [3] {Fore.CYAN}Adjust time availability limits")
            print(f" [4] {Fore.RED}Discard and start over")
            choice = input("Enter choice (1/2/3/4): ").strip()

            if choice == "2":
                feedback = input("\nDescribe the changes you want (e.g. 'Make task 1 longer', 'add a mock interview at the end'): ").strip()
                if not feedback:
                    print("No feedback provided. Keeping the current plan on screen.")
                    continue
                resume_value = {"action": "feedback", "feedback": feedback}
            elif choice == "3":
                weekday_input = input("New weekday limit (e.g. '2.5 hours'): ").strip() or "2.0 hours"
                weekend_input = input("New weekend limit (e.g. '4 hours'): ").strip() or "4.0 hours"
                resume_value = {
                    "action": "adjust_time",
                    "raw_availability": f"Weekdays: {weekday_input}. Weekends: {weekend_input}.",
                }
            elif choice == "4":
                print(f"{Fore.YELLOW}Starting over...")
                interrupt_payload = None
                break
            else:
                resume_value = {"action": "approve"}

            print(f"\n{Fore.MAGENTA}{Style.BRIGHT}⚙️ Resuming multi-agent orchestration...\n")
            try:
                interrupt_payload = stream_until_interrupt(graph, config, Command(resume=resume_value))
            except Exception as e:
                print(f"\n{Fore.RED}Error running the agent pipeline: {e}")
                break

            if interrupt_payload is None and resume_value.get("action") == "approve":
                final_state = graph.get_state(config).values
                markdown = final_state.get("schedule_markdown", "")
                print(f"\n{Fore.GREEN}✓ Plan approved!")
                export_opt = input("Export this plan to a file? (Enter filename like 'plan.md' or press Enter to skip): ").strip()
                if export_opt:
                    try:
                        with open(export_opt, 'w', encoding='utf-8') as f:
                            f.write(markdown)
                        print(f"{Fore.GREEN}{Style.BRIGHT}✓ Plan successfully saved to '{export_opt}'")
                    except Exception as e:
                        print(f"{Fore.RED}❌ Error saving file: {e}")
                print(f"\n{Fore.YELLOW}{Style.BRIGHT}Thank you for using the AI Learning Planner! Goodbye!")
                return


if __name__ == "__main__":
    main()
