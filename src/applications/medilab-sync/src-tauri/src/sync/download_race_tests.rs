//! Test race giữa một transfer đang chạy và thao tác gỡ/gắn lại thư mục: sau khi gỡ, job/tệp/folder
//! bị cascade xóa và SQLite tái dùng rowid cho binding mới, nên task cũ chỉ được ghi DB hoặc thay
//! tệp đích nếu danh tính nó chụp lúc bắt đầu (job + tệp + binding) vẫn còn nguyên.
//!
//! Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable

use crate::api::{ApiClient, FinalizeResponse};
use crate::storage::{Db, JobRow};
use crate::sync::download::download_temp_path;
use crate::sync::engine::{record_finalize_result, run_download_job_with, DownloadCheckpoint};
use crate::sync::test_server::MockSyncServer;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Tệp remote mà binding A tải xuống.
const REMOTE_A: i64 = 900;
/// Version chuẩn của tệp remote A.
const VERSION_A: i64 = 8;
/// Nội dung server của tệp remote A.
const SERVER_CONTENT: &str = "server content of a.txt, version 8";

/// Môi trường một test: DB tạm, thư mục gốc chứa các folder cục bộ, server giả và client.
struct Fixture {
    dir: tempfile::TempDir,
    db: Db,
    server: MockSyncServer,
    client: ApiClient,
}

/// Dựng fixture và công bố version chuẩn của tệp remote A trên server giả.
async fn fixture() -> Fixture {
    let server = MockSyncServer::start(64 * 1024).await;
    server.publish_file(REMOTE_A, VERSION_A, SERVER_CONTENT);
    let dir = tempfile::tempdir().unwrap();
    let db = Db::open(&dir.path().join("t.db")).unwrap();
    let client = ApiClient::new(&server.base, "test-key", 1).unwrap();
    Fixture {
        dir,
        db,
        server,
        client,
    }
}

/// Bind thư mục `name` (tạo trên đĩa) vào folder remote `remote_id`; trả id folder và đường dẫn.
fn bind(db: &Db, root: &Path, name: &str, remote_id: i64) -> (i64, PathBuf) {
    let local = root.join(name);
    std::fs::create_dir_all(&local).unwrap();
    let id = db
        .upsert_folder(local.to_str().unwrap(), name, Some(remote_id), true, &[])
        .unwrap();
    (id, local)
}

/// Map `relative` tới tệp remote, xếp hàng download và claim nó như dispatcher (job `running`).
fn claim_download(db: &Db, folder_id: i64, relative: &str, remote: i64, version: i64) -> JobRow {
    let file_id = db
        .ensure_remote_mapping(folder_id, relative, remote, Some(version))
        .unwrap();
    db.enqueue_download(
        folder_id,
        file_id,
        relative,
        SERVER_CONTENT.len() as i64,
        remote,
        version,
        "hash-of-queued-version",
        None,
    )
    .unwrap();
    db.claim_next_job(Some("download"), None).unwrap().unwrap()
}

/// Ghi một tệp cục bộ `relative` và xếp hàng upload rồi claim nó (job `running`).
fn claim_upload(db: &Db, folder_id: i64, local: &Path, relative: &str) -> JobRow {
    std::fs::write(local.join(relative), format!("local {relative}")).unwrap();
    let file_id = db
        .upsert_file(folder_id, relative, 10, 1, "local-hash")
        .unwrap();
    db.enqueue_upload(folder_id, file_id, relative, 10, None, None)
        .unwrap();
    db.claim_next_job(Some("upload"), None).unwrap().unwrap()
}

/// Trạng thái hiện tại của job `job_id`, `None` nếu dòng không còn.
fn job_status(db: &Db, job_id: i64) -> Option<String> {
    db.list_jobs()
        .unwrap()
        .into_iter()
        .find(|job| job.id == job_id)
        .map(|job| job.status)
}

/// Chạy download của `job` với `checkpoint` là hook chen giữa các bước.
async fn download(
    fx: &Fixture,
    job: &JobRow,
    checkpoint: impl Fn(DownloadCheckpoint),
) -> crate::sync::engine::DownloadReport {
    let owned = fx.db.owned(job);
    run_download_job_with(
        &fx.client,
        &fx.db,
        job,
        &owned,
        |_, _, _| {},
        || false,
        checkpoint,
    )
    .await
    .unwrap()
}

