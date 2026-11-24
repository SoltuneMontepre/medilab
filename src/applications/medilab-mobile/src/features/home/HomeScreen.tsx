import { router } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { UnreachableError, type Task, type TaskDay } from "../../api";
import { useBadges } from "../../badges";
import { useReloadOnReturn } from "../../focus";
import { failed, useLoad } from "../../load";
import { useT } from "../../locale";
import { useRetryPerson } from "../../person";
import { useAction } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { taskPath } from "../documents/documentPath";
import { TONES } from "../shared/Badge";
import { Button, type Tone } from "../shared/Button";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact } from "../tasks/TaskRow";
import { formatTime, isOverdue, statusTone, taskLabel, whenText } from "../tasks/taskText";

type TaskAction = "claim" | "start" | "done";

interface Next {
  action: TaskAction;
  tone: Tone;
}

/** The action the web's dashboard offers on a task of the person: starting it once it is theirs, and marking it done
 * while it is under way, unless the system closes it. */
function nextAction(task: Task): Next | null {
  if (task.status === "assigned") {
    return { action: "start", tone: "primary" };
  }
  if (task.status === "in_progress" && !task.closed_by_system) {
    return { action: "done", tone: "success" };
  }
  return null;
}

const ACTION_LABELS = { claim: "task.claim", start: "task.start", done: "task.done" } as const;

/** The person's day, as the Tasks app on the web opens on it: today's plan and the next tasks with the action each
 * needs, the tasks waiting in their queues to claim, and their finished work, each opening its list. */
export function HomeScreen() {
  const t = useT();
  const { call } = useSession();
  const [pulling, setPulling] = useState(false);
  const { problem, busy, run } = useAction();
  // The navigation not read at start, without a connection, is read again when the person tries again.
  const retryPerson = useRetryPerson();
  const { refresh: refreshBadges } = useBadges();

  // Reading the day also checks the phone's key; a refused key returns the person to sign-in.
  const read = useCallback(async (): Promise<TaskDay> => {
    const day = await call<TaskDay>("/tasks/today");
    if (!day) {
      throw new UnreachableError();
    }
    return day;
  }, [call]);
  const { load, setLoad, reload } = useLoad(read);

  // The day is read again without hiding it, when the person returns to it, pulls it down or acts on a task.
  const refresh = useCallback(async () => {
    try {
      setLoad({ state: "ready", value: await read() });
    } catch (error) {
      setLoad(failed(error));
    }
  }, [read, setLoad]);
  useReloadOnReturn(refresh);

  async function pull() {
    setPulling(true);
    await refresh();
    setPulling(false);
  }

  function act(task: Task, action: TaskAction) {
    void run(async () => {
      await call(`/tasks/${task.id}/${action}`, { method: "POST" });
      await refresh();
    });
  }

  return (
    <Screen title={t("tabs.tasks")} tab refreshing={pulling} onRefresh={pull} testID="home">
      {load.state === "ready" ? (
        <Day day={load.value} busy={busy} onAct={act} />
      ) : (
        <LoadNotice
          load={load}
          gone=""
          onRetry={() => {
            void reload();
            retryPerson();
            refreshBadges();
          }}
        />
      )}
      <ActionProblem problem={problem?.load ?? null} gone={t("task.gone")} onRetry={() => problem?.retry()} />
    </Screen>
  );
}

function Day({
  day,
  busy,
  onAct,
}: Readonly<{ day: TaskDay; busy: boolean; onAct: (task: Task, action: TaskAction) => void }>) {
  const t = useT();
  const { language } = useSession();
  const today = new Date().toLocaleDateString(language, { weekday: "long", day: "numeric", month: "long" });
  return (
    <>
      <View style={styles.head}>
        <Text style={styles.date}>{today}</Text>
        <Text style={shared.title}>{t("home.signedInAs", { name: day.person })}</Text>
        <Text style={shared.detail}>
          {t("day.summary", { open: day.open_count, overdue: day.overdue_count, today: day.due_today_count })}
        </Text>
      </View>

      <Sheet
        title={t("day.myTasks")}
        openTestID="home-todo"
        onOpen={() => router.push({ pathname: "/tasks", params: { list: "open" } })}
      >
        <Text accessibilityRole="header" style={styles.subheading}>
          {t("day.plannedToday")}
        </Text>
        {day.planned_today.length ? (
          day.planned_today.map((task) => <Planned key={task.id} task={task} />)
        ) : (
          <Text style={shared.detail}>{t("day.nothingPlanned")}</Text>
        )}
        <Text accessibilityRole="header" style={styles.subheading}>
          {t("day.nextUp")}
        </Text>
        {day.next_up.length ? (
          day.next_up.map((task) => {
            const next = nextAction(task);
            return (
              <DayRow
                key={task.id}
                task={task}
                action={next && { label: t(ACTION_LABELS[next.action]), tone: next.tone }}
                busy={busy}
                onAct={() => next && onAct(task, next.action)}
              />
            );
          })
        ) : (
          <Text style={shared.detail}>{t("day.nothingToDo")}</Text>
        )}
      </Sheet>

      <Sheet title={t("day.queue")} onOpen={() => router.push({ pathname: "/tasks", params: { list: "queue" } })}>
        <Figure count={day.claimable_count} text={t("day.waiting")} />
        {day.claimable.map((task) => (
          <DayRow
            key={task.id}
            task={task}
            action={{ label: t("task.claim"), tone: "primary" }}
            busy={busy}
            onAct={() => onAct(task, "claim")}
          />
        ))}
      </Sheet>

      <Sheet title={t("day.finished")} onOpen={() => router.push({ pathname: "/tasks", params: { list: "finished" } })}>
        <Figure count={day.finished_week_count} text={t("day.finishedWeek")} />
        <Text style={shared.detail}>{t("day.finishedAll", { count: day.finished_count })}</Text>
      </Sheet>
    </>
  );
}

