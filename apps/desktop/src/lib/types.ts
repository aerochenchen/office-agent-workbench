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

export interface SkillValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface SkillInspectResult {
  skill: SkillInspect;
  validation: SkillValidation;
  /** Inferable frontmatter fills (version/tier/display_name). */
  auto_fixes?: string[];
  /** True when applying auto_fixes would make the package installable. */
  can_install_with_fixes?: boolean;
}

export interface SkillInstallResult {
  ok: boolean;
  skill: SkillInspect;
  validation: SkillValidation;
}

/** Runtime 400 detail when skill install/inspect fails validation. */
export interface SkillErrorDetail {
  error?: string;
  errors?: string[];
  warnings?: string[];
  validation?: SkillValidation;
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
  /** Server-assigned UUID for one chat turn (SSE started). */
  turnId?: string;
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

export type PermissionMode = "cautious" | "standard" | "trust_workspace";

export interface RuntimeConfig {
  api_base: string;
  /** Local form draft only; empty after GET /config. */
  api_key: string;
  api_key_masked?: string;
  api_key_set?: boolean;
  model: string;
  allowed_hosts: string[];
  permission_mode: PermissionMode;
}

export interface PermissionRequestEvent {
  id: string;
  tool: string;
  summary: string;
  session_id: string;
}

export interface ChatStreamHandlers {
  onStarted?: (sessionId: string, turnId?: string) => void;
  onStatus?: (phase: string) => void;
  onToolStart?: (ev: {
    id: string;
    name: string;
    label: string;
    args_summary?: string;
    turn_id?: string;
  }) => void;
  onToolDone?: (ev: {
    id: string;
    name: string;
    label: string;
    ok: boolean;
    summary?: string;
    turn_id?: string;
  }) => void;
  onPermissionRequest?: (ev: PermissionRequestEvent) => void;
  onFinal?: (reply: ChatReply) => void;
  onError?: (message: string) => void;
}
