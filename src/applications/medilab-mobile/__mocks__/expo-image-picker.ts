// The camera and the gallery as the tests drive them: each pick answers the next photo a test planned, or a cancel.
type Picked =
  | { canceled: true; assets: null }
  | { canceled: false; assets: { base64: string; fileName: string; mimeType: string }[] };

const planned: Picked[] = [];

/** The person takes or picks this photo next; null cancels. */
export function nextPhoto(photo: { base64: string; fileName: string; mimeType: string } | null) {
  planned.push(photo ? { canceled: false, assets: [photo] } : { canceled: true, assets: null });
}

function pick(): Promise<Picked> {
  return Promise.resolve(planned.shift() ?? { canceled: true, assets: null });
}

export const requestCameraPermissionsAsync = jest.fn(async () => ({ granted: true }));
export const launchCameraAsync = jest.fn(pick);
export const launchImageLibraryAsync = jest.fn(pick);
