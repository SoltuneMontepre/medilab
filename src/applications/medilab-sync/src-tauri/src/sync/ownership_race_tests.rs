//! Test quyền sở hữu job đang chạy qua các lần await: gỡ thư mục cascade xóa job/tệp/folder và SQLite
//! tái dùng rowid khi gắn lại, nên task cũ (upload/download) chỉ được chốt lỗi, tạm dừng, lưu
//! session/tiến độ, ghi dấu vân tay hay hoàn tất nếu danh tính `RunningJob` nó chụp lúc bắt đầu vẫn
//! còn nguyên. Job/tệp của binding mới trùng rowid phải giữ nguyên.
//!
//! Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable

use crate::api::ApiClient;
use crate::error::AppError;
use crate::storage::{Db, JobRow, RunningJob};
use crate::sync::dispatcher::{settle_stopped_job, StoppedAs};
use crate::sync::engine::{
    record_job_failure, refresh_file_fingerprint, run_upload_job, run_upload_job_with,
    UploadOptions, ACCESS_PAUSED_MESSAGE,
};
use crate::sync::hash::{sha256_file, unix_mtime};
use crate::sync::test_server::MockSyncServer;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

/// Kích thước part nhỏ để tệp vài part upload nhanh.
const PART: i64 = 64 * 1024;

/// Môi trường một test: DB tạm, thư mục gốc chứa các folder cục bộ, server giả và client.
struct Fixture {
    dir: tempfile::TempDir,
    db: Db,
    server: MockSyncServer,
    client: ApiClient,
}

