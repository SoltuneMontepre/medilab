/**
 * Kiểm thử đơn vị cho quy tắc khôi phục và chọn phiên bản lịch sử.
 *
 * Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
 */
import { describe, expect, test } from "bun:test";
import type { FileVersion } from "../../types";
import { getRestoreActionState, resolveSelectedVersion } from "./versionRules";
import { translate } from "../../i18n";

/** Mock helper tạo FileVersion phục vụ kiểm thử. */
function createMockVersion(params: {
  id: number;
  version_number: number;
  is_canonical?: boolean;
  can_restore?: boolean;
  object_available?: boolean | null;
  content_hash?: string;
}): FileVersion {
  return {
    id: params.id,
    file_id: 100,
    version_number: params.version_number,
    size: 1024,
    content_hash: params.content_hash ?? `hash-${params.version_number}`,
    checksum_algorithm: "sha256",
    source: params.is_canonical ? "DESKTOP_SYNC" : "ONLYOFFICE",
    created_at: "2026-09-19 05:52",
    created_by: { id: 1, name: "Admin" },
    device: { id: 1, name: "LAB-PC" },
    is_canonical: params.is_canonical ?? false,
    parent_version_id: params.version_number > 1 ? params.id - 1 : null,
    parent_version_number: params.version_number > 1 ? params.version_number - 1 : null,
    restored_from_version_id: null,
    restored_from_version_number: null,
    object_available: params.object_available ?? true,
    can_restore: params.can_restore ?? true,
  };
}

const v1 = createMockVersion({ id: 10, version_number: 1 });
const v2 = createMockVersion({ id: 20, version_number: 2 });
const v3 = createMockVersion({ id: 30, version_number: 3, is_canonical: true });
const pageItems = [v3, v2, v1];

describe("resolveSelectedVersion", () => {
  test("mở dialog chọn mục đầu tiên (hiện tại/mới nhất)", () => {
    const initial = resolveSelectedVersion(pageItems, null, null);
    expect(initial?.id).toBe(30);
    expect(initial?.version_number).toBe(3);
  });

  test("giữ lựa chọn khi người dùng bấm một phiên bản cụ thể", () => {
    expect(resolveSelectedVersion(pageItems, null, 20)?.id).toBe(20);
    expect(resolveSelectedVersion(pageItems, null, 10)?.id).toBe(10);
  });

  test("sau khôi phục ưu tiên phiên bản mới (preferredVersionId)", () => {
    const v4 = createMockVersion({ id: 40, version_number: 4, is_canonical: true });
    const restored = resolveSelectedVersion([v4, v3, v2, v1], 40, 10);
    expect(restored?.id).toBe(40);
    expect(restored?.version_number).toBe(4);
  });

  test("chuyển trang: rơi về mục đầu trang mới nếu phiên bản trước không nằm trên trang đó", () => {
    expect(resolveSelectedVersion([v1], null, 30)?.id).toBe(10);
  });

  test("danh sách rỗng trả về null", () => {
    expect(resolveSelectedVersion([], null, null)).toBeNull();
  });
});

describe("getRestoreActionState", () => {
  test("phiên bản hiện tại không khôi phục được, lý do already_current", () => {
    const rules = getRestoreActionState(v3);
    expect(rules.isCurrent).toBe(true);
    expect(rules.canRestore).toBe(false);
    expect(rules.reason).toBe("already_current");
  });

  test("phiên bản lịch sử hợp lệ khôi phục được", () => {
    const rules = getRestoreActionState(v2);
    expect(rules.isCurrent).toBe(false);
    expect(rules.canRestore).toBe(true);
    expect(rules.reason).toBeUndefined();
  });

  test("mất object MinIO: không khôi phục, lý do object_unavailable", () => {
    const missing = createMockVersion({ id: 15, version_number: 1, object_available: false });
    const rules = getRestoreActionState(missing);
    expect(rules.canRestore).toBe(false);
    expect(rules.reason).toBe("object_unavailable");
  });

  test("mẫu đã đóng (can_restore=false): lý do closed", () => {
    const closed = createMockVersion({ id: 16, version_number: 1, can_restore: false });
    const rules = getRestoreActionState(closed);
    expect(rules.canRestore).toBe(false);
    expect(rules.reason).toBe("closed");
  });

  test("null version an toàn", () => {
    expect(getRestoreActionState(null).canRestore).toBe(false);
  });
});

describe("thông điệp tiếng Việt của lịch sử phiên bản", () => {
  test("xác nhận và giải thích khôi phục không ngụ ý xóa", () => {
    expect(translate("vi", "history.restoreConfirm", { version: 2 })).toBe("Khôi phục phiên bản v2?");
    const help = translate("vi", "history.restoreHelp", { version: 2 });
    expect(help).toContain("giữ lại trong lịch sử");
    expect(help).not.toContain("xóa");
  });

  test("thông báo sau khôi phục, nhãn hiện tại và gợi ý bảng", () => {
    expect(translate("vi", "history.restoredSuccess", { version: 1 })).toBe(
      "Đã khôi phục v1 thành phiên bản hiện tại mới.",
    );
    expect(translate("vi", "history.alreadyCurrent")).toBe("Phiên bản hiện tại");
    expect(translate("vi", "history.tableHint")).toBe(
      "Chọn một phiên bản để xem chi tiết hoặc khôi phục.",
    );
  });
});
