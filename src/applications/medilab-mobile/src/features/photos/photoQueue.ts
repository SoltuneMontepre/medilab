import { randomUUID } from "expo-crypto";
import { Directory, File, Paths } from "expo-file-system";

import type { SamplePhoto } from "../../api";
import type { Session } from "../../session";

/** A photo taken on the phone and kept there until MediLab has it or the person discards it. Its key is the
 * Idempotency-Key it is sent with every time, so a photo sent again after a lost answer is attached once. */
export interface UnsentPhoto {
  key: string;
  sampleId: number;
  name: string;
  takenAt: string;
}

// The app's own folder of unsent photos: each photo and a note of what it is, named by its key.
const FOLDER = "unsent-photos";
const PHOTO_TYPE = "image/jpeg";

function folder(): Directory {
  const unsent = new Directory(Paths.document, FOLDER);
  if (!unsent.exists) {
    unsent.create({ intermediates: true });
  }
  return unsent;
}

function photoFile(key: string): File {
  return new File(folder(), `${key}.jpg`);
}

function noteFile(key: string): File {
  return new File(folder(), `${key}.json`);
}

/** Keeps the picture the camera took of the sample on the phone, out of the camera's cache, before it is sent. */
export async function keepPhoto(sampleId: number, code: string, pictureUri: string): Promise<UnsentPhoto> {
  const key = randomUUID();
  const takenAt = new Date().toISOString();
  // A photo's name is one name, never a path: the moment it was taken without its colons.
  const photo: UnsentPhoto = { key, sampleId, name: `${code}-${takenAt.replace(/[:.]/g, "-")}.jpg`, takenAt };
  await new File(pictureUri).move(photoFile(key));
  const note = noteFile(key);
  note.create();
  await note.write(JSON.stringify(photo));
  return photo;
}

/** The photos of the sample still on the phone, oldest first. */
export async function unsentPhotos(sampleId: number): Promise<UnsentPhoto[]> {
  const notes = folder()
    .list()
    .filter((entry): entry is File => entry instanceof File && entry.name.endsWith(".json"));
  const photos: UnsentPhoto[] = await Promise.all(notes.map(async (note) => JSON.parse(await note.text())));
  return photos.filter((photo) => photo.sampleId === sampleId).sort((a, b) => a.takenAt.localeCompare(b.takenAt));
}

/** Sends the photo to its sample, then removes it from the phone. A photo MediLab did not get stays on the phone. */
export async function sendPhoto(photo: UnsentPhoto, call: Session["call"]): Promise<SamplePhoto | null> {
  const data = await photoFile(photo.key).base64();
  const sent = await call<SamplePhoto>(`/samples/${photo.sampleId}/photos`, {
    method: "POST",
    body: { name: photo.name, mimetype: PHOTO_TYPE, data },
    headers: { "Idempotency-Key": photo.key },
  });
  discardPhoto(photo);
  return sent;
}

/** Removes the photo from the phone without sending it. */
export function discardPhoto(photo: UnsentPhoto): void {
  for (const file of [photoFile(photo.key), noteFile(photo.key)]) {
    if (file.exists) {
      file.delete();
    }
  }
}