/// Dựng fixture với server giả dùng part `PART`.
async fn fixture() -> Fixture {
    let server = MockSyncServer::start(PART).await;
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

/// Nội dung tất định dài `len` byte, khác nhau theo `seed`.
fn content(len: usize, seed: u8) -> Vec<u8> {
    (0..len)
        .map(|index| (index as u8).wrapping_mul(31).wrapping_add(seed))
        .collect()
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

/// Ghi tệp `relative` với `bytes`, lưu dấu vân tay đúng của nó, xếp hàng upload và claim job như
/// dispatcher (job `running`).
fn claim_upload(db: &Db, folder_id: i64, local: &Path, relative: &str, bytes: &[u8]) -> JobRow {
    let path = local.join(relative);
    std::fs::write(&path, bytes).unwrap();
    let file_id = db
        .upsert_file(
            folder_id,
            relative,
            bytes.len() as i64,
            unix_mtime(&path),
            &sha256_file(&path).unwrap(),
        )
        .unwrap();
    db.enqueue_upload(folder_id, file_id, relative, bytes.len() as i64, None, None)
        .unwrap();
    db.claim_next_job(Some("upload"), None).unwrap().unwrap()
}

/// Map `relative` tới tệp remote, xếp hàng download và claim nó (job `running`).
fn claim_download(db: &Db, folder_id: i64, relative: &str, remote: i64) -> JobRow {
    let file_id = db
        .ensure_remote_mapping(folder_id, relative, remote, Some(1))
        .unwrap();
    db.enqueue_download(folder_id, file_id, relative, 10, remote, 1, "h", None)
        .unwrap();
    db.claim_next_job(Some("download"), None).unwrap().unwrap()
}

/// Gỡ folder của `stale` rồi gắn thư mục `other` (remote 7) trùng rowid; tạo `relative` và claim
/// job cùng loại cho nó. Kiểm folder, tệp và job đều trùng rowid với `stale`; trả job mới.
fn rebind_reusing_ids(fx: &Fixture, stale: &JobRow, relative: &str) -> JobRow {
    fx.db.delete_folder(stale.folder_id).unwrap();
    let (folder_b, local_b) = bind(&fx.db, fx.dir.path(), "other", 7);
    let job_b = if stale.operation == "download" {
        claim_download(&fx.db, folder_b, relative, 901)
    } else {
        claim_upload(
            &fx.db,
            folder_b,
            &local_b,
            relative,
            b"content of binding B",
        )
    };
    assert_eq!(
        (job_b.id, job_b.file_id, job_b.folder_id),
        (stale.id, stale.file_id, stale.folder_id),
        "job, file and folder rowids reused"
    );
    job_b
}

/// Dòng job `job_id` hiện tại (panic nếu không còn).
fn job_row(db: &Db, job_id: i64) -> JobRow {
    db.list_jobs()
        .unwrap()
        .into_iter()
        .find(|job| job.id == job_id)
        .unwrap()
}

/// Job mới vẫn đúng như lúc claim: `running`, attempt 0, không lỗi, không session.
fn assert_job_untouched(db: &Db, job: &JobRow) {
    let row = job_row(db, job.id);
    assert_eq!(row.status, "running", "new job still owned by its own task");
    assert_eq!(row.attempt_count, 0, "new job attempt untouched");
    assert_eq!(row.last_error, None, "new job error untouched");
    assert_eq!(
        db.job_session_state(job.id).unwrap().0,
        None,
        "no upload session written into the new job"
    );
}

/// Tệp mới vẫn đúng như lúc tạo: chưa đồng bộ, dấu vân tay của chính nó.
fn assert_upload_file_untouched(db: &Db, job: &JobRow) {
    let file = db.file_by_id(job.file_id).unwrap().unwrap();
    assert_ne!(file.status, "synced", "new file not marked synced");
    assert_eq!(file.last_synced_hash, None, "new file base untouched");
    assert_eq!(file.remote_file_id, None, "new file not remapped");
    let fingerprint = db.file_fingerprint(job.file_id).unwrap().unwrap();
    assert_eq!(
        fingerprint.sha256.as_deref(),
        Some(sha(b"content of binding B").as_str()),
        "new file fingerprint untouched"
    );
}

/// SHA-256 hex của một buffer.
fn sha(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(bytes))
}

/// Upload lỗi (5xx) tới sau khi rowid bị tái dùng → không chốt lỗi vào job mới.
#[tokio::test]
async fn upload_failure_after_rowid_reuse_leaves_the_new_job_untouched() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", b"a");
    let owned_a = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    let recorded = record_job_failure(
        &fx.db,
        &job_a,
        &owned_a,
        &AppError::Http("500 Internal Server Error".into()),
    )
    .unwrap();
    assert!(recorded.is_none(), "stale task records nothing");
    assert_job_untouched(&fx.db, &job_b);
}

/// Upload lỗi 409 (session cũ) sau khi rowid bị tái dùng → không xóa session của job mới.
#[tokio::test]
async fn upload_409_after_rowid_reuse_keeps_the_new_job_session() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", b"a");
    let owned_a = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    fx.db
        .save_job_session(job_b.id, 42, r#"[[1,"etag-b"]]"#, "hash-b", Some(PART))
        .unwrap();
    record_job_failure(
        &fx.db,
        &job_a,
        &owned_a,
        &AppError::Http("409 Conflict".into()),
    )
    .unwrap();
    assert_eq!(
        fx.db.job_session_state(job_b.id).unwrap().0,
        Some(42),
        "new job session kept"
    );
    assert_eq!(job_row(&fx.db, job_b.id).status, "running");
}

/// Download lỗi tới sau khi rowid bị tái dùng → không chốt lỗi vào job download mới.
#[tokio::test]
async fn download_failure_after_rowid_reuse_leaves_the_new_job_untouched() {
    let fx = fixture().await;
    let (folder_a, _) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_download(&fx.db, folder_a, "a.txt", 900);
    let owned_a = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    let recorded = record_job_failure(
        &fx.db,
        &job_a,
        &owned_a,
        &AppError::Connectivity("connection reset".into()),
    )
    .unwrap();
    assert!(recorded.is_none());
    assert_job_untouched(&fx.db, &job_b);
}

