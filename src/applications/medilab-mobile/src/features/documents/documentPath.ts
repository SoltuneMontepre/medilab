import type { Href } from "expo-router";

// The models the app opens on screens of their own: tasks, samples, sample tests and results.
const TASK_MODEL = "medilab.task";
const SAMPLE_MODEL = "medilab.sample";
export const SAMPLE_TEST_MODEL = "medilab.sample.test";
const RESULT_MODEL = "medilab.test.result";

/** The app's address of a document, which its screen opens with the person's rights: a task opens on its task
 * screen, a sample on its sample screen, a sample test and a result on their bench screens, any other document on the
 * document screen. */
export function documentPath(document: { model: string; id: number }): Href {
  if (document.model === TASK_MODEL) {
    return taskPath(document.id);
  }
  if (document.model === SAMPLE_MODEL) {
    return samplePath(document.id);
  }
  if (document.model === SAMPLE_TEST_MODEL) {
    return sampleTestPath(document.id);
  }
  if (document.model === RESULT_MODEL) {
    return resultPath(document.id);
  }
  return { pathname: "/documents/[model]/[id]", params: { model: document.model, id: String(document.id) } };
}

export function taskPath(id: number): Href {
  return { pathname: "/tasks/[id]", params: { id: String(id) } };
}

export function samplePath(id: number): Href {
  return { pathname: "/samples/[id]", params: { id: String(id) } };
}

export function sampleTestPath(id: number): Href {
  return { pathname: "/sample-tests/[id]", params: { id: String(id) } };
}

export function resultPath(id: number): Href {
  return { pathname: "/results/[id]", params: { id: String(id) } };
}