/// Binding mới sau khi gỡ A: folder `other` (remote 7) trùng rowid với A, tệp B trùng rowid tệp A
/// và job download B trùng rowid job A, đang `running`. Trả job B.
fn rebind_with_reused_ids(db: &Db, root: &Path, stale: &JobRow) -> JobRow {
    let (folder_b, _) = bind(db, root, "other", 7);
    let job_b = claim_download(db, folder_b, "b.txt", 901, 9);
    assert_eq!(folder_b, stale.folder_id, "folder rowid reused");
    assert_eq!(job_b.file_id, stale.file_id, "file rowid reused");
    assert_eq!(job_b.id, stale.id, "job rowid reused");
    job_b
}

/// Test A: gỡ thư mục trong lúc download đang chạy (sau khi tải xong, trước khi thay tệp đích) →
/// không ghi tệp vào thư mục đã gỡ, không ghi DB, tệp tạm bị dọn.
#[tokio::test]
async fn unbind_during_running_download_writes_nothing() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let report = download(&fx, &job, |point| {
        if point == DownloadCheckpoint::BeforeCommit {
            fx.db.delete_folder(folder_a).unwrap();
        }
    })
    .await;
    assert!(report.superseded, "task must report it lost ownership");
    assert!(
        !local_a.join("a.txt").exists(),
        "no file committed into the unbound folder"
    );
    assert!(
        !download_temp_path(&local_a.join("a.txt"), job.id).exists(),
        "temp file removed"
    );
    assert!(fx.db.file_by_id(job.file_id).unwrap().is_none());
    assert!(fx.db.list_jobs().unwrap().is_empty());
}

/// Test B: sau khi task chụp danh tính, thư mục bị gỡ rồi gắn thư mục khác trùng rowid (folder,
/// tệp, job) → task cũ không được cập nhật dòng tệp/job mới, không ghi tệp.
#[tokio::test]
async fn rowid_reuse_during_running_download_leaves_the_new_file_untouched() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let rebound = Mutex::new(None);
    let report = download(&fx, &job, |point| {
        if point == DownloadCheckpoint::TargetCaptured {
            fx.db.delete_folder(folder_a).unwrap();
            *rebound.lock().unwrap() = Some(rebind_with_reused_ids(&fx.db, fx.dir.path(), &job));
        }
    })
    .await;
    let job_b = rebound.into_inner().unwrap().unwrap();
    assert!(report.superseded);
    let file_b = fx.db.file_by_id(job_b.file_id).unwrap().unwrap();
    assert_eq!(file_b.relative_path, "b.txt");
    assert_eq!(file_b.remote_file_id, Some(901), "new row not remapped");
    assert_eq!(file_b.remote_version_id, Some(9));
    assert_eq!(file_b.last_synced_hash, None, "new row base untouched");
    assert_eq!(
        file_b.suppress_hash, None,
        "new row suppress hash untouched"
    );
    assert_ne!(file_b.status, "synced");
    assert_eq!(
        job_status(&fx.db, job_b.id).as_deref(),
        Some("running"),
        "job B still owned by its own task"
    );
    assert!(!local_a.join("a.txt").exists(), "nothing written to disk");
}

/// Test C: gỡ rồi gắn lại CÙNG đường dẫn (vào folder remote khác) ngay trước khi thay tệp đích,
/// trong đó người dùng có tệp `a.txt` riêng → tệp cục bộ của binding mới không bị ghi đè.
#[tokio::test]
async fn rebind_same_path_before_replace_keeps_the_new_binding_file() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let rebound = Mutex::new(None);
    let report = download(&fx, &job, |point| {
        if point == DownloadCheckpoint::BeforeCommit {
            fx.db.delete_folder(folder_a).unwrap();
            std::fs::write(local_a.join("a.txt"), "local edit of binding B").unwrap();
            let (folder_b, _) = bind(&fx.db, fx.dir.path(), "root", 8);
            assert_eq!(folder_b, folder_a, "folder rowid reused");
            let file_b = fx
                .db
                .ensure_remote_mapping(folder_b, "a.txt", 901, Some(9))
                .unwrap();
            assert_eq!(file_b, job.file_id, "file rowid reused");
            *rebound.lock().unwrap() = Some(file_b);
        }
    })
    .await;
    assert!(report.superseded);
    assert_eq!(
        std::fs::read_to_string(local_a.join("a.txt")).unwrap(),
        "local edit of binding B",
        "the new binding's local file must not be overwritten"
    );
    assert!(!download_temp_path(&local_a.join("a.txt"), job.id).exists());
    let file_b = fx
        .db
        .file_by_id(rebound.into_inner().unwrap().unwrap())
        .unwrap()
        .unwrap();
    assert_eq!(file_b.remote_file_id, Some(901));
    assert_eq!(file_b.last_synced_hash, None);
    assert_ne!(file_b.status, "synced");
}

