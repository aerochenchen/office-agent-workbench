export const BOOT_TIMEOUT_MS = 25_000;
export const BOOT_POLL_MS = 1_000;
export const STEADY_POLL_MS = 8_000;

export function bootPollInterval(elapsedMs: number): number {
  return elapsedMs < BOOT_TIMEOUT_MS ? BOOT_POLL_MS : STEADY_POLL_MS;
}

export function shouldMarkDownDuringBoot(elapsedMs: number, lastOk: boolean): boolean {
  if (lastOk) return false;
  return elapsedMs >= BOOT_TIMEOUT_MS;
}