/// Download dừng ở điểm an toàn (Pause/mất quyền) được chốt sau khi rowid bị tái dùng →
/// `Superseded`, job mới không bị đưa về `pending`.
#[tokio::test]
async fn stopped_download_after_rowid_reuse_is_superseded() {
    let fx = fixture().await;
    let (folder_a, _) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_download(&fx.db, folder_a, "a.txt", 900);
    let owned_a = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    let stopped = settle_stopped_job(&fx.db, &job_a, &owned_a, ACCESS_PAUSED_MESSAGE).unwrap();
    assert_eq!(stopped, StoppedAs::Superseded);
    assert_job_untouched(&fx.db, &job_b);
}

/// Pause giữa upload đúng lúc thư mục bị gỡ rồi gắn lại trùng rowid → không lưu session/ETag vào
/// job mới, và chốt tạm dừng không đưa job mới về `pending`.
#[tokio::test]
async fn paused_upload_after_rowid_reuse_writes_no_session_and_settles_nothing() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let bytes = content(3 * PART as usize, 1);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &bytes);
    let owned_a = fx.db.owned(&job_a);
    let paused = AtomicBool::new(false);
    let rebound = std::sync::Mutex::new(None);
    let result = run_upload_job_with(
        &fx.client,
        &fx.db,
        &job_a,
        &owned_a,
        &UploadOptions::sequential(),
        |_, _| {},
        || paused.load(Ordering::SeqCst),
        |part| {
            if part == 2 {
                *rebound.lock().unwrap() = Some(rebind_reusing_ids(&fx, &job_a, "b.txt"));
                paused.store(true, Ordering::SeqCst);
            }
        },
    )
    .await;
    let job_b = rebound.into_inner().unwrap().unwrap();
    assert!(result.is_err(), "upload stopped");
    assert_job_untouched(&fx.db, &job_b);
    let stopped = settle_stopped_job(&fx.db, &job_a, &owned_a, ACCESS_PAUSED_MESSAGE).unwrap();
    assert_eq!(stopped, StoppedAs::Superseded);
    assert_job_untouched(&fx.db, &job_b);
    assert_upload_file_untouched(&fx.db, &job_b);
}

/// Part vừa PUT xong sau khi rowid bị tái dùng → ETag/tiến độ không được lưu vào job mới, và upload
/// cũ không finalize version nào.
#[tokio::test]
async fn upload_progress_after_rowid_reuse_is_not_saved_and_not_finalized() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let bytes = content(2 * PART as usize, 2);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &bytes);
    let owned_a = fx.db.owned(&job_a);
    let rebound = std::sync::Mutex::new(None);
    let result = run_upload_job_with(
        &fx.client,
        &fx.db,
        &job_a,
        &owned_a,
        &UploadOptions::sequential(),
        |_, _| {},
        || false,
        |part| {
            if part == 1 {
                *rebound.lock().unwrap() = Some(rebind_reusing_ids(&fx, &job_a, "b.txt"));
            }
        },
    )
    .await;
    let job_b = rebound.into_inner().unwrap().unwrap();
    assert!(
        matches!(result, Err(AppError::Superseded)),
        "{:?}",
        result.map(|report| report.outcome)
    );
    assert_job_untouched(&fx.db, &job_b);
    assert_upload_file_untouched(&fx.db, &job_b);
    assert!(
        fx.server.finalize_requests().is_empty(),
        "nothing finalized"
    );
}

/// Gỡ thư mục (không gắn lại) giữa upload → không finalize, không còn dòng nào.
#[tokio::test]
async fn unbind_during_upload_does_not_finalize() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let bytes = content(2 * PART as usize, 3);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &bytes);
    let result = run_upload_job(
        &fx.client,
        &fx.db,
        &job_a,
        |_, _| {},
        || false,
        |part| {
            if part == 2 {
                fx.db.delete_folder(folder_a).unwrap();
            }
        },
    )
    .await;
    assert!(matches!(result, Err(AppError::Superseded)));
    assert!(
        fx.server.finalize_requests().is_empty(),
        "nothing finalized"
    );
    assert!(fx.db.list_jobs().unwrap().is_empty());
}

