import { fireEvent, screen } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import { fakeMediLab, kept } from "../../testing/fakeMediLab";
import { memoryFiles } from "../../testing/memoryFiles";
import { renderSignedIn } from "../../testing/renderSignedIn";
import { sample } from "../../testing/sample";
import { SampleScreen } from "../scanning/SampleScreen";
import { keepPhoto } from "./photoQueue";

jest.mock("../../config", () => ({ serverUrl: "https://lab.example" }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useFocusEffect: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));

const API = "https://lab.example/medilab/api/v1";
// The sample as sample delivery staff see it, who may photograph it.
const STAFF_SAMPLE = { status: 200, body: sample({ customer: "Công ty An Phú", handover: null, tasks: [], can_add_photos: true }) };
const COLLECTED = {
  id: 7,
  name: "PTN.2026.0042-collected.jpg",
  mimetype: "image/jpeg",
  created_at: "2026-11-16T03:00:00Z",
  created_by: "Lê Thị Lan",
};

// A photo the camera took of sample 42 that MediLab did not get.
async function unsentPhoto() {
  memoryFiles.set("file:///cache/Camera/1.jpg", "photo of the sample");
  return keepPhoto(42, "PTN.2026.0042", "file:///cache/Camera/1.jpg");
}

describe("SamplePhotos", () => {
  beforeEach(() => {
    kept().clear();
    memoryFiles.clear();
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "42" });
  });

  it("lists the sample's photos and opens the camera for another", async () => {
    const mediLab = fakeMediLab(STAFF_SAMPLE, { status: 200, body: { photos: [COLLECTED] } });
    await renderSignedIn(<SampleScreen />);

    expect(await screen.findByText("PTN.2026.0042-collected.jpg")).toBeOnTheScreen();
    expect(screen.getByText(/^Chụp bởi Lê Thị Lan lúc /)).toBeOnTheScreen();
    expect(mediLab.sent[1].url).toBe(`${API}/samples/42/photos`);

    await fireEvent.press(screen.getByTestId("take-photo"));

    expect(router.push).toHaveBeenCalledWith({
      pathname: "/samples/[id]/photo",
      params: { id: "42", code: "PTN.2026.0042" },
    });
  });

  it("sends again a photo kept on the phone with the key it was first sent with", async () => {
    const photo = await unsentPhoto();
    const mediLab = fakeMediLab(
      STAFF_SAMPLE,
      { status: 200, body: { photos: [] } },
      { status: 200, body: COLLECTED },
      { status: 200, body: { photos: [COLLECTED] } },
    );
    await renderSignedIn(<SampleScreen />);

    await fireEvent.press(await screen.findByTestId(`send-photo-${photo.key}`));

    expect(mediLab.sent[2]).toMatchObject({
      method: "POST",
      url: `${API}/samples/42/photos`,
      headers: { "Idempotency-Key": photo.key },
      body: { name: photo.name, mimetype: "image/jpeg", data: btoa("photo of the sample") },
    });
    expect(await screen.findByTestId("sample-photo-7")).toBeOnTheScreen();
    expect(screen.queryByTestId(`unsent-photo-${photo.key}`)).toBeNull();
    expect(memoryFiles.size).toBe(0);
  });

  it("keeps an unsent photo on the phone while MediLab cannot be reached, until it is discarded", async () => {
    const photo = await unsentPhoto();
    const noPhotos = { status: 200, body: { photos: [] } };
    fakeMediLab(STAFF_SAMPLE, noPhotos, "unreachable", noPhotos, noPhotos);
    await renderSignedIn(<SampleScreen />);

    await fireEvent.press(await screen.findByTestId(`send-photo-${photo.key}`));

    expect(await screen.findByText(/^Không kết nối được MediLab/)).toBeOnTheScreen();
    expect(screen.getByTestId(`unsent-photo-${photo.key}`)).toBeOnTheScreen();
    expect(memoryFiles.size).toBe(2);

    await fireEvent.press(screen.getByTestId(`discard-photo-${photo.key}`));

    expect(screen.queryByTestId(`unsent-photo-${photo.key}`)).toBeNull();
    expect(memoryFiles.size).toBe(0);
  });

  it("shows a tester no photos and asks MediLab for none", async () => {
    const mediLab = fakeMediLab({ status: 200, body: sample() });
    await renderSignedIn(<SampleScreen />);

    expect(await screen.findByText("PTN.2026.0042")).toBeOnTheScreen();
    expect(screen.queryByText("Ảnh mẫu")).toBeNull();
    expect(screen.queryByTestId("take-photo")).toBeNull();
    expect(mediLab.sent).toHaveLength(1);
  });
});