/// Test C2: gắn lại CÙNG đường dẫn và CÙNG folder remote (binding trùng hoàn toàn), tệp `a.txt`
/// của binding mới vừa được quét cục bộ (chưa map remote) → vẫn không bị ghi đè vì job/tệp đã khác.
#[tokio::test]
async fn identical_rebind_before_replace_keeps_the_scanned_local_file() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let report = download(&fx, &job, |point| {
        if point == DownloadCheckpoint::BeforeCommit {
            fx.db.delete_folder(folder_a).unwrap();
            std::fs::write(local_a.join("a.txt"), "local edit of binding B").unwrap();
            let (folder_b, _) = bind(&fx.db, fx.dir.path(), "root", 7);
            assert_eq!(folder_b, folder_a, "folder rowid reused");
            let file_b = fx
                .db
                .upsert_file(folder_b, "a.txt", 23, 1, "local-b")
                .unwrap();
            assert_eq!(file_b, job.file_id, "file rowid reused");
        }
    })
    .await;
    assert!(report.superseded);
    assert_eq!(
        std::fs::read_to_string(local_a.join("a.txt")).unwrap(),
        "local edit of binding B"
    );
    let file_b = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(file_b.remote_file_id, None, "scanned row not remapped");
    assert_ne!(file_b.status, "synced");
}

/// Test E: download bình thường vẫn tải, thay tệp đích, ghi base và hoàn tất job.
#[tokio::test]
async fn normal_download_commits_file_and_base() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let report = download(&fx, &job, |_| {}).await;
    assert!(!report.superseded);
    assert_eq!(
        std::fs::read_to_string(local_a.join("a.txt")).unwrap(),
        SERVER_CONTENT
    );
    let hash = fx.server.publish_file(REMOTE_A, VERSION_A, SERVER_CONTENT);
    let file = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(file.status, "synced");
    assert_eq!(file.last_synced_hash.as_deref(), Some(hash.as_str()));
    assert_eq!(file.remote_version_id, Some(VERSION_A));
    assert_eq!(file.suppress_hash, None);
    assert_eq!(job_status(&fx.db, job.id).as_deref(), Some("completed"));
    assert!(!download_temp_path(&local_a.join("a.txt"), job.id).exists());
}

/// Test E2: bản cục bộ đã trùng server → chỉ ghi base, job hoàn tất, không tải lại.
#[tokio::test]
async fn download_with_identical_local_copy_only_advances_the_base() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    std::fs::write(local_a.join("a.txt"), SERVER_CONTENT).unwrap();
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    let report = download(&fx, &job, |_| {}).await;
    assert!(!report.superseded);
    let file = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(file.status, "synced");
    assert_eq!(file.remote_version_id, Some(VERSION_A));
    assert_eq!(job_status(&fx.db, job.id).as_deref(), Some("completed"));
}

/// Test E3: bản cục bộ khác cả base lẫn server → đánh dấu xung đột, không ghi đè tệp cục bộ.
#[tokio::test]
async fn download_over_a_diverged_local_copy_marks_conflict() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_download(&fx.db, folder_a, "a.txt", REMOTE_A, VERSION_A);
    fx.db
        .apply_remote_base(job.file_id, REMOTE_A, 7, "older-base", 5)
        .unwrap();
    std::fs::write(local_a.join("a.txt"), "local edit").unwrap();
    let report = download(&fx, &job, |_| {}).await;
    assert!(!report.superseded);
    assert_eq!(
        std::fs::read_to_string(local_a.join("a.txt")).unwrap(),
        "local edit"
    );
    assert_eq!(
        fx.db.file_by_id(job.file_id).unwrap().unwrap().status,
        "conflict"
    );
    assert_eq!(job_status(&fx.db, job.id).as_deref(), Some("conflict"));
}

