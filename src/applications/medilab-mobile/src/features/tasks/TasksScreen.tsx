import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";

import type { Task, TaskList, TaskPage } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { usePersonRead } from "../../person";
import { useSession } from "../../session";
import { ActionProblem } from "../connection/ActionProblem";
import { taskPath } from "../documents/documentPath";
import { chosenTab, ListTabs, type ListTab } from "../shared/ListTabs";
import { NavButton } from "../shared/Navbar";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";
import { TaskRow } from "./TaskRow";

const LISTS: ListTab<TaskList>[] = [
  { list: "open", label: "tasks.open", empty: "tasks.openEmpty" },
  { list: "finished", label: "tasks.finished", empty: "tasks.finishedEmpty" },
  { list: "queue", label: "tasks.queue", empty: "tasks.queueEmpty" },
];

interface Listed {
  tasks: Task[];
  nextAfter: number | null;
}

/** The person's to-do list: their open tasks, soonest deadline first, their finished tasks, and the tasks waiting in
 * the queues they can claim from, the same as the web's lists. A person who may create tasks creates one from it. */
export function TasksScreen() {
  const t = useT();
  const { call } = useSession();
  const person = usePersonRead();
  const params = useLocalSearchParams<{ list?: string }>();
  const [list, setList] = useState(() => chosenTab(LISTS, params.list));
  const [problem, setProblem] = useState<Load<never> | null>(null);

  const page = useCallback(
    async (after: number | null): Promise<Listed> => {
      const query = after ? `list=${list}&after=${after}` : `list=${list}`;
      const answer = await call<TaskPage>(`/tasks?${query}`);
      return { tasks: answer?.tasks ?? [], nextAfter: answer?.next_after ?? null };
    },
    [call, list],
  );
  const first = useCallback(() => page(null), [page]);
  const { load, setLoad, reload, refresh } = useLoad(first);
  useReloadOnReturn(refresh);

  async function more() {
    if (load.state !== "ready" || !load.value.nextAfter) {
      return;
    }
    setProblem(null);
    try {
      const next = await page(load.value.nextAfter);
      setLoad({ state: "ready", value: { tasks: [...load.value.tasks, ...next.tasks], nextAfter: next.nextAfter } });
    } catch (error) {
      setProblem(failed(error));
    }
  }

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <Screen
      title={t("tasks.title")}
      scroll={false}
      actions={
        person?.me.can.create_tasks && (
          <NavButton icon="plus" label={t("tasks.new")} testID="tasks-new" onPress={() => router.push("/tasks/new")} />
        )
      }
    >
      <ListTabs
        tabs={LISTS}
        chosen={list}
        onChoose={(chosen) => {
          setProblem(null);
          setList(chosen);
        }}
      />
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value.tasks : []}
        keyOf={(task) => task.id}
        renderItem={(task) => <TaskRow task={task} onPress={() => router.push(taskPath(task.id))} />}
        icon="clipboard-check-outline"
        empty={t(current.empty)}
        onRetry={reload}
        onRefresh={refresh}
        hasMore={load.state === "ready" && load.value.nextAfter !== null}
        onMore={more}
        footer={<ActionProblem problem={problem} gone={t(current.empty)} onRetry={more} />}
      />
    </Screen>
  );
}
