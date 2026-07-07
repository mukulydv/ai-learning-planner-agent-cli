export type AgentId = 'intake' | 'context' | 'decomposer' | 'scheduler' | 'reviewer' | 'human';

export type AgentStatus = 'idle' | 'thinking' | 'completed' | 'waiting' | 'skipped' | 'error';

export interface AgentMeta {
  id: AgentId;
  name: string;
  role: string;
  icon: string;      // emoji glyph
  accent: string;    // tailwind-ish accent color (hex)
}

export const AGENTS: AgentMeta[] = [
  { id: 'intake',     name: 'Intake',     role: 'Parses availability',      icon: '⏱️', accent: '#60a5fa' },
  { id: 'context',    name: 'Context',    role: 'RAG · FAISS retrieval',    icon: '📚', accent: '#22d3ee' },
  { id: 'decomposer', name: 'Decomposer', role: 'Milestones & micro-tasks', icon: '🧩', accent: '#c084fc' },
  { id: 'scheduler',  name: 'Scheduler',  role: 'Calendar allocation',      icon: '🗓️', accent: '#34d399' },
  { id: 'reviewer',   name: 'Reviewer',   role: 'Quality critique',         icon: '🔍', accent: '#fbbf24' },
  { id: 'human',      name: 'Human',      role: 'You — approve or refine',  icon: '🧑‍💻', accent: '#fb7185' },
];

export interface AgentEvent {
  type: string;
  agent?: AgentId;
  status?: string;
  message?: string;
  ts: number;
}

export interface Milestone {
  milestone_id: string;
  title: string;
  description: string;
  sequence: number;
}

export interface MicroTask {
  task_id: string;
  milestone_id: string;
  title: string;
  description: string;
  estimated_duration_minutes: number;
  priority: string;
  sequence: number;
}

export interface ScheduledTask {
  title: string;
  description: string;
  duration_minutes: number;
  priority: string;
  sequence: number;
  milestone_id: string;
  part: string | null;
}

export interface ScheduleDay {
  date: string;
  day_name: string;
  is_weekend: boolean;
  allocated_tasks: ScheduledTask[];
  limit_minutes: number;
  used_minutes: number;
  notes: string;
}

export interface PlanSnapshot {
  schedule_markdown: string;
  milestones: Milestone[];
  tasks: MicroTask[];
  schedule: ScheduleDay[];
  sources: string[];
  allocation: { weekday_hours: number; weekend_hours: number; additional_notes: string } | null;
}

export type Phase = 'idle' | 'running' | 'waiting_human' | 'done' | 'error';