function Figure({ count, text }: Readonly<{ count: number; text: string }>) {
  return (
    <View style={styles.figure}>
      <Text style={styles.count}>{count}</Text>
      <Text style={[shared.detail, styles.figureText]}>{text}</Text>
    </View>
  );
}

/** A planned task of today on the day's timeline: its hours beside a block in the colour of its status. */
function Planned({ task }: Readonly<{ task: Task }>) {
  const t = useT();
  const { language } = useSession();
  const tone = TONES[statusTone(task.status)];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={taskLabel(task, t, language)}
      style={({ pressed }) => [styles.planned, pressed && styles.pressed]}
      onPress={() => router.push(taskPath(task.id))}
    >
      <View style={styles.hours}>
        {!!task.planned_start && (
          <Text style={styles.start} numberOfLines={1}>
            {formatTime(task.planned_start, language)}
          </Text>
        )}
        {!!task.planned_end && (
          <Text style={shared.detail} numberOfLines={1}>
            {formatTime(task.planned_end, language)}
          </Text>
        )}
      </View>
      <View style={[styles.block, { backgroundColor: tone.background, borderLeftColor: tone.dot }]}>
        <Text style={shared.label} numberOfLines={2}>
          {task.name}
        </Text>
        {!!task.location && <Fact icon="map-marker-outline" text={task.location} />}
      </View>
    </Pressable>
  );
}

/** A task of the day: its status dot, name, deadline and place, opening it, and the action it needs beside it. */
function DayRow({
  task,
  action,
  busy,
  onAct,
}: Readonly<{ task: Task; action: { label: string; tone: Tone } | null; busy: boolean; onAct: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const when = whenText(task, t, language);
  const overdue = isOverdue(task);
  return (
    <View style={styles.row}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={taskLabel(task, t, language)}
        testID="task-row"
        style={({ pressed }) => [styles.rowMain, pressed && styles.pressed]}
        onPress={() => router.push(taskPath(task.id))}
      >
        <View style={[styles.dot, { backgroundColor: TONES[statusTone(task.status)].dot }]} />
        <View style={styles.rowText}>
          <Text style={shared.label} numberOfLines={2}>
            {task.name}
          </Text>
          {!!when && <Fact icon={overdue ? "clock-alert-outline" : "clock-outline"} text={when} alert={overdue} />}
          {!!task.location && <Fact icon="map-marker-outline" text={task.location} />}
        </View>
      </Pressable>
      {action && <Button label={action.label} tone={action.tone} compact disabled={busy} onPress={onAct} />}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { gap: space.xs, paddingVertical: space.xs },
  date: { fontSize: fontSize.sm, color: colors.textMuted, textTransform: "capitalize" },
  subheading: { fontSize: fontSize.sm, fontWeight: "600", color: colors.textMuted, textTransform: "uppercase" },
  figure: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
  count: { fontSize: 28, fontWeight: "700", color: colors.primary },
  figureText: { flex: 1 },
  planned: { flexDirection: "row", gap: space.md },
  hours: { width: 76, alignItems: "flex-end", paddingTop: space.sm },
  start: { fontSize: fontSize.base, fontWeight: "600", color: colors.text },
  block: {
    flex: 1,
    borderLeftWidth: 4,
    borderRadius: radius.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    gap: 2,
  },
  pressed: { opacity: 0.6 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: space.md,
  },
  rowMain: { flex: 1, flexDirection: "row", gap: space.md },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 6 },
  rowText: { flex: 1, gap: 2 },
});
