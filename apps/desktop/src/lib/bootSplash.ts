import type { HealthState } from "./runtimeStatus";

const SPLASH_ID = "boot-splash";
const CAROUSEL_ID = "boot-splash-carousel";
const FADE_MS = 200;

/** Keep the splash up while waiting for local runtime health. */
export function shouldDismissBootSplash(health: HealthState): boolean {
  return health === "ok" || health === "down";
}

function clearSplashCarouselTimer(): void {
  const carousel = document.getElementById(CAROUSEL_ID);
  if (!carousel) return;
  const raw = carousel.dataset.carouselIntervalId;
  if (!raw) return;
  const id = Number(raw);
  if (!Number.isFinite(id)) return;
  window.clearInterval(id);
  delete carousel.dataset.carouselIntervalId;
}

export function dismissBootSplash(): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  clearSplashCarouselTimer();
  el.classList.add("boot-splash--done");
  window.setTimeout(() => {
    el.remove();
  }, FADE_MS);
}
