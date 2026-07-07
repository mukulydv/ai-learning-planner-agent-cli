import { Component, computed, inject } from '@angular/core';
import { DatePipe } from '@angular/common';
import { AGENTS } from './models';
import { OrchestratorService } from './orchestrator.service';

const ACCENTS = Object.fromEntries(AGENTS.map((a) => [a.id, a.accent]));
const NAMES = Object.fromEntries(AGENTS.map((a) => [a.id, a.name]));

@Component({
  selector: 'app-event-feed',
  imports: [DatePipe],
  template: `
    <div class="glass p-6 animate-enter h-full flex flex-col" style="animation-delay: 160ms">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-white">Activity stream</h2>
        <span class="text-xs text-slate-500">{{ feed().length }} events</span>
      </div>

      @if (!feed().length) {
        <div class="flex-1 grid place-items-center text-sm text-slate-500 py-10">
          Agent telemetry will appear here once a run starts.
        </div>
      } @else {
        <ul class="themed-scroll flex-1 space-y-2.5 overflow-y-auto pr-1 max-h-[420px]">
          @for (event of feed(); track $index) {
            <li class="glass-inset px-3.5 py-2.5 flex items-start gap-3 animate-enter">
              <span class="mt-1 h-2 w-2 shrink-0 rounded-full"
                    [style.background]="accentOf(event.agent)"
                    [style.boxShadow]="'0 0 8px ' + accentOf(event.agent)"></span>
              <div class="min-w-0">
                <p class="text-[11px] font-semibold uppercase tracking-wider"
                   [style.color]="accentOf(event.agent)">
                  {{ nameOf(event.agent) }}
                  <span class="text-slate-500 normal-case font-normal tracking-normal">
                    · {{ event.ts * 1000 | date:'HH:mm:ss' }}</span>
                </p>
                <p class="text-sm text-slate-300 break-words">{{ event.message }}</p>
              </div>
            </li>
          }
        </ul>
      }
    </div>
  `,
})
export class EventFeed {
  protected readonly orchestrator = inject(OrchestratorService);

  protected readonly feed = computed(() =>
    this.orchestrator.events()
      .filter((e) => e.type === 'agent_event' && e.message)
      .slice()
      .reverse(),
  );

  protected accentOf(agent?: string): string {
    return (agent && ACCENTS[agent]) || '#94a3b8';
  }

  protected nameOf(agent?: string): string {
    return (agent && NAMES[agent]) || 'System';
  }
}
