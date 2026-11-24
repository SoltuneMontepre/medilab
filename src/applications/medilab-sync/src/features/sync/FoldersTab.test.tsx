import { describe, expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import type { FolderRow } from "../../types";
import { FolderCard, HomeFolderCard } from "./FoldersTab";

/** Render một thẻ thư mục bằng tiếng Anh để so chuỗi không dấu. */
function renderCard(folder: FolderRow): string {
  return renderToString(
    <LocaleProvider locale="en">
      <FolderCard
        folder={folder}
        busy={false}
        onOpen={() => {}}
        onManageAccess={() => {}}
        onUnregister={() => {}}
      />
    </LocaleProvider>,
  );
}

const folder: FolderRow = {
  id: 1,
  local_path: "/data/hplc",
  remote_id: 42,
  logical_root: "HPLC",
  enabled: true,
  recursive: true,
  sample_code: "HS.1",
  category: "raw",
  sync_mode: "upload_only",
  access_state: "ok",
};

describe("HomeFolderCard", () => {
  /** Render thẻ thư mục chính bằng tiếng Anh. */
  function renderHome(homeFolder: string | null): string {
    return renderToString(
      <LocaleProvider locale="en">
        <HomeFolderCard homeFolder={homeFolder} busy={false} onChoose={() => {}} />
      </LocaleProvider>,
    );
  }

  test("asks for one folder and says sample folders then come by themselves", () => {
    const html = renderHome(null);
    expect(html).toContain("by itself");
    expect(html).toContain(">Choose folder</button>");
  });

  test("shows the chosen folder without the Windows prefix and offers to change it", () => {
    const html = renderHome("\\\\?\\C:\\MediLab");
    expect(html).toContain("C:\\MediLab");
    expect(html).not.toContain("\\\\?\\");
    expect(html).toContain(">Change folder</button>");
  });
});

describe("FolderCard", () => {
  test("names the sample and its category in words and leaves out server ids", () => {
    const html = renderCard(folder);
    expect(html).toContain("HPLC");
    expect(html).toContain("HS.1");
    expect(html).toContain("Raw data");
    expect(html).not.toContain("remote_id");
  });

  test("says whether the folder also downloads what others save", () => {
    expect(renderCard(folder)).toContain("Upload only");
    expect(renderCard({ ...folder, sync_mode: "two_way" })).toContain("Two-way");
    expect(renderCard({ ...folder, sync_mode: null })).not.toContain("Upload only");
  });

  test("offers to open the folder", () => {
    expect(renderCard(folder)).toContain("Open folder");
  });
});
