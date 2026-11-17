import { router } from "expo-router";
import { useCallback } from "react";
import { Text, View } from "react-native";

import type { Sample, SamplePhoto } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useAction, useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { Button } from "../shared/Button";
import { formatMoment } from "../tasks/taskText";
import { discardPhoto, sendPhoto, unsentPhotos, type UnsentPhoto } from "./photoQueue";

/** The photos of a sample taken when it was collected or received: those MediLab has, those still on the phone to
 * send again or discard, and the way to take another. Only a person who may add photos sees them; a tester never does. */
export function SamplePhotos({ sample }: Readonly<{ sample: Sample }>) {
  const t = useT();
  const { call } = useSession();
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
    <View style={shared.section}>
      <Text accessibilityRole="header" style={shared.heading}>
        {t("sample.photos")}
      </Text>
      {unsent.load.state === "ready" &&
        unsent.load.value.map((photo) => (
          <Unsent
            key={photo.key}
            photo={photo}
            busy={busy}
            onSend={() => settle(() => sendPhoto(photo, call))}
            onDiscard={() => settle(async () => discardPhoto(photo))}
          />
        ))}
      <ActionProblem problem={problem?.load ?? null} gone={t("sample.gone")} onRetry={() => problem?.retry()} />
      {sent.load.state === "ready" && <Sent photos={sent.load.value.photos} />}
      <Button
        label={t("sample.takePhoto")}
        onPress={() =>
          router.push({ pathname: "/samples/[id]/photo", params: { id: String(sample.id), code: sample.code } })
        }
        testID="take-photo"
      />
    </View>
  );
}

function Unsent({
  photo,
  busy,
  onSend,
  onDiscard,
}: Readonly<{ photo: UnsentPhoto; busy: boolean; onSend: () => void; onDiscard: () => void }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <View style={shared.card} testID={`unsent-photo-${photo.key}`}>
      <Text style={shared.label}>{t("photo.unsent", { date: formatMoment(photo.takenAt, language) })}</Text>
      <Button label={t("photo.send")} onPress={onSend} primary disabled={busy} testID={`send-photo-${photo.key}`} />
      <Button label={t("photo.discard")} onPress={onDiscard} disabled={busy} testID={`discard-photo-${photo.key}`} />
    </View>
  );
}

function Sent({ photos }: Readonly<{ photos: SamplePhoto[] }>) {
  const t = useT();
  const { language } = useSession();
  if (!photos.length) {
    return <Text style={shared.detail}>{t("sample.noPhotos")}</Text>;
  }
  return photos.map((photo) => (
    <View key={photo.id} style={shared.card} testID={`sample-photo-${photo.id}`}>
      <Text style={shared.label}>{photo.name}</Text>
      <Text style={shared.detail}>
        {t("sample.photoTaken", { name: photo.created_by, date: formatMoment(photo.created_at, language) })}
      </Text>
    </View>
  ));
}
