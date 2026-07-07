import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OrchestratorService } from './orchestrator.service';

@Component({
  selector: 'app-hitl-panel',
  imports: [FormsModule],
  template: `
    <div class="glass p-6 md:p-8 animate-enter border-amber-400/25"
         style="box-shadow: 0 8px 40px rgba(251,191,36,0.08), inset 0 1px 0 rgba(255,255,255,0.2)">
      <div class="flex items-center gap-3 mb-5">
        <div class="h-10 w-10 rounded-xl grid place-items-center text-xl bg-amber-400/15 border border-amber-400/30">🧑‍💻</div>
        <div>
          <h2 class="text-lg font-semibold text-white">Human-in-the-loop review</h2>
          <p class="text-sm text-slate-400">The graph is paused on an interrupt — the agents are waiting for you.</p>
        </div>
      </div>

      <div class="flex flex-wrap gap-3 mb-5">
        <button (click)="mode.set('approve')" [class]="tabClass('approve')">✓ Approve</button>
        <button (click)="mode.set('feedback')" [class]="tabClass('feedback')">✎ Request changes</button>
        <button (click)="mode.set('adjust_time')" [class]="tabClass('adjust_time')">⏱ Adjust availability</button>
      </div>

      @switch (mode()) {
        @case ('feedback') {
          <textarea [(ngModel)]="feedback" rows="3"
            placeholder="e.g. Add a mock interview at the end, and make the FAISS deep-dive longer"
            class="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                   placeholder:text-slate-500 outline-none transition-all duration-300
                   focus:border-amber-400/60 focus:bg-white/10 resize-none themed-scroll"></textarea>
        }
        @case ('adjust_time') {
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label class="block">
              <span class="text-xs font-medium uppercase tracking-wider text-slate-400">New weekday limit</span>
              <input [(ngModel)]="weekday" placeholder="2.5 hours"
                class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                       placeholder:text-slate-500 outline-none focus:border-amber-400/60 focus:bg-white/10" />
            </label>
            <label class="block">
              <span class="text-xs font-medium uppercase tracking-wider text-slate-400">New weekend limit</span>
              <input [(ngModel)]="weekend" placeholder="5 hours"
                class="mt-1.5 w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm text-white
                       placeholder:text-slate-500 outline-none focus:border-amber-400/60 focus:bg-white/10" />
            </label>
          </div>
        }
        @default {
          <p class="text-sm text-slate-400">Finalise the plan exactly as drafted below.</p>
        }
      }

      <button (click)="submit()" [disabled]="!canSubmit()"
        class="mt-5 rounded-xl px-6 py-3 text-sm font-semibold text-slate-900 transition-all duration-300
               bg-gradient-to-r from-amber-300 to-orange-400
               hover:shadow-[0_0_28px_rgba(251,191,36,0.45)] hover:-translate-y-0.5 active:translate-y-0
               disabled:opacity-40 disabled:cursor-not-allowed">
        {{ submitLabel() }}
      </button>
    </div>
  `,
})
export class HitlPanel {
  protected readonly orchestrator = inject(OrchestratorService);

  protected readonly mode = signal<'approve' | 'feedback' | 'adjust_time'>('approve');
  protected readonly feedback = signal('');
  protected readonly weekday = signal('');
  protected readonly weekend = signal('');

  protected tabClass(tab: string): string {
    const base = 'rounded-xl px-4 py-2 text-sm font-medium border transition-all duration-300 ';
    return this.mode() === tab
      ? base + 'border-amber-400/60 bg-amber-400/15 text-amber-200 shadow-[0_0_18px_rgba(251,191,36,0.2)]'
      : base + 'border-white/10 bg-white/5 text-slate-400 hover:text-white hover:border-white/25';
  }

  protected canSubmit(): boolean {
    if (this.mode() === 'feedback') return !!this.feedback().trim();
    if (this.mode() === 'adjust_time') return !!(this.weekday().trim() || this.weekend().trim());
    return true;
  }

  protected submitLabel(): string {
    return { approve: 'Approve & finalise plan', feedback: 'Send feedback to decomposer', adjust_time: 'Re-run scheduler' }[this.mode()];
  }

  submit(): void {
    const mode = this.mode();
    if (mode === 'feedback') {
      this.orchestrator.resume({ action: 'feedback', feedback: this.feedback().trim() });
      this.feedback.set('');
    } else if (mode === 'adjust_time') {
      this.orchestrator.resume({
        action: 'adjust_time',
        weekday_availability: this.weekday().trim() || '2 hours',
        weekend_availability: this.weekend().trim() || '4 hours',
      });
    } else {
      this.orchestrator.resume({ action: 'approve' });
    }
    this.mode.set('approve');
  }
}
