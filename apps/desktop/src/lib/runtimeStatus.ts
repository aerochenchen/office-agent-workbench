/** Local runtime process reachability (from /health). */
export type HealthState = "checking" | "ok" | "down";

/**
 * Top-bar readiness: runtime up is not enough — chat also needs a model endpoint.
 * - checking: boot / config still loading
 * - needs_config: runtime online, model not configured
 * - ok: ready to chat
 * - down: runtime unreachable
 */
export type RuntimeStatus = "checking" | "needs_config" | "ok" | "down";

export function deriveRuntimeStatus(
  health: HealthState,
  options: { configReady: boolean; needsConfig: boolean },
): RuntimeStatus {
  if (health === "checking") return "checking";
  if (health === "down") return "down";
  if (!options.configReady) return "checking";
  if (options.needsConfig) return "needs_config";
  return "ok";
}

export function runtimeStatusLabel(status: RuntimeStatus): string {
  switch (status) {
    case "ok":
      return "就绪";
    case "needs_config":
      return "待配置";
    case "down":
      return "未连接";
    default:
      return "启动中…";
  }
}
