import { Component, computed, inject, signal } from '@angular/core';
import { OrchestratorService } from './orchestrator.service';

@Component({
  selector: 'app-plan-view',
  template: `
    @if (orchestrator.isBusy() && !snapshot()) {
      <!-- shimmer skeleton while agents are thinking -->
      <div class="glass p-6 md:p-8 animate-enter space-y-4">
        <div class="shimmer h-6 w-52"></div>
        <div class="shimmer h-20 w-full"></div>
        <div class="shimmer h-20 w-full" style="animation-delay: 0.2s"></div>
        <div class="shimmer h-20 w-2/3" style="animation-delay: 0.4s"></div>
      </div>
    } @else if (snapshot(); as snap) {
      <div class="glass p-6 md:p-8 animate-enter">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h2 class="text-lg font-semibold text-white">
              {{ orchestrator.phase() === 'done' ? 'Final plan' : 'Draft plan' }}
              @if (orchestrator.phase() === 'done') { <span class="ml-1">🎉</span> }
            </h2>
            <p class="text-sm text-slate-400">
              {{ snap.tasks.length }} micro-tasks · {{ snap.milestones.length }} milestones
              · {{ snap.schedule.length }} days
              @if (snap.allocation) {
                · {{ snap.allocation.weekday_hours }}h weekdays / {{ snap.allocation.weekend_hours }}h weekends
              }
            </p>
          </div>
          <div class="flex gap-2">
            <button (click)="tab.set('milestones')" [class]="tabClass('milestones')">Milestones</button>
            <button (click)="tab.set('schedule')" [class]="tabClass('schedule')">Calendar</button>
            <button (click)="download(snap.schedule_markdown)"
              class="rounded-lg px-4 py-2 text-sm font-medium border border-white/10 bg-white/5 text-slate-300
                     transition-all duration-300 hover:text-white hover:border-cyan-400/50
                     hover:shadow-[0_0_18px_rgba(34,211,238,0.2)]">⬇ Export .md</button>
          </div>
        </div>

        @if (snap.sources.length) {
          <div class="flex flex-wrap items-center gap-2 mb-6">
            <span class="text-xs text-slate-500 uppercase tracking-wider">FAISS sources:</span>
            @for (source of snap.sources; track source) {
              <span class="text-xs px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-400/25 text-cyan-300">
                📄 {{ source }}
              </span>
            }
          </div>
        }

        @if (tab() === 'milestones') {
          <!-- milestone timeline with grouped tasks -->
          <div class="space-y-5">
            @for (milestone of snap.milestones; track milestone.milestone_id; let i = $index) {
              <div class="relative pl-8 animate-enter" [style.animation-delay]="(i * 90) + 'ms'">
                <div class="absolute left-0 top-1 h-6 w-6 rounded-full grid place-items-center text-[11px] font-bold
                            bg-gradient-to-br from-indigo-400 to-fuchsia-500 text-white
                            shadow-[0_0_14px_rgba(168,85,247,0.45)]">{{ milestone.sequence }}</div>
                @if (i < snap.milestones.length - 1) {
                  <div class="absolute left-3 top-8 bottom-[-14px] w-px bg-gradient-to-b from-fuchsia-500/40 to-transparent"></div>
                }
                <h3 class="font-semibold text-white">{{ milestone.title }}</h3>
                <p class="text-sm text-slate-400 mb-3">{{ milestone.description }}</p>
                <div class="grid gap-2">
                  @for (task of tasksFor(milestone.milestone_id); track task.task_id) {
                    <div class="glass-inset px-4 py-3 flex items-center justify-between gap-4 transition-all
                                duration-300 hover:bg-white/10 hover:translate-x-1">
                      <div class="min-w-0">
                        <p class="text-sm font-medium text-slate-200 truncate">
                          <span class="text-slate-500 mr-1.5">{{ task.sequence }}.</span>{{ task.title }}
                        </p>
                        <p class="text-xs text-slate-500 truncate">{{ task.description }}</p>
                      </div>
                      <div class="flex items-center gap-2 shrink-0">
                        <span class="text-[11px] px-2 py-0.5 rounded-full border" [class]="priorityClass(task.priority)">
                          {{ task.priority }}
                        </span>
                        <span class="text-xs text-slate-400 tabular-nums">{{ task.estimated_duration_minutes }}m</span>
                      </div>
                    </div>
                  }
                </div>
              </div>
            }
          </div>
        } @else {
          <!-- day-wise calendar -->
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            @for (day of snap.schedule; track day.date; let i = $index) {
              <div class="glass-inset p-4 animate-enter transition-all duration-300 hover:bg-white/10 hover:-translate-y-1"
                   [style.animation-delay]="(i * 60) + 'ms'"
                   [class.opacity-60]="!day.allocated_tasks.length">
                <div class="flex items-center justify-between mb-2.5">
                  <p class="text-sm font-semibold" [class]="day.is_weekend ? 'text-fuchsia-300' : 'text-indigo-300'">
                    {{ day.day_name }} <span class="text-slate-500 font-normal">{{ day.date }}</span>
                  </p>
                  <span class="text-[11px] text-slate-500 tabular-nums">
                    {{ day.used_minutes }}/{{ day.limit_minutes }}m
                  </span>
                </div>
                <!-- capacity bar -->
                <div class="h-1.5 rounded-full bg-white/8 mb-3 overflow-hidden">
                  <div class="h-full rounded-full bg-gradient-to-r from-indigo-400 to-fuchsia-400 transition-all duration-700"
                       [style.width.%]="day.limit_minutes ? (day.used_minutes / day.limit_minutes) * 100 : 0"></div>
                </div>
                @if (day.allocated_tasks.length) {
                  <ul class="space-y-1.5">
                    @for (task of day.allocated_tasks; track $index) {
                      <li class="text-xs text-slate-300 flex justify-between gap-2">
                        <span class="truncate">{{ task.title }}@if (task.part) { <span class="text-amber-400/80">*</span> }</span>
                        <span class="text-slate-500 tabular-nums shrink-0">{{ task.duration_minutes }}m</span>
                      </li>
                    }
                  </ul>
                } @else {
                  <p class="text-xs text-slate-500 italic">{{ day.notes || 'Rest / catch-up' }}</p>
                }
              </div>
            }
          </div>
          <p class="text-[11px] text-slate-500 mt-3"><span class="text-amber-400/80">*</span> split across days to fit the daily capacity</p>
        }
      </div>
    }
  `,
})
export class PlanView {
  protected readonly orchestrator = inject(OrchestratorService);
  protected readonly tab = signal<'milestones' | 'schedule'>('milestones');
  protected readonly snapshot = computed(() => this.orchestrator.snapshot());

  protected tabClass(tab: string): string {
    const base = 'rounded-lg px-4 py-2 text-sm font-medium border transition-all duration-300 ';
    return this.tab() === tab
      ? base + 'border-indigo-400/60 bg-indigo-500/15 text-indigo-200'
      : base + 'border-white/10 bg-white/5 text-slate-400 hover:text-white hover:border-white/25';
  }

  protected tasksFor(milestoneId: string) {
    return this.snapshot()?.tasks.filter((t) => t.milestone_id === milestoneId) ?? [];
  }

  protected priorityClass(priority: string): string {
    switch ((priority || '').toLowerCase()) {
      case 'high': return 'border-rose-400/30 bg-rose-500/10 text-rose-300';
      case 'medium': return 'border-amber-400/30 bg-amber-500/10 text-amber-300';
      default: return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    }
  }

  protected download(markdown: string): void {
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'study-plan.md';
    link.click();
    URL.revokeObjectURL(url);
  }
}
