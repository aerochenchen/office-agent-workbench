export interface TreeEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export type SkillTier = "light" | "heavy";

export interface SkillMeta {
  id: string;
  name: string;
  description: string;
  version: string;
  tier: SkillTier;
  min_ram_gb: number | null;
  enabled: boolean;
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

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  toolEvents?: ToolEvent[];
}

export interface RuntimeConfig {
  api_base: string;
  api_key: string;
  model: string;
  allowed_hosts: string[];
}