/// Finalize thành công tới sau khi thư mục bị gỡ rồi gắn lại trùng rowid (job mới cũng `running`)
/// → job/tệp mới không bị đánh dấu hoàn tất/`synced`.
#[tokio::test]
async fn finalize_success_after_rowid_reuse_does_not_complete_the_new_job() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &content(1000, 4));
    let hold = fx.server.hold_request("finalize");
    let upload = {
        let (client, db, job) = (fx.client.clone(), fx.db.clone(), job_a.clone());
        tokio::spawn(async move {
            run_upload_job(&client, &db, &job, |_, _| {}, || false, |_| {}).await
        })
    };
    hold.started.notified().await;
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    hold.release.notify_one();
    upload.await.unwrap().unwrap();
    assert_eq!(
        fx.server.versions().len(),
        1,
        "server committed the stale version"
    );
    assert_job_untouched(&fx.db, &job_b);
    assert_upload_file_untouched(&fx.db, &job_b);
}

/// Server trả dedup cho một upload mà trong lúc `prepare` đang bay, thư mục bị gỡ rồi gắn lại trùng
/// rowid → job/tệp mới không bị hoàn tất, dấu vân tay/hash của chúng giữ nguyên.
#[tokio::test]
async fn dedup_after_rowid_reuse_does_not_complete_the_new_job() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let bytes = content(1000, 5);
    fx.server.add_dedup_hash(&sha(&bytes));
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &bytes);
    let hold = fx.server.hold_request("prepare");
    let upload = {
        let (client, db, job) = (fx.client.clone(), fx.db.clone(), job_a.clone());
        tokio::spawn(async move {
            run_upload_job(&client, &db, &job, |_, _| {}, || false, |_| {}).await
        })
    };
    hold.started.notified().await;
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    hold.release.notify_one();
    let result = upload.await.unwrap();
    assert!(matches!(result, Err(AppError::Superseded)));
    assert_job_untouched(&fx.db, &job_b);
    assert_upload_file_untouched(&fx.db, &job_b);
}

/// Hash lại tệp xong sau khi rowid bị tái dùng → dấu vân tay không được ghi vào tệp mới.
#[tokio::test]
async fn fingerprint_after_rowid_reuse_does_not_touch_the_new_file() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", b"a");
    let owned_a: RunningJob = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "b.txt");
    let result = refresh_file_fingerprint(&fx.db, &owned_a, &local_a.join("a.txt")).await;
    assert!(matches!(result, Err(AppError::Superseded)));
    assert_upload_file_untouched(&fx.db, &job_b);
}

/// Gắn lại thư mục khác trùng rowid với CÙNG đường dẫn tương đối (job/tệp/folder/đường dẫn trùng,
/// chỉ binding khác) → upload cũ không đọc nguồn từ binding mới, không mở session, không ghi gì.
#[tokio::test]
async fn upload_source_stays_on_the_captured_binding() {
    let fx = fixture().await;
    let (folder_a, local_a) = bind(&fx.db, fx.dir.path(), "root", 7);
    let job_a = claim_upload(&fx.db, folder_a, &local_a, "a.txt", &content(1000, 6));
    let owned_a = fx.db.owned(&job_a);
    let job_b = rebind_reusing_ids(&fx, &job_a, "a.txt");
    let result = run_upload_job_with(
        &fx.client,
        &fx.db,
        &job_a,
        &owned_a,
        &UploadOptions::sequential(),
        |_, _| {},
        || false,
        |_| {},
    )
    .await;
    assert!(matches!(result, Err(AppError::Superseded)));
    assert!(fx.server.versions().is_empty(), "nothing uploaded");
    assert_eq!(fx.server.put_count(), 0, "no bytes of binding B sent");
    assert_job_untouched(&fx.db, &job_b);
    assert_upload_file_untouched(&fx.db, &job_b);
}
