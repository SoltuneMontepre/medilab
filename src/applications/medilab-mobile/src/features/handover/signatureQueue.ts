import { Directory, File, Paths } from "expo-file-system";

import type { HandoverRecord } from "../../api";
import type { Session } from "../../session";

/** A customer's signature kept on the phone until MediLab has it or the person discards it. Signing again from the
 * same phone answers the signed record, so a signature sent again after a lost answer is recorded once. */
export interface UnsentSignature {
  recordId: number;
  signature: string;
  signedAt: string;
}

// The app's own folder of unsent signatures: one for each handover record, named by the record.
const FOLDER = "unsent-signatures";

function signatureFile(recordId: number): File {
  return new File(new Directory(Paths.document, FOLDER), `${recordId}.json`);
}

/** Keeps the customer's signature of the record on the phone, as a PNG in base64, before it is sent. */
export async function keepSignature(recordId: number, signature: string): Promise<UnsentSignature> {
  const kept: UnsentSignature = { recordId, signature, signedAt: new Date().toISOString() };
  const folder = new Directory(Paths.document, FOLDER);
  if (!folder.exists) {
    folder.create({ intermediates: true });
  }
  const file = signatureFile(recordId);
  if (!file.exists) {
    file.create();
  }
  await file.write(JSON.stringify(kept));
  return kept;
}

/** The record's signature still on the phone, if any. */
export async function unsentSignature(recordId: number): Promise<UnsentSignature | null> {
  const file = signatureFile(recordId);
  return file.exists ? JSON.parse(await file.text()) : null;
}

/** Sends the signature from the app's confirmation step, then removes it from the phone. A signature MediLab did not
 * get stays on the phone. */
export async function sendSignature(kept: UnsentSignature, call: Session["call"]): Promise<HandoverRecord | null> {
  const record = await call<HandoverRecord>(`/handover-records/${kept.recordId}/sign`, {
    method: "POST",
    body: { signature: kept.signature, confirmed: true },
  });
  discardSignature(kept.recordId);
  return record;
}

/** Removes the record's signature from the phone without sending it. */
export function discardSignature(recordId: number): void {
  const file = signatureFile(recordId);
  if (file.exists) {
    file.delete();
  }
}
