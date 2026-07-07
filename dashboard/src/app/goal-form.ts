import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OrchestratorService } from './orchestrator.service';

@Component({
  selector: 'app-goal-form',
  imports: [FormsModule],
  template: `
    <div class="glass p-6 md:p-8 animate-enter">
      <div class="flex items-center gap-3 mb-6">
        <div class="float-y text-3xl">🎯</div>
        <div>
          <h2 class="text-lg font-semibold text-white">Plan a new learning goal</h2>
          <p class="text-sm text-slate-400">The orchestrator will decompose it into milestones, tasks and a calendar.</p>
        </div>
      </div>

      <div class="grid gap-4">
        <label class="block">
          <span class="text-xs font-medium uppercase tracking-wider text-slate-400">Learning goal</span>
          <input
            [(ngModel)]="goal"
            [disabled]="orchestrator.isBusy()"
            placeholder="e.g. Become interview-ready in LangGraph and multi-agent systems"
            class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                   placeholder:text-slate-500 outline-none transition-all duration-300
                   focus:border-indigo-400/60 focus:bg-white/10 focus:shadow-[0_0_24px_rgba(129,140,248,0.25)]" />
        </label>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label class="block">
            <span class="text-xs font-medium uppercase tracking-wider text-slate-400">Weekday availability</span>
            <input [(ngModel)]="weekday" [disabled]="orchestrator.isBusy()" placeholder="2 hours"
              class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                     placeholder:text-slate-500 outline-none transition-all duration-300
                     focus:border-indigo-400/60 focus:bg-white/10" />
          </label>
          <label class="block">
            <span class="text-xs font-medium uppercase tracking-wider text-slate-400">Weekend availability</span>
            <input [(ngModel)]="weekend" [disabled]="orchestrator.isBusy()" placeholder="4 hours"
              class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                     placeholder:text-slate-500 outline-none transition-all duration-300
                     focus:border-indigo-400/60 focus:bg-white/10" />
          </label>
          <label class="block">
            <span class="text-xs font-medium uppercase tracking-wider text-slate-400">Start date</span>
            <input type="date" [(ngModel)]="startDate" [disabled]="orchestrator.isBusy()"
              class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                     outline-none transition-all duration-300 focus:border-indigo-400/60 focus:bg-white/10
                     [color-scheme:dark]" />
          </label>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-4 pt-1">
          <label class="flex items-center gap-2.5 cursor-pointer select-none group">
            <input type="checkbox" [(ngModel)]="useContext" [disabled]="orchestrator.isBusy()" class="peer sr-only" />
            <span class="relative h-6 w-11 rounded-full bg-white/10 border border-white/15 transition-colors duration-300
                         peer-checked:bg-indigo-500/70
                         after:absolute after:top-0.5 after:left-0.5 after:h-4.5 after:w-4.5 after:rounded-full
                         after:bg-white after:transition-transform after:duration-300 peer-checked:after:translate-x-5"></span>
            <span class="text-sm text-slate-300 group-hover:text-white transition-colors">
              RAG context <span class="text-slate-500">(FAISS over source_for_context)</span>
            </span>
          </label>

          <button
            (click)="launch()"
            [disabled]="orchestrator.isBusy() || !goal().trim()"
            class="rounded-xl px-6 py-3 text-sm font-semibold text-white transition-all duration-300
                   bg-gradient-to-r from-indigo-500 via-fuchsia-500 to-cyan-500 bg-[length:200%_100%] bg-left
                   hover:bg-right hover:shadow-[0_0_32px_rgba(168,85,247,0.4)] hover:-translate-y-0.5
                   active:translate-y-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0">
            @if (orchestrator.isBusy()) {
              <span class="thinking-dots align-middle"><span></span><span></span><span></span></span>
              <span class="ml-2">Orchestrating</span>
            } @else {
              Launch agents ⚡
            }
          </button>
        </div>
      </div>
    </div>
  `,
})
export class GoalForm {
  protected readonly orchestrator = inject(OrchestratorService);

  protected readonly goal = signal('');
  protected readonly weekday = signal('2 hours');
  protected readonly weekend = signal('4 hours');
  protected readonly startDate = signal(new Date().toISOString().slice(0, 10));
  protected readonly useContext = signal(true);

  launch(): void {
    this.orchestrator.start({
      goal: this.goal().trim(),
      weekday_availability: this.weekday() || '2 hours',
      weekend_availability: this.weekend() || '4 hours',
      start_date: this.startDate() || null,
      use_context: this.useContext(),
    });
  }
}
