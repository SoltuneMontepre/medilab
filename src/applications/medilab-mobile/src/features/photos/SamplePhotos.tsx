import { router } from "expo-router";
import { useCallback } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { Sample, SamplePhoto } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { Button } from "../shared/Button";
import { Icon } from "../shared/Icon";
import { Sheet } from "../shared/Sheet";
import { UnsentCard } from "../shared/UnsentCard";
import { formatMoment } from "../tasks/taskText";
import { discardPhoto, sendPhoto, unsentPhotos } from "./photoQueue";

/** The photos of a sample taken when it was collected or received: those MediLab has, those still on the phone to
 * send again or discard, and the way to take another. Only a person who may add photos sees them; a tester never does. */
export function SamplePhotos({ sample }: Readonly<{ sample: Sample }>) {
  const t = useT();
  const { call, language } = useSession();
  const { problem, busy, run } = useAction();
  const sent = useRecord<{ photos: SamplePhoto[] }>(`/samples/${sample.id}/photos`);
  const unsent = useLoad(useCallback(() => unsentPhotos(sample.id), [sample.id]));
  // The phone's own photos are read again when the person returns from the camera, as MediLab's are.
  useReloadOnReturn(unsent.reload);

  function settle(action: () => Promise<unknown>) {
    return run(async () => {
      try {
        await action();
      } finally {
        await Promise.all([sent.reload(), unsent.reload()]);
      }
    });
  }

  return (
    <Sheet title={t("sample.photos")}>
      {unsent.load.state === "ready" &&
        unsent.load.value.map((photo) => (
          <UnsentCard
            key={photo.key}
            label={t("photo.unsent", { date: formatMoment(photo.takenAt, language) })}
            send={t("photo.send")}
            discard={t("photo.discard")}
            busy={busy}
            onSend={() => settle(() => sendPhoto(photo, call))}
            onDiscard={() => settle(async () => discardPhoto(photo))}
            testID={`unsent-photo-${photo.key}`}
          />
        ))}
      <ActionProblem problem={problem?.load ?? null} gone={t("sample.gone")} onRetry={() => problem?.retry()} />
      {sent.load.state === "ready" && <Sent photos={sent.load.value.photos} />}
      <Button
        label={t("sample.takePhoto")}
        icon="camera-outline"
        onPress={() =>
          router.push({ pathname: "/samples/[id]/photo", params: { id: String(sample.id), code: sample.code } })
        }
        testID="take-photo"
      />
    </Sheet>
  );
}

function Sent({ photos }: Readonly<{ photos: SamplePhoto[] }>) {
  const t = useT();
  const { language } = useSession();
  if (!photos.length) {
    return <Text style={shared.detail}>{t("sample.noPhotos")}</Text>;
  }
  return photos.map((photo) => (
    <View key={photo.id} style={styles.photo} testID={`sample-photo-${photo.id}`}>
      <View style={styles.thumb}>
        <Icon name="image-outline" color={colors.primary} />
      </View>
      <View style={styles.text}>
        <Text style={shared.label} numberOfLines={1}>
          {photo.name}
        </Text>
        <Text style={shared.detail}>
          {t("sample.photoTaken", { name: photo.created_by, date: formatMoment(photo.created_at, language) })}
        </Text>
      </View>
    </View>
  ));
}

const styles = StyleSheet.create({
  photo: { flexDirection: "row", alignItems: "center", gap: space.md },
  thumb: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.primaryLight,
    alignItems: "center",
    justifyContent: "center",
  },
  text: { flex: 1, gap: 2 },
});
