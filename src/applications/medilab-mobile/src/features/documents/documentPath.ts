import type { Href } from "expo-router";

/** The app's address of a document, which its screen opens with the person's rights. */
export function documentPath(document: { model: string; id: number }): Href {
  return { pathname: "/documents/[model]/[id]", params: { model: document.model, id: String(document.id) } };
}
