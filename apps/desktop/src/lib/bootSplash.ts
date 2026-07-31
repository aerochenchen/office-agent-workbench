const SPLASH_ID = "boot-splash";
const FADE_MS = 200;

export function dismissBootSplash(): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.classList.add("boot-splash--done");
  window.setTimeout(() => {
    el.remove();
  }, FADE_MS);
}
