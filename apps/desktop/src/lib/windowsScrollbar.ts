const SCROLL_SELECTOR = [
  ".pane-body",
  ".chat-input",
  ".markdown-body pre",
  ".settings-nav",
  ".settings-pane",
  ".settings-notice-text",
  ".skill-manager-body",
  ".modal-body",
].join(",");

const MARK = "win-scroll--on";

function overflowGap(el: HTMLElement): number {
  return Math.max(el.scrollHeight - el.clientHeight, el.scrollWidth - el.clientWidth);
}

function syncOverflow(el: HTMLElement): void {
  const gap = overflowGap(el);
  const marked = el.classList.contains(MARK);
  el.classList.toggle(MARK, marked ? gap > -12 : gap > 1);
}

function bindScroller(el: HTMLElement): () => void {
  let hideTimer = 0;
  let dragging = false;
  const armHide = (delay: number) => {
    window.clearTimeout(hideTimer);
    hideTimer = window.setTimeout(() => {
      if (!dragging && !el.matches(":hover")) delete el.dataset.scrollbar;
    }, delay);
  };
  const reveal = () => {
    el.dataset.scrollbar = "active";
    armHide(700);
  };
  const onEnter = () => {
    window.clearTimeout(hideTimer);
    el.dataset.scrollbar = "active";
  };
  const onLeave = () => {
    if (!dragging) armHide(480);
  };
  const onPointerDown = (event: PointerEvent) => {
    if (event.target !== el) return;
    dragging = true;
    window.clearTimeout(hideTimer);
    el.dataset.scrollbar = "active";
  };
  const onPointerUp = () => {
    if (!dragging) return;
    dragging = false;
    armHide(700);
  };

  syncOverflow(el);
  const resizeObserver = new ResizeObserver(() => syncOverflow(el));
  resizeObserver.observe(el);
  el.addEventListener("scroll", reveal, { passive: true });
  el.addEventListener("pointerenter", onEnter);
  el.addEventListener("pointerleave", onLeave);
  el.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);

  return () => {
    window.clearTimeout(hideTimer);
    resizeObserver.disconnect();
    el.removeEventListener("scroll", reveal);
    el.removeEventListener("pointerenter", onEnter);
    el.removeEventListener("pointerleave", onLeave);
    el.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    el.classList.remove(MARK);
    delete el.dataset.scrollbar;
  };
}

/** 给对话、设置、技能和文件树的滚动容器套上同一套 Windows 滚动条。macOS 保持系统滚动条。 */
export function installWindowsScrollbars(root: ParentNode = document): () => void {
  if (document.documentElement.dataset.platform !== "windows") return () => {};

  const bindings = new Map<HTMLElement, () => void>();
  let frame = 0;

  const bindNew = () => {
    root.querySelectorAll<HTMLElement>(SCROLL_SELECTOR).forEach((el) => {
      if (bindings.has(el)) return;
      bindings.set(el, bindScroller(el));
    });
  };

  const syncBound = () => {
    for (const [el, disconnect] of bindings) {
      if (!el.isConnected) {
        disconnect();
        bindings.delete(el);
        continue;
      }
      syncOverflow(el);
    }
    bindNew();
  };

  const scheduleSync = () => {
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      syncBound();
    });
  };

  bindNew();
  const observer = new MutationObserver(scheduleSync);
  const scope = root instanceof HTMLElement ? root : document.body;
  observer.observe(scope, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["class"],
  });

  return () => {
    window.cancelAnimationFrame(frame);
    observer.disconnect();
    for (const disconnect of bindings.values()) disconnect();
    bindings.clear();
  };
}
