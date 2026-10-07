//! Test đối soát cục bộ khi thư mục bị gỡ (unbind) trong lúc một lượt quét đang chạy: lượt quét
//! đọc danh sách folder MỘT lần rồi mới hash từng tệp (có thể mất nhiều giây với tệp lớn), nên
//! folder có thể biến mất (cascade xóa `sync_file`/`sync_job`) trước khi tệp được ghi vào DB.
//!
//! Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable

use crate::api::FolderChangeDto;
use crate::storage::{Db, FolderRow};
use crate::sync::engine::{
    accept_server_version_in, enqueue_if_changed, plan_remote_change, reconcile_folders,
    RemoteOutcome,
};
use std::path::{Path, PathBuf};

/// DB tạm và thư mục gốc để tạo folder cục bộ.
fn temp_db() -> (tempfile::TempDir, Db) {
    let dir = tempfile::tempdir().unwrap();
    let db = Db::open(&dir.path().join("t.db")).unwrap();
    (dir, db)
}

/// Bind một thư mục cục bộ `name` (tạo trên đĩa) chứa một tệp `file`; trả dòng folder.
fn bind_with_file(db: &Db, root: &Path, name: &str, file: &str, remote_id: i64) -> FolderRow {
    let local = root.join(name);
    std::fs::create_dir_all(&local).unwrap();
    std::fs::write(local.join(file), format!("content of {name}/{file}")).unwrap();
    let id = db
        .upsert_folder(local.to_str().unwrap(), name, Some(remote_id), true, &[])
        .unwrap();
    db.list_folders()
        .unwrap()
        .into_iter()
        .find(|folder| folder.id == id)
        .unwrap()
}

/// Số dòng `sync_file` của tệp `a.txt` trong một folder (0 hoặc 1).
fn file_rows(db: &Db, folder_id: i64) -> usize {
    usize::from(db.file_by_path(folder_id, "a.txt").unwrap().is_some())
}

/// Chuỗi đúng như log native: lượt quét đã đọc danh sách folder, người dùng gỡ thư mục (xóa
/// folder + cascade), rồi lượt quét ghi tệp của folder cũ → không được lỗi FK; tệp bị bỏ qua.
#[test]
fn unbind_during_scan_skips_the_file_instead_of_failing_on_foreign_key() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "unbound", "a.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(folder.id).unwrap();
    let path: PathBuf = PathBuf::from(&snapshot[0].local_path).join("a.txt");
    let result = enqueue_if_changed(&db, &snapshot[0], &path, "a.txt");
    assert!(
        result.is_ok(),
        "{:?}",
        result.err().map(|err| err.to_string())
    );
    assert!(!result.unwrap(), "nothing queued for an unbound folder");
    assert_eq!(file_rows(&db, folder.id), 0);
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Folder A bị gỡ giữa lượt đối soát không được làm hủy cả lượt: folder B vẫn được quét.
#[test]
fn unbinding_one_folder_mid_reconcile_does_not_abort_the_others() {
    let (dir, db) = temp_db();
    let unbound = bind_with_file(&db, dir.path(), "unbound", "a.txt", 615);
    let kept = bind_with_file(&db, dir.path(), "kept", "a.txt", 616);
    let snapshot = db.list_folders().unwrap();
    assert_eq!(
        snapshot[0].id, unbound.id,
        "unbound folder is scanned first"
    );
    db.delete_folder(unbound.id).unwrap();
    let result = reconcile_folders(&db, snapshot);
    assert!(
        result.is_ok(),
        "{:?}",
        result.err().map(|err| err.to_string())
    );
    assert!(
        db.file_by_path(kept.id, "a.txt").unwrap().is_some(),
        "other folder still scanned"
    );
    let jobs = db.list_jobs().unwrap();
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0].folder_id, kept.id);
}

