import type { Href } from "expo-router";

// The model of tasks, which the app opens on its task screen.
const TASK_MODEL = "medilab.task";

/** The app's address of a document, which its screen opens with the person's rights: a task opens on its task
 * screen, any other document on the document screen. */
export function documentPath(document: { model: string; id: number }): Href {
  if (document.model === TASK_MODEL) {
    return taskPath(document.id);
  }
  return { pathname: "/documents/[model]/[id]", params: { model: document.model, id: String(document.id) } };
}

export function taskPath(id: number): Href {
  return { pathname: "/tasks/[id]", params: { id: String(id) } };
}
