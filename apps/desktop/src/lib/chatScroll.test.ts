import { describe, expect, it } from "vitest";
import { selectionTouchesElement, shouldAutoScrollChat } from "./chatScroll";

describe("shouldAutoScrollChat", () => {
  it("skips auto-scroll while text is selected in the scroll area", () => {
    expect(
      shouldAutoScrollChat({ hasSelectionInScroll: true, distanceFromBottom: 0 }),
    ).toBe(false);
  });

  it("scrolls when near bottom and nothing is selected", () => {
    expect(
      shouldAutoScrollChat({ hasSelectionInScroll: false, distanceFromBottom: 20 }),
    ).toBe(true);
  });

  it("does not scroll when the user has scrolled up", () => {
    expect(
      shouldAutoScrollChat({ hasSelectionInScroll: false, distanceFromBottom: 200 }),
    ).toBe(false);
  });
});

describe("selectionTouchesElement", () => {
  it("returns false for null selection", () => {
    const el = { contains: () => true } as unknown as Element;
    expect(selectionTouchesElement(null, el)).toBe(false);
  });

  it("returns false when selection is collapsed", () => {
    const el = { contains: () => true } as unknown as Element;
    const sel = { isCollapsed: true, anchorNode: {} } as unknown as Selection;
    expect(selectionTouchesElement(sel, el)).toBe(false);
  });

  it("returns true when anchor is inside the element", () => {
    const parent = {} as unknown as Element;
    const text = { nodeType: 3, parentElement: parent } as unknown as Node;
    const el = {
      contains: (n: Node | null) => n === parent,
    } as unknown as Element;
    const sel = {
      isCollapsed: false,
      anchorNode: text,
    } as unknown as Selection;
    expect(selectionTouchesElement(sel, el)).toBe(true);
  });
});