/// Gỡ rồi gắn một thư mục KHÁC ngay sau đó: SQLite tái dùng rowid nên folder mới có thể mang
/// đúng `id` cũ. Lượt quét cũ không được gán tệp của đường dẫn cũ vào folder mới.
#[test]
fn stale_scan_never_attributes_files_to_a_rebound_folder_that_reused_the_id() {
    let (dir, db) = temp_db();
    let old = bind_with_file(&db, dir.path(), "old-path", "a.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(old.id).unwrap();
    let new = bind_with_file(&db, dir.path(), "new-path", "other.txt", 616);
    assert_eq!(new.id, old.id, "SQLite reused the folder id");
    let path = PathBuf::from(&snapshot[0].local_path).join("a.txt");
    let queued = enqueue_if_changed(&db, &snapshot[0], &path, "a.txt").unwrap();
    assert!(!queued, "file of the old path must not be queued");
    assert!(db.file_by_path(new.id, "a.txt").unwrap().is_none());
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Một thay đổi canonical từ change feed/hydrate cho tệp remote `file_id` ở `path`.
fn remote_change(file_id: i64, path: &str) -> FolderChangeDto {
    FolderChangeDto {
        id: 1,
        change_type: "CANONICAL_VERSION".into(),
        folder_id: 615,
        file_id,
        logical_path: path.into(),
        current_version_id: Some(7),
        version_number: Some(1),
        content_hash: Some("a".repeat(64)),
        size: 10,
        source: Some("DESKTOP".into()),
        changed_at: None,
        changed_by_device_id: None,
    }
}

/// A — hydrate/poll đã đọc danh sách folder, người dùng gỡ thư mục, rồi thay đổi remote được
/// áp tiếp: không lỗi FK, không tạo lại folder, không có dòng tệp/job nào.
#[tokio::test]
async fn remote_change_after_unbind_is_skipped_without_foreign_key_error() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "hydrating", "local.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(folder.id).unwrap();
    let result = plan_remote_change(&db, &snapshot[0], &remote_change(900, "report.pdf")).await;
    assert!(
        result.is_ok(),
        "{:?}",
        result.err().map(|err| err.to_string())
    );
    assert_eq!(result.unwrap(), RemoteOutcome::Skipped);
    assert!(
        db.list_folders().unwrap().is_empty(),
        "folder must not be recreated"
    );
    assert!(db.file_by_path(folder.id, "report.pdf").unwrap().is_none());
    assert!(db.list_jobs().unwrap().is_empty());
}

/// B — poll đang chạy cho folder cũ, người dùng gỡ nó và gắn thư mục KHÁC (remote khác) trùng
/// rowid: tệp remote của folder cũ không được map/xếp hàng vào folder mới.
#[tokio::test]
async fn remote_change_of_old_binding_is_not_mapped_into_a_rebound_folder_with_reused_id() {
    let (dir, db) = temp_db();
    let old = bind_with_file(&db, dir.path(), "old-remote", "local.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(old.id).unwrap();
    let new = bind_with_file(&db, dir.path(), "new-remote", "other.txt", 616);
    assert_eq!(new.id, old.id, "SQLite reused the folder id");
    let outcome = plan_remote_change(&db, &snapshot[0], &remote_change(900, "report.pdf"))
        .await
        .unwrap();
    assert_eq!(outcome, RemoteOutcome::Skipped);
    assert!(
        db.file_by_path(new.id, "report.pdf").unwrap().is_none(),
        "remote file of the old folder mapped into the new one"
    );
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Thư mục bị gỡ giữa bước tạo ánh xạ và bước xếp hàng download (khe chờ hash tệp cục bộ):
/// bước sau bị bỏ qua thay vì INSERT job trỏ tới tệp/folder đã cascade xóa.
#[test]
fn download_after_unbind_between_mapping_and_enqueue_is_skipped() {
    use crate::storage::enqueue_download_on;
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "mid-flight", "local.txt", 615);
    let binding = folder.binding();
    let file_id = db
        .ensure_remote_mapping_bound(&binding, "report.pdf", 900, Some(7))
        .unwrap()
        .expect("binding still current");
    db.delete_folder(folder.id).unwrap();
    let queued = db.with_bound_file(&binding, file_id, |conn| {
        enqueue_download_on(
            conn,
            binding.id,
            file_id,
            "report.pdf",
            10,
            900,
            7,
            "hash",
            Some(1),
        )
    });
    assert!(
        queued.is_ok(),
        "{:?}",
        queued.err().map(|err| err.to_string())
    );
    assert_eq!(queued.unwrap(), None);
    assert!(db.list_jobs().unwrap().is_empty());
}

/// C — binding không đổi: change feed/hydrate vẫn map tệp remote và xếp hàng download như cũ.
#[tokio::test]
async fn remote_change_with_unchanged_binding_is_mapped_and_queued() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "steady", "local.txt", 615);
    let outcome = plan_remote_change(&db, &folder, &remote_change(900, "report.pdf"))
        .await
        .unwrap();
    assert_eq!(outcome, RemoteOutcome::DownloadQueued);
    let mapped = db.file_by_path(folder.id, "report.pdf").unwrap().unwrap();
    assert_eq!(mapped.remote_file_id, Some(900));
    let jobs = db.list_jobs().unwrap();
    assert_eq!(jobs.len(), 1);
    assert_eq!(
        (jobs[0].operation.as_str(), jobs[0].folder_id),
        ("download", folder.id)
    );
}