/// Response finalize `conflict` cho tệp remote 900.
fn conflict_response() -> FinalizeResponse {
    FinalizeResponse {
        status: "conflict".into(),
        file_id: REMOTE_A,
        version_id: Some(3),
        version_number: Some(3),
        conflict_id: Some(1),
        server_version_id: Some(4),
    }
}

/// Test D: finalize `conflict` tới sau khi thư mục bị gỡ rồi gắn lại với job/tệp trùng rowid (job
/// mới cũng đang `running`) → không đánh dấu xung đột tệp/job mới.
#[tokio::test]
async fn finalize_conflict_after_rowid_reuse_does_not_mark_the_new_file() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt");
    let owned_a = fx.db.owned(&job_a);
    fx.db.delete_folder(folder_a).unwrap();
    let (folder_b, local_b) = bind(&fx.db, fx.dir.path(), "other", 7);
    let job_b = claim_upload(&fx.db, folder_b, &local_b, "b.txt");
    assert_eq!(
        (job_b.id, job_b.file_id, job_b.folder_id),
        (job_a.id, job_a.file_id, job_a.folder_id),
        "job, file and folder rowids reused"
    );
    record_finalize_result(&fx.db, &job_a, &owned_a, &conflict_response()).unwrap();
    let file_b = fx.db.file_by_id(job_b.file_id).unwrap().unwrap();
    assert_eq!(file_b.relative_path, "b.txt");
    assert_ne!(file_b.status, "conflict", "new file not marked conflict");
    assert_eq!(file_b.remote_file_id, None, "new file not remapped");
    assert_eq!(job_status(&fx.db, job_b.id).as_deref(), Some("running"));
}

/// Test D2: finalize `conflict` tới sau khi thư mục bị gỡ (không gắn lại) → không lỗi, không ghi.
#[tokio::test]
async fn finalize_conflict_after_unbind_is_a_no_op() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt");
    let owned_a = fx.db.owned(&job_a);
    fx.db.delete_folder(folder_a).unwrap();
    record_finalize_result(&fx.db, &job_a, &owned_a, &conflict_response()).unwrap();
    assert!(fx.db.file_by_id(job_a.file_id).unwrap().is_none());
    assert!(fx.db.list_jobs().unwrap().is_empty());
}

/// Test F: finalize `conflict` bình thường → job và tệp cùng thành `conflict`, tệp map về tệp
/// remote và version server.
#[tokio::test]
async fn finalize_conflict_marks_job_and_file() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_upload(&fx.db, folder_a, &local_a, "a.txt");
    let owned = fx.db.owned(&job);
    record_finalize_result(&fx.db, &job, &owned, &conflict_response()).unwrap();
    let file = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(file.status, "conflict");
    assert_eq!(file.remote_file_id, Some(REMOTE_A));
    assert_eq!(file.remote_version_id, Some(4), "server version recorded");
    let row = fx
        .db
        .list_jobs()
        .unwrap()
        .into_iter()
        .find(|row| row.id == job.id)
        .unwrap();
    assert_eq!(row.status, "conflict");
    assert_eq!(row.last_error.as_deref(), Some("Phát hiện xung đột"));
    assert_eq!(row.remote_file_id, Some(REMOTE_A));
}

/// Test F2: job đã rời `running` (vd. Pause đưa về `pending`) trước khi finalize `conflict` được
/// ghi → không ghi job, không đánh dấu tệp.
#[tokio::test]
async fn finalize_conflict_for_a_job_no_longer_running_writes_nothing() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job = claim_upload(&fx.db, folder_a, &local_a, "a.txt");
    let owned = fx.db.owned(&job);
    assert!(fx
        .db
        .transition_running_job(job.id, "pending", None, 0, None, None, None)
        .unwrap());
    record_finalize_result(&fx.db, &job, &owned, &conflict_response()).unwrap();
    assert_ne!(
        fx.db.file_by_id(job.file_id).unwrap().unwrap().status,
        "conflict"
    );
    assert_eq!(job_status(&fx.db, job.id).as_deref(), Some("pending"));
}
