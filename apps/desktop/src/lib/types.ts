export interface TreeEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export type SkillTier = "light" | "heavy";

export interface SkillMeta {
  id: string;
  name: string;
  display_name?: string;
  description: string;
  version: string;
  tier: SkillTier;
  min_ram_gb: number | null;
  permissions?: string[];
  enabled: boolean;
}

export interface SkillInspect {
  id: string;
  name: string;
  display_name?: string;
  description: string;
  version: string;
  tier: SkillTier;
  min_ram_gb: number | null;
  permissions: string[];
  shared_scripts?: string[];
  enabled?: boolean;
}

export interface ToolEvent {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
}

export interface ChatReply {
  reply: string;
  tool_events: ToolEvent[];
  session_id: string;
}

export type MessageRole = "user" | "assistant" | "error";

export type LiveStepStatus = "running" | "ok" | "fail";

export interface LiveStep {
  id: string;
  name: string;
  label: string;
  status: LiveStepStatus;
  summary?: string;
}

export type AssistantPhase = "pending" | "live" | "done";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  toolEvents?: ToolEvent[];
  /** In-progress assistant bubble (A0 placeholder / B1 live stream). */
  phase?: AssistantPhase;
  liveSteps?: LiveStep[];
  startedAt?: number;
  statusPhase?: "planning" | "tools" | "finishing";
  stepsExpanded?: boolean;
}

export interface SessionMeta {
  id: string;
  workspace_path: string;
  title: string;
  created_at: number;
  updated_at: number;
}

export interface SessionUiMessage {
  role: "user" | "assistant";
  content: string;
}

export interface RuntimeConfig {
  api_base: string;
  api_key: string;
  model: string;
  allowed_hosts: string[];
}

export interface ChatStreamHandlers {
  onStarted?: (sessionId: string) => void;
  onStatus?: (phase: string) => void;
  onToolStart?: (ev: {
    id: string;
    name: string;
    label: string;
    args_summary?: string;
  }) => void;
  onToolDone?: (ev: {
    id: string;
    name: string;
    label: string;
    ok: boolean;
    summary?: string;
  }) => void;
  onFinal?: (reply: ChatReply) => void;
  onError?: (message: string) => void;
}
