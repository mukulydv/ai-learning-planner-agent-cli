import { Component, inject } from '@angular/core';
import { AgentPipeline } from './agent-pipeline';
import { EventFeed } from './event-feed';
import { GoalForm } from './goal-form';
import { HitlPanel } from './hitl-panel';
import { OrchestratorService } from './orchestrator.service';
import { PlanView } from './plan-view';

@Component({
  selector: 'app-root',
  imports: [GoalForm, AgentPipeline, EventFeed, HitlPanel, PlanView],
  template: `
    <div class="aurora"><div class="blob"></div></div>

    <div class="mx-auto max-w-7xl px-4 md:px-8 py-8 md:py-12">
      <!-- header -->
      <header class="flex flex-wrap items-center justify-between gap-4 mb-10 animate-enter">
        <div class="flex items-center gap-4">
          <div class="h-12 w-12 rounded-2xl grid place-items-center text-2xl glass float-y">🧠</div>
          <div>
            <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight">
              <span class="text-gradient">Multi-Agent Orchestrator</span>
            </h1>
            <p class="text-sm text-slate-400">
              AI Learning Planner · LangGraph · Gemini · FAISS RAG · Human-in-the-loop
            </p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          @if (orchestrator.simulated() && orchestrator.phase() !== 'idle') {
            <span class="text-xs px-3 py-1.5 rounded-full border border-sky-400/40 bg-sky-500/10 text-sky-300">
              Simulation mode — no GEMINI_API_KEY on the server
            </span>
          }
          @if (orchestrator.phase() !== 'idle') {
            <button (click)="orchestrator.reset()"
              class="text-sm px-4 py-2 rounded-xl border border-white/10 bg-white/5 text-slate-300
                     transition-all duration-300 hover:text-white hover:border-rose-400/50">
              ↺ New session
            </button>
          }
        </div>
      </header>

      <main class="space-y-6">
        @if (orchestrator.phase() === 'idle') {
          <app-goal-form />
        }

        @if (orchestrator.phase() !== 'idle') {
          <app-agent-pipeline />
        }

        @if (orchestrator.phase() === 'error') {
          <div class="glass p-6 border-rose-400/30 animate-enter">
            <p class="text-sm font-semibold text-rose-300 mb-1">Orchestration error</p>
            <p class="text-sm text-slate-300">{{ orchestrator.errorMessage() }}</p>
          </div>
        }

        @if (orchestrator.phase() === 'waiting_human') {
          <app-hitl-panel />
        }

        @if (orchestrator.phase() !== 'idle' && orchestrator.phase() !== 'error') {
          <div class="grid gap-6 lg:grid-cols-[1fr_360px] items-start">
            <app-plan-view />
            <app-event-feed />
          </div>
        }
      </main>

      <footer class="mt-12 text-center text-xs text-slate-600 animate-enter">
        Built by Mukul Kumar Yadav — LangGraph multi-agent backend + Angular {{ angularVersion }} & Tailwind CSS dashboard
      </footer>
    </div>
  `,
})
export class App {
  protected readonly orchestrator = inject(OrchestratorService);
  protected readonly angularVersion = 22;
}
