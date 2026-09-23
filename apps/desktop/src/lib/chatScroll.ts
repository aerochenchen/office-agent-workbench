/** Whether chat auto-scroll should run (skip while user is selecting text). */
export function shouldAutoScrollChat(opts: {
  hasSelectionInScroll: boolean;
  distanceFromBottom: number;
  thresholdPx?: number;
}): boolean {
  if (opts.hasSelectionInScroll) return false;
  return opts.distanceFromBottom <= (opts.thresholdPx ?? 96);
}

export function selectionTouchesElement(
  selection: Selection | null,
  el: Element,
): boolean {
  if (!selection || selection.isCollapsed) return false;
  const node = selection.anchorNode;
  if (!node) return false;
  // nodeType 1 = ELEMENT_NODE; otherwise use parentElement for text nodes.
  const target =
    node.nodeType === 1 ? (node as Element) : node.parentElement;
  return target != null && el.contains(target);
}
