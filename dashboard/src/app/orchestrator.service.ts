import { Injectable, computed, signal } from '@angular/core';
import { AGENTS, AgentEvent, AgentId, AgentStatus, PlanSnapshot, Phase } from './models';

const API_BASE = 'http://localhost:8000';

export interface StartPayload {
  goal: string;
  weekday_availability: string;
  weekend_availability: string;
  start_date: string | null;
  use_context: boolean;
}

export interface ResumePayload {
  action: 'approve' | 'feedback' | 'adjust_time';
  feedback?: string;
  weekday_availability?: string;
  weekend_availability?: string;
}

function idleAgents(): Record<AgentId, { status: AgentStatus; message: string }> {
  const map = {} as Record<AgentId, { status: AgentStatus; message: string }>;
  for (const a of AGENTS) map[a.id] = { status: 'idle', message: '' };
  return map;
}

@Injectable({ providedIn: 'root' })
export class OrchestratorService {
  readonly phase = signal<Phase>('idle');
  readonly agents = signal(idleAgents());
  readonly currentAgent = signal<AgentId | null>(null);
  readonly events = signal<AgentEvent[]>([]);
  readonly snapshot = signal<PlanSnapshot | null>(null);
  readonly simulated = signal(false);
  readonly errorMessage = signal('');
  readonly goal = signal('');

  readonly isBusy = computed(() => this.phase() === 'running');
  readonly latestMessage = computed(() => {
    const list = this.events();
    for (let i = list.length - 1; i >= 0; i--) {
      if (list[i].type === 'agent_event' && list[i].message) return list[i].message!;
    }
    return '';
  });

  private sessionId: string | null = null;
  private source: EventSource | null = null;

  async start(payload: StartPayload): Promise<void> {
    this.closeStream();
    this.goal.set(payload.goal);
    this.phase.set('running');
    this.agents.set(idleAgents());
    this.currentAgent.set(null);
    this.events.set([]);
    this.snapshot.set(null);
    this.errorMessage.set('');

    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const data = await res.json();
      this.sessionId = data.session_id;
      this.simulated.set(!!data.simulated);
      this.openStream();
    } catch (e: any) {
      this.phase.set('error');
      this.errorMessage.set(
        e?.message?.includes('fetch')
          ? 'Cannot reach the orchestrator API on http://localhost:8000 — is server.py running?'
          : String(e?.message ?? e),
      );
    }
  }

  async resume(payload: ResumePayload): Promise<void> {
    if (!this.sessionId) return;
    this.phase.set('running');
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${this.sessionId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
    } catch (e: any) {
      this.phase.set('error');
      this.errorMessage.set(String(e?.message ?? e));
    }
  }

  reset(): void {
    this.closeStream();
    this.sessionId = null;
    this.phase.set('idle');
    this.agents.set(idleAgents());
    this.currentAgent.set(null);
    this.events.set([]);
    this.snapshot.set(null);
    this.errorMessage.set('');
  }

  private openStream(): void {
    this.source = new EventSource(`${API_BASE}/api/sessions/${this.sessionId}/events`);
    this.source.onmessage = (msg) => this.handleEvent(JSON.parse(msg.data));
    this.source.onerror = () => {
      // EventSource fires error on normal close too; only surface it mid-run.
      if (this.phase() === 'running') {
        this.phase.set('error');
        this.errorMessage.set('Lost connection to the orchestrator event stream.');
      }
      this.closeStream();
    };
  }

  private handleEvent(event: AgentEvent & Record<string, any>): void {
    this.events.update((list) => [...list, event]);

    if (event.type === 'agent_event' && event.agent) {
      const agent = event.agent as AgentId;
      const status = event.status ?? '';
      const mapped: AgentStatus =
        status === 'completed' ? 'completed'
        : status === 'skipped' ? 'skipped'
        : status === 'waiting' ? 'waiting'
        : 'thinking';
      this.agents.update((map) => ({
        ...map,
        [agent]: { status: mapped, message: event.message ?? '' },
      }));
      this.currentAgent.set(mapped === 'thinking' || mapped === 'waiting' ? agent : this.currentAgent());
      return;
    }

    if (event.type === 'interrupt') {
      this.snapshot.set(event as unknown as PlanSnapshot);
      this.phase.set('waiting_human');
      this.currentAgent.set('human');
      return;
    }

    if (event.type === 'done') {
      this.snapshot.set(event as unknown as PlanSnapshot);
      this.phase.set('done');
      this.currentAgent.set(null);
      this.agents.update((map) => ({ ...map, human: { status: 'completed', message: 'Plan approved.' } }));
      this.closeStream();
      return;
    }

    if (event.type === 'error') {
      this.phase.set('error');
      this.errorMessage.set(event['message'] ?? 'Unknown orchestrator error');
      if (this.currentAgent()) {
        const agent = this.currentAgent()!;
        this.agents.update((map) => ({ ...map, [agent]: { status: 'error', message: event['message'] ?? '' } }));
      }
      this.closeStream();
    }
  }

  private closeStream(): void {
    this.source?.close();
    this.source = null;
  }
}
