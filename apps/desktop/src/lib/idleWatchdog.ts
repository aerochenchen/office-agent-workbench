/** Fires `onIdle` if `bump()` is not called within `idleMs`. */
export function createIdleWatchdog(idleMs: number, onIdle: () => void): {
  bump: () => void;
  stop: () => void;
} {
  let handle: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const bump = () => {
    if (stopped) return;
    if (handle !== null) clearTimeout(handle);
    handle = setTimeout(() => {
      handle = null;
      if (!stopped) onIdle();
    }, idleMs);
  };

  const stop = () => {
    stopped = true;
    if (handle !== null) {
      clearTimeout(handle);
      handle = null;
    }
  };

  bump();
  return { bump, stop };
}
