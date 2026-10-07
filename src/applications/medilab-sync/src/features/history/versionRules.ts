import type { FileVersion } from "../../types";

/** Trạng thái khả dụng của chức năng khôi phục một phiên bản tệp. */
export type RestoreActionState = {
  isCurrent: boolean;
  canRestore: boolean;
  reason?: "already_current" | "object_unavailable" | "closed";
};

/**
 * Quyết định tính khả dụng của thao tác khôi phục cho một phiên bản tệp.
 *
 * Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
 *
 * Quy tắc:
 * 1. Phiên bản hiện hành (`is_canonical = true`) không được phép khôi phục lại vì đã là hiện tại.
 * 2. Phiên bản lịch sử nhưng đối tượng MinIO không còn (`object_available = false`) bị vô hiệu hóa.
 * 3. Phiên bản lịch sử thuộc thư mục/mẫu đã đóng (`can_restore = false`) bị vô hiệu hóa.
 * 4. Phiên bản lịch sử hợp lệ (`can_restore = true`, `object_available != false`) được phép khôi phục.
 */
export function getRestoreActionState(version: FileVersion | null): RestoreActionState {
  if (!version) {
    return { isCurrent: false, canRestore: false };
  }
  // Phiên bản chuẩn hiện hành không cho phép khôi phục
  if (version.is_canonical) {
    return { isCurrent: true, canRestore: false, reason: "already_current" };
  }
  // Đối tượng lưu trữ không còn trên máy chủ
  if (version.object_available === false) {
    return { isCurrent: false, canRestore: false, reason: "object_unavailable" };
  }
  // Quyền khôi phục bị hạn chế do mẫu/thư mục đã đóng
  if (!version.can_restore) {
    return { isCurrent: false, canRestore: false, reason: "closed" };
  }
  return { isCurrent: false, canRestore: true };
}

/**
 * Xác định phiên bản cần chọn khi tải trang mới, chuyển trang phân trang hoặc sau khi khôi phục.
 *
 * Quy tắc:
 * 1. Ưu tiên `preferredVersionId` (ví dụ phiên bản mới vừa khôi phục xong).
 * 2. Nếu không có hoặc không tìm thấy, giữ `currentSelectedId` nếu phiên bản đó còn nằm trên trang.
 * 3. Nếu phiên bản trước đó không còn trên trang mới, chọn phiên bản đầu tiên của trang (phiên bản mới nhất hiển thị).
 * 4. Trả về `null` nếu danh sách trống.
 */
export function resolveSelectedVersion(
  items: FileVersion[],
  preferredVersionId?: number | null,
  currentSelectedId?: number | null,
): FileVersion | null {
  if (items.length === 0) {
    return null;
  }
  const candidateId = preferredVersionId ?? currentSelectedId ?? items[0].id;
  return items.find((item) => item.id === candidateId) ?? items[0];
}