/// Gắn lại CÙNG đường dẫn cục bộ nhưng vào folder remote KHÁC (trùng rowid): thay đổi của remote
/// cũ không được map vào binding mới — `local_path` giống nhau nên chỉ `remote_id` phân biệt.
#[tokio::test]
async fn remote_change_of_old_remote_is_not_mapped_after_rebinding_same_path_to_another_remote() {
    let (dir, db) = temp_db();
    let old = bind_with_file(&db, dir.path(), "same-path", "local.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(old.id).unwrap();
    let new = bind_with_file(&db, dir.path(), "same-path", "local.txt", 616);
    assert_eq!(
        (new.id, new.local_path.as_str()),
        (old.id, old.local_path.as_str())
    );
    let outcome = plan_remote_change(&db, &snapshot[0], &remote_change(900, "report.pdf"))
        .await
        .unwrap();
    assert_eq!(outcome, RemoteOutcome::Skipped);
    assert!(db.file_by_path(new.id, "report.pdf").unwrap().is_none());
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Gắn lại y hệt (cùng đường dẫn, cùng remote, trùng rowid) sau khi dòng tệp cũ đã bị cascade
/// xóa: `file_id` cũ không còn thuộc folder nên bước xếp hàng bị bỏ qua, không lỗi FK.
#[test]
fn stale_file_id_after_identical_rebind_is_skipped() {
    use crate::storage::enqueue_download_on;
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "identical", "local.txt", 615);
    let binding = folder.binding();
    let file_id = db
        .ensure_remote_mapping_bound(&binding, "report.pdf", 900, Some(7))
        .unwrap()
        .unwrap();
    db.delete_folder(folder.id).unwrap();
    let rebound = bind_with_file(&db, dir.path(), "identical", "local.txt", 615);
    assert_eq!(rebound.binding(), binding, "identical binding after rebind");
    let queued = db.with_bound_file(&binding, file_id, |conn| {
        enqueue_download_on(
            conn,
            binding.id,
            file_id,
            "report.pdf",
            10,
            900,
            7,
            "hash",
            Some(1),
        )
    });
    assert!(
        queued.is_ok(),
        "{:?}",
        queued.err().map(|err| err.to_string())
    );
    assert_eq!(queued.unwrap(), None);
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Gắn CÙNG folder remote vào đường dẫn cục bộ KHÁC (trùng rowid): lượt quét cũ không được gán
/// tệp ở đường dẫn cũ cho binding mới — `remote_id` giống nhau nên chỉ `local_path` phân biệt.
#[test]
fn stale_scan_is_not_attributed_after_rebinding_same_remote_to_another_path() {
    let (dir, db) = temp_db();
    let old = bind_with_file(&db, dir.path(), "first-path", "a.txt", 615);
    let snapshot = db.list_folders().unwrap();
    db.delete_folder(old.id).unwrap();
    let new = bind_with_file(&db, dir.path(), "second-path", "b.txt", 615);
    assert_eq!((new.id, new.remote_id), (old.id, old.remote_id));
    let path = PathBuf::from(&snapshot[0].local_path).join("a.txt");
    let queued = enqueue_if_changed(&db, &snapshot[0], &path, "a.txt").unwrap();
    assert!(!queued);
    assert!(db.file_by_path(new.id, "a.txt").unwrap().is_none());
    assert!(db.list_jobs().unwrap().is_empty());
}

/// Tệp `report.pdf` đang xung đột trong `folder`: có ánh xạ remote 900 và bản cục bộ trên đĩa.
fn conflicted_file(db: &Db, folder: &FolderRow) -> i64 {
    let file_id = db
        .ensure_remote_mapping_bound(&folder.binding(), "report.pdf", 900, Some(7))
        .unwrap()
        .unwrap();
    db.mark_file_conflict(file_id, Some(900), Some(8), "Xung đột")
        .unwrap();
    std::fs::write(
        PathBuf::from(&folder.local_path).join("report.pdf"),
        "local edit",
    )
    .unwrap();
    file_id
}

/// A — người dùng chọn "Giữ bản server" đúng lúc thư mục bị gỡ (giữa lúc đọc và lúc ghi): lỗi
/// có kiểu `FolderNotFound`, không FK, không job download, không tạo lại folder.
#[test]
fn accept_server_version_after_unbind_does_not_enqueue_or_fail_on_foreign_key() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "conflicted", "local.txt", 615);
    let file_id = conflicted_file(&db, &folder);
    let result = accept_server_version_in(&db, file_id, "desktop", || {
        db.delete_folder(folder.id).unwrap();
    });
    let err = result.expect_err("unbound folder must not accept");
    assert!(
        matches!(err, crate::error::AppError::FolderNotFound),
        "{err}"
    );
    assert!(db.list_jobs().unwrap().is_empty());
    assert!(
        db.list_folders().unwrap().is_empty(),
        "folder must not be recreated"
    );
}

