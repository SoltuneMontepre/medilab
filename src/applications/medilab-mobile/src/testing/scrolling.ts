import type { TestInstance } from "test-renderer";

/** The scroll view that holds `element`, or null when no scroll view holds it. */
export function scrollingParent(element: TestInstance) {
  let parent = element.parent;
  while (parent && parent.type !== "RCTScrollView") {
    parent = parent.parent;
  }
  return parent;
}
