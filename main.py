import os
import datetime
from dotenv import load_dotenv
from colorama import init, Fore, Back, Style

# Initialize colorama for colored console output
init(autoreset=True)

# Load environment variables
load_dotenv()

# Import Langchain model and tools
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from tools import load_context_data
from planner import (
    parse_time_allocation,
    decompose_goal,
    generate_schedule,
    format_schedule_markdown,
    TimeAllocation,
    DecomposedTasks
)

def print_banner():
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}┌─────────────────────────────────────────────────────────┐
│              {Fore.YELLOW}AI TIME TABLE PLANNER AGENT{Fore.CYAN}                │
│       Dynamic Task Decomposition & Scheduling System    │
└─────────────────────────────────────────────────────────┘
"""
    print(banner)

def get_valid_time_allocation(llm: ChatGoogleGenerativeAI) -> TimeAllocation:
    """Asks for time availability and validates it using TimeAllocation Pydantic schema."""
    while True:
        try:
            print(f"\n{Fore.GREEN}[1/3] TIME AVAILABILITY ASSIGNMENT")
            weekday_input = input("Enter daily study limit for Weekdays (e.g. '2.5 hours', '120 mins', '1.5 hrs'): ").strip()
            weekend_input = input("Enter daily study limit for Weekends (e.g. '4 hours', '240 mins', '5 hrs'): ").strip()
            
            if not weekday_input:
                weekday_input = "2.0 hours"
            if not weekend_input:
                weekend_input = "4.0 hours"
                
            combined_input = f"Weekdays: {weekday_input}. Weekends: {weekend_input}."
            
            print(f"{Fore.BLUE}Parsing availability with Gemini...")
            allocation = parse_time_allocation(combined_input, llm)
            
            # Print parsed values
            print(f"{Fore.CYAN}Parsed allocations:")
            print(f" - Weekdays: {allocation.weekday_hours:.1f} hours/day")
            print(f" - Weekends: {allocation.weekend_hours:.1f} hours/day")
            if allocation.additional_notes:
                print(f" - Notes: {allocation.additional_notes}")
                
            # If valid, return
            return allocation
            
        except ValidationError as ve:
            print(f"\n{Fore.RED}{Style.BRIGHT}❌ Guardrail Violation in Time Allocation:")
            for err in ve.errors():
                print(f"   - {err['msg']}")
            print(f"{Fore.YELLOW}Please try entering your availability again.\n")
        except Exception as e:
            print(f"\n{Fore.RED}❌ Error parsing input: {str(e)}. Please try again.")

def get_valid_decomposed_tasks(
    goal: str, 
    context: str, 
    llm: ChatGoogleGenerativeAI, 
    feedback_notes: str = ""
) -> DecomposedTasks:
    """Invokes decomposition engine and applies guardrails with retry if parsing fails validation."""
    attempts = 3
    for attempt in range(attempts):
        try:
            decomposed = decompose_goal(goal, context, llm, feedback_notes)
            return decomposed
        except ValidationError as ve:
            print(f"\n{Fore.RED}❌ Task Decomposition Validation Failed (Attempt {attempt+1}/{attempts}):")
            for err in ve.errors():
                print(f"   - {err['msg']}")
            if attempt == attempts - 1:
                raise ve
            print(f"{Fore.YELLOW}Retrying task generation with stricter formatting...")
        except Exception as e:
            print(f"\n{Fore.RED}❌ Error during decomposition: {str(e)}")
            raise e

def main():
    print_banner()
    
    # Initialize LLM
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"{Fore.RED}Error: GEMINI_API_KEY not found in environment or .env file.")
        return
        
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=api_key)
    
    # Questionnaire Loop
    while True:
        print(f"\n{Fore.GREEN}[2/3] PLAN DETAILS & GOALS")
        goal = input("What is your main preparation or learning goal? (e.g. 'Learn LangChain'): ").strip()
        while not goal:
            goal = input(f"{Fore.RED}Goal cannot be empty. Please enter your goal: ").strip()
            
        # Time availability
        allocation = get_valid_time_allocation(llm)
        
        # Context Folder Loading
        print(f"\n{Fore.GREEN}[3/3] EXTERNAL SKILLS & CONTEXT")
        load_context_opt = input("Search 'source_for_context' folder for skills/resume files? (y/n) [default: y]: ").strip().lower()
        if load_context_opt not in ('n', 'no'):
            print(f"{Fore.BLUE}Reading context files...")
            context_data = load_context_data()
            context_text = context_data["content"]
            sources_used = context_data["sources"]
            if sources_used:
                print(f"{Fore.CYAN}Found skills context. Sources read: {sources_used}")
            else:
                print(f"{Fore.YELLOW}No context files (.pdf/.txt) found in 'source_for_context'. Continuing without external context.")
        else:
            context_text = ""
            sources_used = []
            print(f"{Fore.YELLOW}Skipping external context load.")
            
        # Start date
        start_date_str = input("Enter start date (YYYY-MM-DD) [default: today]: ").strip()
        if start_date_str:
            try:
                start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"{Fore.YELLOW}Invalid format. Defaulting to today's date.")
                start_date = datetime.date.today()
        else:
            start_date = datetime.date.today()
            
        # Task Decomposition & Schedule Loop (HITL Loop)
        feedback_notes = ""
        tasks = []
        
        while True:
            print(f"\n{Fore.MAGENTA}{Style.BRIGHT}⚙️ Generating study plan with Gemini...")
            try:
                # Get tasks (with decomposition + guardrails validation)
                decomposed_data = get_valid_decomposed_tasks(goal, context_text, llm, feedback_notes)
                tasks = decomposed_data.tasks
                
                # Generate schedule
                schedule = generate_schedule(tasks, allocation, start_date)
                schedule_markdown = format_schedule_markdown(schedule, sources_used)
                
                # Display schedule to user
                print(f"\n{Fore.GREEN}{Style.BRIGHT}=== DRAFT STUDY PLAN ===")
                print(schedule_markdown)
                print(f"{Fore.GREEN}{Style.BRIGHT}========================\n")
                
                # HITL Interceptor Menu
                print(f"{Fore.YELLOW}{Style.BRIGHT}HUMAN-IN-THE-LOOP INTERCEPTOR")
                print("Choose an option:")
                print(f" [1] {Fore.GREEN}Approve and Finalize this plan")
                print(f" [2] {Fore.CYAN}Request changes to the tasks (Feedback Refinement Loop)")
                print(f" [3] {Fore.CYAN}Adjust time availability limits")
                print(f" [4] {Fore.RED}Discard and start over")
                
                choice = input("Enter choice (1/2/3/4): ").strip()
                
                if choice == "1":
                    # Export options
                    print(f"\n{Fore.GREEN}✓ Plan approved!")
                    export_opt = input("Do you want to export this plan to a file? (Enter filename like 'plan.md' or press Enter to skip): ").strip()
                    if export_opt:
                        try:
                            # Ensure folder exists
                            with open(export_opt, 'w', encoding='utf-8') as f:
                                f.write(schedule_markdown)
                            print(f"{Fore.GREEN}{Style.BRIGHT}✓ Plan successfully saved to '{export_opt}'")
                        except Exception as e:
                            print(f"{Fore.RED}❌ Error saving file: {str(e)}")
                    print(f"\n{Fore.YELLOW}{Style.BRIGHT}Thank you for using the AI Time Table Planner! Goodbye!")
                    return
                    
                elif choice == "2":
                    feedback = input("\nDescribe the changes you want (e.g. 'Make task 1 longer', 'add a mock interview at the end'): ").strip()
                    if feedback:
                        feedback_notes = feedback
                        print(f"{Fore.BLUE}Applying adjustments to the task breakdown...")
                    else:
                        print("No feedback provided. Re-rendering current schedule.")
                        
                elif choice == "3":
                    print(f"\n{Fore.GREEN}Adjust availability:")
                    allocation = get_valid_time_allocation(llm)
                    print(f"{Fore.BLUE}Re-generating schedule with new capacities...")
                    
                elif choice == "4":
                    print(f"{Fore.YELLOW}Starting over...")
                    break # Breaks the HITL loop to restart outer questionnaire
                    
            except Exception as e:
                print(f"\n{Fore.RED}Error generating schedule: {str(e)}")
                input("Press Enter to try adjusting inputs...")
                break

if __name__ == "__main__":
    main()