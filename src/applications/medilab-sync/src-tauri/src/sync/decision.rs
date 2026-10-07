//! Quyết định đồng bộ ba chiều: nội dung cục bộ so với base đã đồng bộ gần nhất so với bản
//! chuẩn trên server.
//!
//! Không dùng mtime hay "timestamp mới nhất thắng". So bằng SHA-256 (+ id version đã biết).
//!
//! | Cục bộ L so với base B | Server R so với base B | Hành động |
//! | --- | --- | --- |
//! | L == B (sạch) | R đã đổi | Tải xuống R |
//! | L đã đổi | R == B | Tải lên |
//! | L đã đổi | R đã đổi, L != R | Xung đột |
//! | L == R | bất kỳ | Cập nhật base / không truyền (tự vọng lại chính mình) |
//! | không có tệp cục bộ | server có tồn tại | Tải xuống |

/// Hành động đồng bộ được chọn cho một tệp, sau khi so hash nội dung ba chiều.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyncAction {
    Download,
    Upload,
    Conflict,
    AdvanceBase,
}

/// Chọn hành động đồng bộ bằng cách so hash nội dung cục bộ, base đã đồng bộ, và server — không
/// bao giờ dùng mtime.
pub fn decide_sync_action(
    local_hash: Option<&str>,
    last_synced_hash: Option<&str>,
    remote_hash: &str,
) -> SyncAction {
    if remote_hash.is_empty() {
        return SyncAction::AdvanceBase;
    }
    if let Some(local) = local_hash {
        if local == remote_hash {
            return SyncAction::AdvanceBase;
        }
        let local_clean = last_synced_hash == Some(local);
        let remote_changed = last_synced_hash != Some(remote_hash);
        if local_clean && remote_changed {
            return SyncAction::Download;
        }
        if !local_clean && !remote_changed {
            return SyncAction::Upload;
        }
        if !local_clean && remote_changed {
            return SyncAction::Conflict;
        }
        return SyncAction::Download;
    }
    // Không có tệp cục bộ mà server có version chuẩn → luôn tải xuống, kể cả khi base đã bằng
    // server (tệp từng đồng bộ rồi bị xóa trên máy này). App không lan truyền thao tác xóa, nên
    // "base khớp" không có nghĩa là có tệp trên đĩa.
    SyncAction::Download
}

#[cfg(test)]
mod tests {
    use super::{decide_sync_action, SyncAction};

    /// Cục bộ sạch, server đã đổi → tải xuống.
    #[test]
    fn local_clean_remote_changed_downloads() {
        assert_eq!(
            decide_sync_action(Some("base"), Some("base"), "remote"),
            SyncAction::Download
        );
    }

    /// Cục bộ đã đổi, server sạch → tải lên.
    #[test]
    fn local_changed_remote_clean_uploads() {
        assert_eq!(
            decide_sync_action(Some("local"), Some("base"), "base"),
            SyncAction::Upload
        );
    }

    /// Cả hai bên cùng đổi, nội dung khác nhau → xung đột.
    #[test]
    fn both_changed_conflicts() {
        assert_eq!(
            decide_sync_action(Some("local"), Some("base"), "remote"),
            SyncAction::Conflict
        );
    }

    /// Cục bộ và server cùng hash (dù base khác hay giống) → chỉ cập nhật base, không truyền.
    #[test]
    fn same_hash_advances_base_without_transfer() {
        assert_eq!(
            decide_sync_action(Some("v5"), Some("v4"), "v5"),
            SyncAction::AdvanceBase
        );
        assert_eq!(
            decide_sync_action(Some("v5"), Some("v5"), "v5"),
            SyncAction::AdvanceBase
        );
    }

    /// Tự vọng lại chính lượt tải lên của mình không được kích hoạt tải xuống.
    #[test]
    fn own_upload_echo_does_not_download() {
        assert_eq!(
            decide_sync_action(Some("uploaded"), Some("uploaded"), "uploaded"),
            SyncAction::AdvanceBase
        );
    }

    /// Sau một lượt phục hồi version, cục bộ còn sạch với base cũ thì phải tải xuống bản mới.
    #[test]
    fn restore_downloads_when_local_still_clean() {
        assert_eq!(
            decide_sync_action(Some("v3-hash"), Some("v3-hash"), "v1-hash"),
            SyncAction::Download
        );
    }

    /// Chưa có tệp cục bộ, server có tồn tại → tải xuống.
    #[test]
    fn missing_local_file_downloads() {
        assert_eq!(
            decide_sync_action(None, None, "remote"),
            SyncAction::Download
        );
    }

    /// Tệp từng đồng bộ (base = server) nhưng đã bị xóa trên máy này → tải xuống lại, không phải
    /// "đã đồng bộ".
    #[test]
    fn locally_deleted_after_sync_downloads_again() {
        assert_eq!(
            decide_sync_action(None, Some("current"), "current"),
            SyncAction::Download
        );
    }

    /// Chưa biết base, cục bộ khác server → xung đột (không đoán mò là an toàn để ghi đè).
    #[test]
    fn unknown_base_with_divergent_local_is_conflict() {
        assert_eq!(
            decide_sync_action(Some("disk"), None, "remote"),
            SyncAction::Conflict
        );
    }
}