/// B — thư mục bị gỡ rồi gắn thư mục KHÁC trùng rowid, và một tệp của folder mới tái dùng đúng
/// `file_id` cũ: không được xóa cờ hay xếp hàng download vào folder/tệp mới.
#[test]
fn accept_server_version_never_touches_a_rebound_folder_that_reused_ids() {
    let (dir, db) = temp_db();
    let old = bind_with_file(&db, dir.path(), "old-binding", "local.txt", 615);
    let file_id = conflicted_file(&db, &old);
    let reused = std::cell::Cell::new((0_i64, 0_i64));
    let result = accept_server_version_in(&db, file_id, "desktop", || {
        db.delete_folder(old.id).unwrap();
        let new = bind_with_file(&db, dir.path(), "new-binding", "local.txt", 616);
        let other = db
            .ensure_remote_mapping_bound(&new.binding(), "other.pdf", 901, Some(3))
            .unwrap()
            .unwrap();
        reused.set((new.id, other));
    });
    let (new_folder, new_file) = reused.get();
    assert_eq!(
        (new_folder, new_file),
        (old.id, file_id),
        "SQLite reused folder and file ids"
    );
    assert!(result.is_err(), "stale accept must not succeed");
    assert!(
        db.list_jobs().unwrap().is_empty(),
        "nothing queued into the new folder"
    );
    let other = db.file_by_path(new_folder, "other.pdf").unwrap().unwrap();
    assert_eq!(other.status, "pending", "new folder's file left untouched");
}

/// C — binding bình thường: giữ bản cục bộ thành bản sao xung đột, xóa cờ, xếp hàng download.
#[test]
fn accept_server_version_with_current_binding_queues_the_download() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "normal", "local.txt", 615);
    let file_id = conflicted_file(&db, &folder);
    accept_server_version_in(&db, file_id, "desktop", || {}).unwrap();
    let jobs = db.list_jobs().unwrap();
    assert_eq!(jobs.len(), 1);
    assert_eq!(
        (
            jobs[0].operation.as_str(),
            jobs[0].file_id,
            jobs[0].folder_id
        ),
        ("download", file_id, folder.id)
    );
    assert_eq!(db.file_by_id(file_id).unwrap().unwrap().status, "pending");
    let copies = std::fs::read_dir(&folder.local_path)
        .unwrap()
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.file_name().to_string_lossy().contains("(conflict - "))
        .count();
    assert_eq!(copies, 1, "local copy preserved");
}

/// D — gắn lại y hệt (cùng đường dẫn, cùng remote, trùng rowid) và `file_id` cũ bị tái dùng cho
/// một tệp KHÁC: binding khớp, tệp thuộc folder, nhưng không phải tệp đã đọc ⇒ không ghi gì.
#[test]
fn accept_server_version_ignores_a_reused_file_id_under_an_identical_binding() {
    let (dir, db) = temp_db();
    let folder = bind_with_file(&db, dir.path(), "identical", "local.txt", 615);
    let file_id = conflicted_file(&db, &folder);
    let reused = std::cell::Cell::new(0_i64);
    let result = accept_server_version_in(&db, file_id, "desktop", || {
        db.delete_folder(folder.id).unwrap();
        let rebound = bind_with_file(&db, dir.path(), "identical", "local.txt", 615);
        let other = db
            .ensure_remote_mapping_bound(&rebound.binding(), "other.pdf", 901, Some(3))
            .unwrap()
            .unwrap();
        reused.set(other);
    });
    assert_eq!(reused.get(), file_id, "SQLite reused the file id");
    assert!(result.is_err());
    assert!(db.list_jobs().unwrap().is_empty());
    let other = db.file_by_path(folder.id, "other.pdf").unwrap().unwrap();
    assert_eq!(other.status, "pending");
}
