import { describe, expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import type { FolderRow } from "../../types";
import { HomeFolderCard } from "./FoldersTab";
import { FolderCard, FolderExplorer } from "./FolderExplorer";

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
        onRebind={() => {}}
      />
    </LocaleProvider>,
  );
}

/** Render bảng thư mục đã thêm bằng tiếng Anh. */
function renderGroups(folders: FolderRow[], dropFolderId: number | null = null): string {
  return renderToString(
    <LocaleProvider locale="en">
      <FolderExplorer
        folders={folders}
        dropFolderId={dropFolderId}
        busy={false}
        onOpen={() => {}}
        onManageAccess={() => {}}
        onUnregister={() => {}}
        onRebind={() => {}}
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

  test("offers to reconnect only a folder that lost its server link", () => {
    expect(renderCard(folder)).not.toContain("Reconnect");
    expect(renderCard({ ...folder, remote_id: null, access_state: "unbound" })).toContain(">Reconnect</button>");
  });
});

describe("FolderExplorer", () => {
  const raw = { ...folder, id: 2, sample_code: "PTN.1", logical_root: "PTN.1-raw", local_path: "C:/lab/PTN.1/Raw Data" };
  const result = { ...raw, id: 3, logical_root: "PTN.1-result", category: "result", local_path: "C:/lab/PTN.1/Results" };
  const loose = { ...folder, id: 4, sample_code: null, logical_root: "Notes", local_path: "C:/notes" };

  test("opens only samples that need attention, and lists their folders by name with loose folders last", () => {
    const html = renderGroups([loose, raw, { ...result, access_state: "unbound" }]);
    expect(html).toContain("2 folders");
    expect(html).toContain("Raw Data");
    expect(html).toContain("Results");
    expect(html.indexOf("PTN.1")).toBeLessThan(html.indexOf("Other folders"));
    expect(html).toContain('data-drop-folder-id="2"');
    expect(html).not.toContain('data-drop-folder-id="4"');
  });

  test("starts a sample with every folder linked collapsed", () => {
    const html = renderGroups([raw, result]);
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("Raw Data");
  });

  test("shows each folder's type, mode and link state in short words", () => {
    const html = renderGroups([raw, { ...result, access_state: "unbound", sync_mode: "two_way" }]);
    expect(html).toContain("Raw data");
    expect(html).toContain("Upload only");
    expect(html).toContain("Two-way");
    expect(html).toContain("Linked");
    expect(html).toContain("Not linked");
  });

  test("flags a group with a folder that needs attention", () => {
    expect(renderGroups([raw, result])).not.toContain("Needs attention");
    expect(renderGroups([raw, { ...result, access_state: "unbound" }])).toContain("Needs attention");
  });

  test("highlights the folder files are dragged over", () => {
    const unbound = { ...result, access_state: "unbound" };
    expect(renderGroups([raw, unbound], 3)).toMatch(/bg-blue-100[^>]*data-drop-folder-id="3"|data-drop-folder-id="3"[^>]*bg-blue-100/);
    expect(renderGroups([raw, unbound])).not.toContain("bg-blue-100");
  });
});
