import { Component, computed, inject } from '@angular/core';
import { AGENTS, AgentId } from './models';
import { OrchestratorService } from './orchestrator.service';

@Component({
  selector: 'app-agent-pipeline',
  template: `
    <div class="glass p-6 md:p-8 animate-enter" style="animation-delay: 80ms">
      <div class="flex items-center justify-between mb-8">
        <div>
          <h2 class="text-lg font-semibold text-white">Agent orchestration</h2>
          <p class="text-sm text-slate-400">LangGraph pipeline — live view of which sub-agent holds the task</p>
        </div>
        <span class="text-xs font-medium px-3 py-1.5 rounded-full border transition-colors duration-500"
              [class]="phaseChipClass()">
          {{ phaseLabel() }}
        </span>
      </div>

      <!-- pipeline nodes -->
      <div class="flex flex-col md:flex-row md:items-start gap-2 md:gap-0">
        @for (agent of agents; track agent.id; let last = $last) {
          <div class="flex md:flex-col items-center gap-3 md:gap-0 md:flex-1 min-w-0">
            <!-- node orb -->
            <div class="relative shrink-0">
              <div
                class="h-16 w-16 rounded-2xl grid place-items-center text-2xl border transition-all duration-500"
                [class.thinking-ring]="statusOf(agent.id) === 'thinking' || statusOf(agent.id) === 'waiting'"
                [style.--ring-color]="agent.accent + '66'"
                [style.borderColor]="isActiveState(agent.id) ? agent.accent : 'rgba(255,255,255,0.12)'"
                [style.background]="nodeBackground(agent.id, agent.accent)"
                [style.boxShadow]="isActiveState(agent.id) ? '0 0 28px ' + agent.accent + '44' : 'none'"
                [style.opacity]="statusOf(agent.id) === 'idle' ? 0.45 : 1">
                {{ agent.icon }}
              </div>
              @if (statusOf(agent.id) === 'completed') {
                <div class="pop-in absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full bg-emerald-400 text-slate-900
                            grid place-items-center text-[10px] font-black">✓</div>
              } @else if (statusOf(agent.id) === 'skipped') {
                <div class="pop-in absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full bg-slate-500 text-slate-900
                            grid place-items-center text-[10px] font-black">–</div>
              } @else if (statusOf(agent.id) === 'error') {
                <div class="pop-in absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full bg-rose-500 text-white
                            grid place-items-center text-[10px] font-black">!</div>
              }
            </div>

            <!-- label -->
            <div class="md:mt-3 md:text-center min-w-0">
              <p class="text-sm font-semibold transition-colors duration-300"
                 [style.color]="isActiveState(agent.id) ? agent.accent : '#cbd5e1'">
                {{ agent.name }}
              </p>
              <p class="text-[11px] text-slate-500 truncate">{{ agent.role }}</p>
              @if (statusOf(agent.id) === 'thinking' || statusOf(agent.id) === 'waiting') {
                <span class="thinking-dots mt-1 inline-block" [style.color]="agent.accent">
                  <span></span><span></span><span></span>
                </span>
              }
            </div>

          </div>

          @if (!last) {
            <div class="connector hidden md:block flex-none w-8 lg:w-14 mt-8"
                 [class.active]="connectorActive($index)"
                 [class.done]="connectorDone($index)"></div>
            <div class="connector md:hidden h-6 w-0.5 ml-8"
                 [class.active]="connectorActive($index)"
                 [class.done]="connectorDone($index)"
                 style="height: 20px; width: 2px;"></div>
          }
        }
      </div>

      <!-- live status ticker -->
      @if (orchestrator.latestMessage(); as message) {
        <div class="mt-8 glass-inset px-4 py-3 flex items-center gap-3 overflow-hidden">
          @if (orchestrator.isBusy()) {
            <span class="relative flex h-2.5 w-2.5 shrink-0">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-fuchsia-400 opacity-60"></span>
              <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-fuchsia-400"></span>
            </span>
          } @else {
            <span class="h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-400"></span>
          }
          <p class="text-sm text-slate-300 truncate">{{ message }}</p>
        </div>
      }
    </div>
  `,
})
export class AgentPipeline {
  protected readonly orchestrator = inject(OrchestratorService);
  protected readonly agents = AGENTS;

  protected statusOf(id: string) {
    return this.orchestrator.agents()[id as AgentId]?.status ?? 'idle';
  }

  protected isActiveState(id: string): boolean {
    const s = this.statusOf(id);
    return s === 'thinking' || s === 'waiting';
  }

  protected nodeBackground(id: string, accent: string): string {
    const s = this.statusOf(id);
    if (s === 'thinking' || s === 'waiting') return `radial-gradient(circle at 30% 25%, ${accent}33, rgba(255,255,255,0.06))`;
    if (s === 'completed') return 'rgba(52, 211, 153, 0.08)';
    return 'rgba(255,255,255,0.05)';
  }

  protected connectorActive(index: number): boolean {
    // Energy flows into the node after this connector while it is working.
    const next = this.agents[index + 1];
    return next ? this.isActiveState(next.id) : false;
  }

  protected connectorDone(index: number): boolean {
    const next = this.agents[index + 1];
    return next ? this.statusOf(next.id) === 'completed' : false;
  }

  protected readonly phaseLabel = computed(() => ({
    idle: 'Standing by',
    running: 'Agents working…',
    waiting_human: 'Awaiting your review',
    done: 'Plan finalised',
    error: 'Error',
  }[this.orchestrator.phase()]));

  protected readonly phaseChipClass = computed(() => ({
    idle: 'border-white/15 text-slate-400 bg-white/5',
    running: 'border-fuchsia-400/40 text-fuchsia-300 bg-fuchsia-500/10',
    waiting_human: 'border-amber-400/40 text-amber-300 bg-amber-500/10',
    done: 'border-emerald-400/40 text-emerald-300 bg-emerald-500/10',
    error: 'border-rose-400/40 text-rose-300 bg-rose-500/10',
  }[this.orchestrator.phase()]));
}
