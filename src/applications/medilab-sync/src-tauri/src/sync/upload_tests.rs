//! Test integrity và pause/resume của `run_upload_job` trên server giả lập (không cần Odoo/MinIO).
//!
//! Luật integrity: applications/laboratory-file-sync-application/docs/contract.md#direct-minio-upload

use crate::api::ApiClient;
use crate::error::AppError;
use crate::storage::{Db, JobRow};
use crate::sync::dispatcher::settle_stopped_job;
use crate::sync::engine::{
    run_upload_job, should_skip_enqueue, UploadOutcome, ACCESS_PAUSED_MESSAGE, LEGACY_PART_SIZE,
};
use crate::sync::hash::{sha256_file, unix_mtime};
use crate::sync::test_server::MockSyncServer;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

/// Kích thước part nhỏ cho các test không cần resume, để test chạy nhanh.
const SMALL_PART: i64 = 64 * 1024;

/// Môi trường một test: DB tạm, folder cục bộ đã bind, server giả và client trỏ tới nó.
struct Fixture {
    _dir: tempfile::TempDir,
    db_path: PathBuf,
    db: Db,
    local: PathBuf,
    folder_id: i64,
    server: MockSyncServer,
    client: ApiClient,
}

/// Dựng fixture với server giả dùng `part_size`.
async fn fixture(part_size: i64) -> Fixture {
    let server = MockSyncServer::start(part_size).await;
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("t.db");
    let db = Db::open(&db_path).unwrap();
    let local = dir.path().join("root");
    std::fs::create_dir_all(&local).unwrap();
    let folder_id = db
        .upsert_folder(local.to_str().unwrap(), "R", Some(7), true, &[])
        .unwrap();
    let client = ApiClient::new(&server.base, "test-key", 1).unwrap();
    Fixture {
        _dir: dir,
        db_path,
        db,
        local,
        folder_id,
        server,
        client,
    }
}

/// Nội dung tất định dài `len` byte, khác nhau theo `seed`.
///
/// Xorshift64 tất định, KHÔNG tuần hoàn: nếu byte lặp theo chu kỳ chia hết part size thì mọi part
/// giống hệt nhau và test thứ tự hash/ETag không phát hiện được hash sai thứ tự.
fn content(len: usize, seed: u8) -> Vec<u8> {
    let mut state: u64 = 0x9E37_79B9_7F4A_7C15 ^ (u64::from(seed) << 8 | u64::from(seed));
    (0..len)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 24) as u8
        })
        .collect()
}

/// Ghi `bytes` vào tệp nhưng giữ nguyên mtime cũ — giả lập ứng dụng bảo toàn timestamp.
fn overwrite_keeping_mtime(path: &Path, bytes: &[u8]) {
    let modified = std::fs::metadata(path).unwrap().modified().unwrap();
    std::fs::write(path, bytes).unwrap();
    let file = std::fs::OpenOptions::new().write(true).open(path).unwrap();
    file.set_modified(modified).unwrap();
}

/// SHA-256 hex của một buffer.
fn sha(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(bytes))
}

impl Fixture {
    /// Ghi tệp rồi xếp hàng upload giống watcher (`enqueue_if_changed`): hash, lưu dấu vân tay,
    /// tạo job, và claim job như worker.
    fn write_and_enqueue(&self, relative: &str, bytes: &[u8]) -> JobRow {
        let path = self.local.join(relative);
        std::fs::write(&path, bytes).unwrap();
        let digest = sha256_file(&path).unwrap();
        let file_id = self
            .db
            .upsert_file(
                self.folder_id,
                relative,
                bytes.len() as i64,
                unix_mtime(&path),
                &digest,
            )
            .unwrap();
        self.db
            .enqueue_upload(
                self.folder_id,
                file_id,
                relative,
                bytes.len() as i64,
                None,
                None,
            )
            .unwrap();
        self.db.next_job().unwrap().unwrap()
    }

    /// Đưa job về `pending` (như `retry_wait` đã tới hạn) rồi claim lại.
    fn requeue(&self, job: &JobRow) -> JobRow {
        self.db
            .mark_job(job.id, "pending", None, job.attempt_count, None, None, None)
            .unwrap();
        self.db.next_job().unwrap().unwrap()
    }

    /// Đọc lại dòng job hiện tại trong DB.
    fn job(&self, job_id: i64) -> JobRow {
        self.db
            .list_jobs()
            .unwrap()
            .into_iter()
            .find(|job| job.id == job_id)
            .unwrap()
    }

    /// Chạy upload không pause, không hook.
    async fn upload(&self, job: &JobRow) -> crate::error::AppResult<super::engine::UploadReport> {
        run_upload_job(&self.client, &self.db, job, |_, _| {}, || false, |_| {}).await
    }
}

/// A — tệp không đổi: object đã finalize có SHA-256 thật bằng expected hash và bằng tệp.
#[tokio::test]
async fn unchanged_file_finalizes_exact_bytes() {
    let fx = fixture(SMALL_PART).await;
    let bytes = content(4 * SMALL_PART as usize - 100, 1);
    let job = fx.write_and_enqueue("a.bin", &bytes);
    let report = fx.upload(&job).await.unwrap();
    assert!(matches!(report.outcome, UploadOutcome::Finalized(_)));
    assert_eq!(report.parts_uploaded, 4);
    assert!(!report.local_changed_after_read);
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&bytes));
    assert_eq!(versions[0].declared_hash, sha(&bytes));
    let row = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(row.last_synced_hash.as_deref(), Some(sha(&bytes).as_str()));
    assert_eq!(row.status, "synced");
}

/// B1 — tệp đổi (metadata khác) sau enqueue, trước upload: hash lại, không dùng hash cũ.
#[tokio::test]
async fn change_before_upload_with_new_metadata_uses_new_hash() {
    let fx = fixture(SMALL_PART).await;
    let old = content(3 * SMALL_PART as usize, 1);
    let job = fx.write_and_enqueue("b.bin", &old);
    let new = content(3 * SMALL_PART as usize + 7, 2);
    std::fs::write(fx.local.join("b.bin"), &new).unwrap();
    fx.upload(&job).await.unwrap();
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].declared_hash, sha(&new));
    assert_eq!(versions[0].actual_hash, sha(&new));
}

/// B2 — tệp đổi trước upload nhưng GIỮ size + mtime: hash lúc enqueue bị dùng lại, nhưng SHA-256
/// của byte stream lộ ra khác biệt nên không finalize; lượt thử sau dùng hash mới.
#[tokio::test]
async fn change_before_upload_with_same_metadata_is_caught_by_sha() {
    let fx = fixture(SMALL_PART).await;
    let old = content(3 * SMALL_PART as usize, 1);
    let job = fx.write_and_enqueue("b2.bin", &old);
    let new = content(old.len(), 9);
    overwrite_keeping_mtime(&fx.local.join("b2.bin"), &new);
    let err = fx.upload(&job).await.unwrap_err();
    assert!(err.to_string().contains("đã thay đổi trong lúc tải lên"));
    assert!(crate::sync::retry::is_retryable(&err));
    assert!(
        fx.server.versions().is_empty(),
        "stale hash must not finalize"
    );
    let (session, parts, _) = fx.db.job_session_state(job.id).unwrap();
    assert_eq!(session, None, "session must be dropped");
    assert_eq!(parts, None);
    let fingerprint = fx.db.file_fingerprint(job.file_id).unwrap().unwrap();
    assert_eq!(fingerprint.sha256.as_deref(), Some(sha(&new).as_str()));

    let retried = fx.requeue(&job);
    fx.upload(&retried).await.unwrap();
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&new));
    assert_eq!(versions[0].declared_hash, sha(&new));
}

/// C — tệp đổi giữa các part (AAAA → BBBB sau khi part 1 đã đọc), kể cả khi giữ nguyên size +
/// mtime: object trộn A|B|B|B đã PUT nhưng KHÔNG bao giờ được finalize.
#[tokio::test]
async fn change_between_parts_never_finalizes_mixed_object() {
    let fx = fixture(SMALL_PART).await;
    let a = content(4 * SMALL_PART as usize, 1);
    let b = content(a.len(), 2);
    let job = fx.write_and_enqueue("c.bin", &a);
    let path = fx.local.join("c.bin");
    let err = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {},
        || false,
        |part| {
            if part == 1 {
                overwrite_keeping_mtime(&path, &b);
            }
        },
    )
    .await
    .unwrap_err();
    assert!(err.to_string().contains("đã thay đổi trong lúc tải lên"));
    assert_eq!(fx.server.put_count(), 4, "mixed parts were sent");
    assert!(fx.server.versions().is_empty(), "mixed object finalized");

    let retried = fx.requeue(&job);
    fx.upload(&retried).await.unwrap();
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&b));
}

/// D — tệp đổi sau khi part cuối đã đọc, trước finalize: server nhận đúng snapshot đã chứng
/// minh (A), và report báo tệp đã đổi để engine xếp hàng version kế tiếp ngay.
#[tokio::test]
async fn change_after_last_read_finalizes_snapshot_and_flags_change() {
    let fx = fixture(SMALL_PART).await;
    let a = content(2 * SMALL_PART as usize + 5, 1);
    let job = fx.write_and_enqueue("d.bin", &a);
    let path = fx.local.join("d.bin");
    let report = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {},
        || false,
        |part| {
            if part == 3 {
                std::fs::write(&path, content(a.len() + 1, 5)).unwrap();
            }
        },
    )
    .await
    .unwrap();
    assert!(report.local_changed_after_read);
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&a));
    assert_eq!(versions[0].declared_hash, sha(&a));
}

/// D2 — tệp đổi sau part cuối mà GIỮ size + mtime và không có sự kiện watcher: report không
/// thấy thay đổi, nhưng base đã lưu là hash thật của bản đã upload nên đối soát định kỳ vẫn
/// xếp hàng bản mới (trễ, không mất).
#[tokio::test]
async fn silent_change_after_last_read_is_left_to_reconciliation() {
    let fx = fixture(SMALL_PART).await;
    let a = content(2 * SMALL_PART as usize, 1);
    let b = content(a.len(), 3);
    let job = fx.write_and_enqueue("d2.bin", &a);
    let path = fx.local.join("d2.bin");
    let report = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {},
        || false,
        |part| {
            if part == 2 {
                overwrite_keeping_mtime(&path, &b);
            }
        },
    )
    .await
    .unwrap();
    assert!(!report.local_changed_after_read);
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&a));
    let row = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(row.last_synced_hash.as_deref(), Some(sha(&a).as_str()));
    assert!(!should_skip_enqueue(
        row.last_synced_hash.as_deref(),
        &sha(&b),
        Some(row.status.as_str()),
        row.suppress_hash.as_deref(),
    ));
}

/// Dedup: server đã có nội dung → không truyền byte, nhưng vẫn hash lại để chứng minh, và lưu
/// đúng hash đó làm base (trước đây base giữ hash cũ nên đối soát xếp hàng lại mãi).
#[tokio::test]
async fn dedup_is_verified_and_records_hash_as_base() {
    let fx = fixture(SMALL_PART).await;
    let bytes = content(1000, 4);
    fx.server.add_dedup_hash(&sha(&bytes));
    let job = fx.write_and_enqueue("e.bin", &bytes);
    fx.db
        .apply_remote_base(job.file_id, 1, 1, "older-base", 10)
        .unwrap();
    let report = fx.upload(&job).await.unwrap();
    assert!(matches!(report.outcome, UploadOutcome::Deduplicated));
    assert_eq!(fx.server.put_count(), 0);
    let row = fx.db.file_by_id(job.file_id).unwrap().unwrap();
    assert_eq!(row.last_synced_hash.as_deref(), Some(sha(&bytes).as_str()));
    assert_eq!(fx.job(job.id).status, "completed");
}

/// Dedup với expected hash cũ (tệp đã đổi mà giữ metadata): không được ghi nhận hoàn tất.
#[tokio::test]
async fn dedup_with_stale_expected_hash_is_rejected() {
    let fx = fixture(SMALL_PART).await;
    let old = content(1000, 4);
    fx.server.add_dedup_hash(&sha(&old));
    let job = fx.write_and_enqueue("e2.bin", &old);
    overwrite_keeping_mtime(&fx.local.join("e2.bin"), &content(1000, 6));
    let err = fx.upload(&job).await.unwrap_err();
    assert!(err.to_string().contains("đã thay đổi trong lúc tải lên"));
    assert_eq!(fx.job(job.id).status, "running");
}

/// URL presigned bị storage từ chối (hết hạn): xin URL mới cho part đó và gửi lại cùng buffer.
#[tokio::test]
async fn rejected_presigned_url_is_presigned_again() {
    let fx = fixture(SMALL_PART).await;
    let bytes = content(2 * SMALL_PART as usize, 7);
    let job = fx.write_and_enqueue("f.bin", &bytes);
    fx.server.reject_next_puts(1);
    fx.upload(&job).await.unwrap();
    assert_eq!(fx.server.put_count(), 3);
    assert_eq!(fx.server.presign_count(), 2);
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// 403 lặp lại dù đã xin URL mới: lỗi đáng thử lại (job không thành `failed` vĩnh viễn).
#[tokio::test]
async fn repeated_presigned_rejection_is_retryable() {
    let fx = fixture(SMALL_PART).await;
    let job = fx.write_and_enqueue("f2.bin", &content(100, 7));
    fx.server.reject_next_puts(2);
    let err = fx.upload(&job).await.unwrap_err();
    assert!(matches!(err, AppError::PresignedUrlRejected(403)));
    assert!(crate::sync::retry::is_retryable(&err));
}

/// Tệp nhiều part theo đúng `LEGACY_PART_SIZE` để test resume session.
fn resumable_bytes() -> Vec<u8> {
    content(2 * LEGACY_PART_SIZE as usize + 4096, 8)
}

/// Pause sau part đầu: part đang gửi hoàn tất, part kế không bắt đầu, job về `pending` không
/// tăng số lần thử; Resume dùng lại session và chỉ PUT các part còn thiếu.
#[tokio::test]
async fn pause_between_parts_keeps_session_and_resumes_remaining_parts() {
    let fx = fixture(LEGACY_PART_SIZE).await;
    let bytes = resumable_bytes();
    let job = fx.write_and_enqueue("g.bin", &bytes);
    let uploaded = AtomicUsize::new(0);
    let err = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {
            uploaded.fetch_add(1, Ordering::SeqCst);
        },
        || uploaded.load(Ordering::SeqCst) >= 1,
        |_| {},
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused));
    assert_eq!(fx.server.put_count(), 1, "next part must not start");
    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let paused = fx.job(job.id);
    assert_eq!(paused.status, "pending");
    assert_eq!(paused.attempt_count, job.attempt_count);
    assert_eq!(paused.last_error, None);
    let (session, parts, hash) = fx.db.job_session_state(job.id).unwrap();
    let session = session.expect("session kept");
    let parts: Vec<(i64, String)> = serde_json::from_str(&parts.unwrap()).unwrap();
    assert_eq!(parts.len(), 1, "etag of the finished part kept");
    assert_eq!(hash.as_deref(), Some(sha(&bytes).as_str()));

    let resumed = fx.db.next_job().unwrap().unwrap();
    assert_eq!(resumed.session_id, Some(session));
    let report = fx.upload(&resumed).await.unwrap();
    assert_eq!(report.parts_uploaded, 2);
    assert_eq!(report.total_parts, 3);
    assert_eq!(fx.server.put_count(), 3);
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&bytes));
}

/// Tắt app giữa upload (future bị hủy, job kẹt `running`): mở lại DB, `recover_jobs` đưa về
/// `pending`, session + etag đã lưu được dùng lại.
#[tokio::test]
async fn restart_mid_upload_resumes_saved_session() {
    let fx = fixture(LEGACY_PART_SIZE).await;
    let bytes = resumable_bytes();
    let job = fx.write_and_enqueue("h.bin", &bytes);
    let first_part_done = Arc::new(tokio::sync::Notify::new());
    let signal = first_part_done.clone();
    tokio::select! {
        _ = run_upload_job(&fx.client, &fx.db, &job, |_, _| signal.notify_one(), || false, |_| {}) => {
            panic!("upload finished before the simulated shutdown");
        }
        _ = first_part_done.notified() => {}
    }
    assert_eq!(fx.job(job.id).status, "running");
    let reopened = Db::open(&fx.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job.id);
    assert!(recovered.session_id.is_some());
    let puts_before = fx.server.put_count();
    let report = run_upload_job(
        &fx.client,
        &reopened,
        &recovered,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert!(report.parts_uploaded < report.total_parts);
    assert_eq!(
        fx.server.put_count() - puts_before,
        report.parts_uploaded as usize
    );
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// A1 — server quảng bá part 64 KiB: upload part 1, Pause, rồi resume CÙNG session. Resume phải
/// dùng part size đã lưu trong job (không phải hằng 16 MiB), chỉ PUT các part còn thiếu, và object
/// cuối có đúng SHA-256 của tệp.
#[tokio::test]
async fn resume_uses_the_part_size_persisted_with_the_session() {
    let fx = fixture(SMALL_PART).await;
    let bytes = content(3 * SMALL_PART as usize + 1234, 3);
    let job = fx.write_and_enqueue("small-parts.bin", &bytes);
    let uploaded = AtomicUsize::new(0);
    let err = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {
            uploaded.fetch_add(1, Ordering::SeqCst);
        },
        || uploaded.load(Ordering::SeqCst) >= 1,
        |_| {},
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused));
    assert_eq!(fx.server.put_count(), 1);
    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let (session, _, _) = fx.db.job_session_state(job.id).unwrap();
    let resumed = fx.db.next_job().unwrap().unwrap();
    assert_eq!(resumed.session_id, session, "same multipart session");
    let report = fx.upload(&resumed).await.unwrap();
    assert_eq!(report.total_parts, 4);
    assert_eq!(report.parts_uploaded, 3, "only the missing parts are PUT");
    assert_eq!(fx.server.put_count(), 4);
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].size, bytes.len());
    assert_eq!(versions[0].actual_hash, sha(&bytes));
}

/// Job lưu trước khi có cột `part_size` (NULL) vẫn resume session cũ bằng `LEGACY_PART_SIZE`.
#[tokio::test]
async fn legacy_session_without_part_size_resumes_with_legacy_size() {
    let fx = fixture(LEGACY_PART_SIZE).await;
    let bytes = content(2 * LEGACY_PART_SIZE as usize + 4096, 9);
    let job = fx.write_and_enqueue("legacy.bin", &bytes);
    let uploaded = AtomicUsize::new(0);
    let err = run_upload_job(
        &fx.client,
        &fx.db,
        &job,
        |_, _| {
            uploaded.fetch_add(1, Ordering::SeqCst);
        },
        || uploaded.load(Ordering::SeqCst) >= 1,
        |_| {},
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused));
    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    // Giả lập dòng của bản cũ: session + etag còn nhưng chưa có part_size.
    let (session, parts, hash) = fx.db.job_session_state(job.id).unwrap();
    fx.db
        .save_job_session(
            job.id,
            session.unwrap(),
            &parts.unwrap(),
            &hash.unwrap(),
            None,
        )
        .unwrap();
    let resumed = fx.db.next_job().unwrap().unwrap();
    assert_eq!(resumed.part_size, None);
    let report = fx.upload(&resumed).await.unwrap();
    assert_eq!((report.parts_uploaded, report.total_parts), (2, 3));
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// A2 — Pause khi part 2 đang PUT (server chưa trả response): upload trả `Paused` trong khoảng một
/// giây thay vì chờ part đó xong; không có ETag cho part 2; resume PUT lại part 2 và SHA khớp.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn pause_cancels_the_part_being_uploaded() {
    use std::sync::atomic::AtomicBool;
    use std::time::{Duration, Instant};
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(3 * SMALL_PART as usize, 4);
    let job = fx.write_and_enqueue("held.bin", &bytes);
    let hold = fx.server.hold_part(2);
    let paused = Arc::new(AtomicBool::new(false));
    let task = {
        let (fx, job, paused) = (fx.clone(), job.clone(), paused.clone());
        tokio::spawn(async move {
            run_upload_job(
                &fx.client,
                &fx.db,
                &job,
                |_, _| {},
                || paused.load(Ordering::SeqCst),
                |_| {},
            )
            .await
        })
    };
    hold.started.notified().await;
    let paused_at = Instant::now();
    paused.store(true, Ordering::SeqCst);
    let result = tokio::time::timeout(Duration::from_secs(3), task)
        .await
        .expect("upload must stop without waiting for the held part")
        .unwrap();
    assert!(matches!(result, Err(AppError::Paused)), "{result:?}");
    assert!(
        paused_at.elapsed() < Duration::from_secs(1),
        "{:?}",
        paused_at.elapsed()
    );
    let (_, parts, _) = fx.db.job_session_state(job.id).unwrap();
    let parts: Vec<(i64, String)> = serde_json::from_str(&parts.unwrap()).unwrap();
    assert_eq!(parts.iter().map(|(n, _)| *n).collect::<Vec<_>>(), vec![1]);

    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let resumed = fx.db.next_job().unwrap().unwrap();
    let report = fx.upload(&resumed).await.unwrap();
    assert_eq!(report.parts_uploaded, 2, "part 2 re-sent, part 3 sent");
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

// ---------------------------------------------------------------------------------------------
// Stage B — nhiều PUT part của MỘT tệp song song, dưới ngân sách bộ nhớ dùng chung.
// ---------------------------------------------------------------------------------------------

use crate::sync::engine::{run_upload_job_with, UploadOptions, UploadReport};
use crate::sync::part_budget::{PartBudget, BUDGET_UNIT_BYTES};
use crate::sync::test_server::PartHold;
use std::sync::atomic::AtomicBool;
use std::time::Duration;

/// Tùy chọn upload với cửa sổ `window` PUT và ngân sách `budget_mib` MiB.
fn window_options(window: usize, budget_mib: usize) -> UploadOptions {
    UploadOptions {
        part_concurrency: window,
        budget: PartBudget::new(budget_mib),
    }
}

/// Chạy upload trong task riêng để test điều khiển server trong lúc upload đang chạy.
fn spawn_upload(
    fx: &Arc<Fixture>,
    job: &JobRow,
    options: UploadOptions,
    paused: Arc<AtomicBool>,
) -> tokio::task::JoinHandle<crate::error::AppResult<UploadReport>> {
    let (fx, job) = (fx.clone(), job.clone());
    tokio::spawn(async move {
        run_upload_job_with(
            &fx.client,
            &fx.db,
            &job,
            &fx.db.owned(&job),
            &options,
            |_, _| {},
            || paused.load(Ordering::SeqCst),
            |_| {},
        )
        .await
    })
}

/// Chờ PUT bị giữ của một part tới server (tức đang bay); quá 3 giây là upload không PUT song song.
async fn wait_in_flight(hold: &PartHold, part: i64) {
    tokio::time::timeout(Duration::from_secs(3), hold.started.notified())
        .await
        .unwrap_or_else(|_| panic!("part {part} never became in flight"));
}

/// Chờ tới khi server đã trả xong PUT của `part` (tối đa 3 giây).
async fn wait_completed(fx: &Fixture, part: i64) {
    for _ in 0..600 {
        if fx.server.put_completions().contains(&part) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    panic!("part {part} never completed");
}

/// Etag đã lưu của job, theo part number.
fn saved_parts(fx: &Fixture, job_id: i64) -> Vec<i64> {
    let (_, parts, _) = fx.db.job_session_state(job_id).unwrap();
    let mut numbers: Vec<i64> = serde_json::from_str::<Vec<(i64, String)>>(&parts.unwrap())
        .unwrap()
        .into_iter()
        .map(|(number, _)| number)
        .collect();
    numbers.sort_unstable();
    numbers
}

/// B1 — 6 part, cửa sổ 3: đúng 3 PUT bay cùng lúc (part 4 chưa bắt đầu khi 1–3 còn bị giữ),
/// server hoàn tất lệch thứ tự (3 trước 2 trước 1) mà object finalize vẫn đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn window_of_three_keeps_three_puts_in_flight_and_accepts_out_of_order_completion() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(6 * SMALL_PART as usize - 100, 21);
    let job = fx.write_and_enqueue("window.bin", &bytes);
    let holds: Vec<PartHold> = (1..=3).map(|part| fx.server.hold_part(part)).collect();
    let task = spawn_upload(&fx, &job, window_options(3, 128), Arc::default());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 1).await;
    }
    let mut arrived = fx.server.put_arrivals();
    arrived.sort_unstable();
    assert_eq!(arrived, vec![1, 2, 3], "part 4 must wait for a free slot");
    holds[2].release.notify_one();
    wait_completed(&fx, 3).await;
    holds[1].release.notify_one();
    wait_completed(&fx, 2).await;
    holds[0].release.notify_one();
    let report = task.await.unwrap().unwrap();
    assert_eq!((report.parts_uploaded, report.total_parts), (6, 6));
    let completions = fx.server.put_completions();
    let position = |part| completions.iter().position(|done| *done == part).unwrap();
    assert!(
        position(3) < position(2) && position(2) < position(1),
        "{completions:?}"
    );
    assert_eq!(fx.server.max_puts_in_flight(), 3);
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, sha(&bytes));
    assert_eq!(versions[0].declared_hash, sha(&bytes));
}

/// B2 — tệp đổi giữa các part khi PUT song song (giữ nguyên size + mtime): hash stream theo thứ
/// tự không khớp expected hash nên KHÔNG finalize object trộn; lượt sau upload đúng nội dung mới.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_upload_never_finalizes_a_mixed_object() {
    let fx = fixture(SMALL_PART).await;
    let a = content(6 * SMALL_PART as usize, 22);
    let b = content(a.len(), 23);
    let job = fx.write_and_enqueue("mixed-window.bin", &a);
    let path = fx.local.join("mixed-window.bin");
    let err = run_upload_job_with(
        &fx.client,
        &fx.db,
        &job,
        &fx.db.owned(&job),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |part| {
            if part == 2 {
                overwrite_keeping_mtime(&path, &b);
            }
        },
    )
    .await
    .unwrap_err();
    assert!(
        err.to_string().contains("đã thay đổi trong lúc tải lên"),
        "{err}"
    );
    assert!(fx.server.versions().is_empty(), "mixed object finalized");
    let retried = fx.requeue(&job);
    run_upload_job_with(
        &fx.client,
        &fx.db,
        &retried,
        &fx.db.owned(&retried),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&b));
}

/// B3 — URL presigned của part 2 bị từ chối trong lúc part 1 và 3 đang bay: chỉ part 2 được
/// presign lại và gửi lại (một lần); part 1 và 3 không bị gửi lại.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn rejected_url_refreshes_only_the_affected_part_while_others_are_in_flight() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(3 * SMALL_PART as usize, 24);
    let job = fx.write_and_enqueue("reject-window.bin", &bytes);
    let (hold_1, hold_3) = (fx.server.hold_part(1), fx.server.hold_part(3));
    fx.server.reject_part(2);
    let task = spawn_upload(&fx, &job, window_options(3, 128), Arc::default());
    wait_in_flight(&hold_1, 1).await;
    wait_in_flight(&hold_3, 3).await;
    wait_completed(&fx, 2).await;
    assert!(
        fx.server.presign_requests().contains(&vec![2]),
        "part 2 re-presigned alone: {:?}",
        fx.server.presign_requests()
    );
    hold_1.release.notify_one();
    hold_3.release.notify_one();
    task.await.unwrap().unwrap();
    let arrivals = fx.server.put_arrivals();
    let count = |part| arrivals.iter().filter(|arrived| **arrived == part).count();
    assert_eq!((count(1), count(2), count(3)), (1, 2, 1), "{arrivals:?}");
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// B4 — Pause khi part 2, 3, 4 đang bay (part 1 đã xong): không part mới nào được lên lịch, các
/// PUT dở bị hủy và không có ETag, ETag của part 1 đã lưu; resume chỉ gửi part còn thiếu.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn pause_with_several_puts_in_flight_keeps_only_completed_etags() {
    use std::time::Instant;
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(6 * SMALL_PART as usize, 25);
    let job = fx.write_and_enqueue("pause-window.bin", &bytes);
    let holds: Vec<PartHold> = (2..=4).map(|part| fx.server.hold_part(part)).collect();
    let paused = Arc::new(AtomicBool::new(false));
    let task = spawn_upload(&fx, &job, window_options(3, 128), paused.clone());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 2).await;
    }
    wait_completed(&fx, 1).await;
    let paused_at = Instant::now();
    paused.store(true, Ordering::SeqCst);
    let result = tokio::time::timeout(Duration::from_secs(3), task)
        .await
        .expect("pause must interrupt the in-flight PUTs")
        .unwrap();
    assert!(matches!(result, Err(AppError::Paused)), "{result:?}");
    assert!(paused_at.elapsed() < Duration::from_secs(1));
    assert_eq!(
        saved_parts(&fx, job.id),
        vec![1],
        "only the finished part has an ETag"
    );
    assert!(
        !fx.server.put_arrivals().contains(&5),
        "no new part scheduled after pause"
    );

    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let resumed = fx.db.next_job().unwrap().unwrap();
    let report = run_upload_job_with(
        &fx.client,
        &fx.db,
        &resumed,
        &fx.db.owned(&resumed),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(report.parts_uploaded, 5, "parts 2..=6 only");
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// B5 — tắt app khi part 2, 3, 4 đang bay (task bị hủy, job kẹt `running`): mở lại DB,
/// `recover_jobs`, resume cùng session; part 1 đã xong không bị gửi lại.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn restart_during_a_window_resumes_without_resending_completed_parts() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(6 * SMALL_PART as usize, 26);
    let job = fx.write_and_enqueue("restart-window.bin", &bytes);
    let holds: Vec<PartHold> = (2..=4).map(|part| fx.server.hold_part(part)).collect();
    let task = spawn_upload(&fx, &job, window_options(3, 128), Arc::default());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 2).await;
    }
    wait_completed(&fx, 1).await;
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert_eq!(fx.job(job.id).status, "running");
    assert_eq!(saved_parts(&fx, job.id), vec![1]);
    let reopened = Db::open(&fx.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job.id);
    let report = run_upload_job_with(
        &fx.client,
        &reopened,
        &recovered,
        &reopened.owned(&recovered),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(report.parts_uploaded, 5);
    let arrivals = fx.server.put_arrivals();
    assert_eq!(
        arrivals.iter().filter(|part| **part == 1).count(),
        1,
        "{arrivals:?}"
    );
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// B6 — 3 tệp upload cùng lúc, mỗi tệp cửa sổ 3 (muốn tới 9 buffer), chung ngân sách 4 MiB với
/// part 1 MiB: đúng 4 buffer được giữ khi 4 PUT bị giữ, PUT thứ 5 không bắt đầu; không bao giờ
/// vượt 4 MiB; cả 3 tệp hoàn tất đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
async fn global_budget_bounds_buffers_across_concurrent_files() {
    let part = BUDGET_UNIT_BYTES as i64;
    let fx = Arc::new(fixture(part).await);
    let files: Vec<(JobRow, Vec<u8>)> = (0..3)
        .map(|index| {
            let bytes = content(6 * part as usize, 30 + index as u8);
            (
                fx.write_and_enqueue(&format!("budget-{index}.bin"), &bytes),
                bytes,
            )
        })
        .collect();
    let budget = PartBudget::new(4);
    let holds: Vec<PartHold> = (1..=4).map(|number| fx.server.hold_part(number)).collect();
    let tasks: Vec<_> = files
        .iter()
        .map(|(job, _)| {
            let options = UploadOptions {
                part_concurrency: 3,
                budget: budget.clone(),
            };
            spawn_upload(&fx, job, options, Arc::default())
        })
        .collect();
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 1).await;
    }
    // Bốn PUT bị giữ nắm toàn bộ ngân sách: không buffer thứ năm nào được đọc/PUT.
    tokio::time::sleep(Duration::from_millis(200)).await;
    assert_eq!(
        budget.in_use_mib(),
        4,
        "budget saturated by the four held PUTs"
    );
    assert_eq!(budget.peak_mib(), 4);
    assert_eq!(
        fx.server.puts_in_flight(),
        4,
        "a fifth PUT needs budget first"
    );
    for hold in &holds {
        hold.release.notify_one();
    }
    for task in tasks {
        task.await.unwrap().unwrap();
    }
    assert!(budget.peak_mib() <= 4);
    assert!(fx.server.max_puts_in_flight() <= 4);
    let mut hashes: Vec<String> = fx
        .server
        .versions()
        .iter()
        .map(|version| version.actual_hash.clone())
        .collect();
    hashes.sort();
    let mut expected: Vec<String> = files.iter().map(|(_, bytes)| sha(bytes)).collect();
    expected.sort();
    assert_eq!(hashes, expected);
}

/// B7 — server cấp part lớn hơn toàn bộ ngân sách: lỗi rõ ràng ngay, không chờ semaphore mãi.
#[tokio::test]
async fn part_larger_than_the_whole_budget_fails_fast() {
    let part = 8 * BUDGET_UNIT_BYTES as i64;
    let fx = fixture(part).await;
    let job = fx.write_and_enqueue("huge-part.bin", &content(9 * BUDGET_UNIT_BYTES, 27));
    let result = tokio::time::timeout(
        Duration::from_secs(2),
        run_upload_job_with(
            &fx.client,
            &fx.db,
            &job,
            &fx.db.owned(&job),
            &window_options(3, 4),
            |_, _| {},
            || false,
            |_| {},
        ),
    )
    .await
    .expect("must fail fast, not wait for budget");
    let err = result.unwrap_err();
    assert!(err.to_string().contains("vượt ngân sách bộ nhớ"), "{err}");
    assert!(!crate::sync::retry::is_connectivity_error(&err));
    assert_eq!(fx.server.put_count(), 0);
}

// ---------------------------------------------------------------------------------------------
// Điều tra native: thứ tự hash / ETag / finalize khi part hoàn tất lệch thứ tự, crash, Pause, RAM.
// ---------------------------------------------------------------------------------------------

/// Hash theo THỨ TỰ PART dù part hoàn tất lệch thứ tự: part 1 chậm 300 ms, part 2 10 ms, part 3
/// 100 ms ⇒ server hoàn tất 2 → 3 → 1, nhưng object finalize phải có SHA-256(part1‖part2‖part3).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn hash_follows_part_order_not_completion_order() {
    let fx = fixture(SMALL_PART).await;
    let bytes = content(3 * SMALL_PART as usize, 41);
    let job = fx.write_and_enqueue("ordered-hash.bin", &bytes);
    fx.server.delay_part(1, 300);
    fx.server.delay_part(2, 10);
    fx.server.delay_part(3, 100);
    run_upload_job_with(
        &fx.client,
        &fx.db,
        &job,
        &fx.db.owned(&job),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(fx.server.put_completions(), vec![2, 3, 1]);
    let part = SMALL_PART as usize;
    let (part_1, part_2, part_3) = (&bytes[..part], &bytes[part..2 * part], &bytes[2 * part..]);
    assert!(
        sha(part_1) != sha(part_2) && sha(part_2) != sha(part_3) && sha(part_1) != sha(part_3),
        "parts must differ, otherwise hash order is unobservable"
    );
    let concatenated = [part_1, part_2, part_3].concat();
    let versions = fx.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].declared_hash, sha(&concatenated));
    assert_eq!(versions[0].actual_hash, sha(&concatenated));
}

/// ETag gắn đúng `part → etag` dù hoàn tất theo thứ tự 3 → 1 → 2, session lưu đủ cả ba (không
/// mất cập nhật), và finalize gửi part theo thứ tự tăng dần 1, 2, 3.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn etags_map_by_part_and_finalize_is_sent_in_part_order() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(3 * SMALL_PART as usize, 42);
    let job = fx.write_and_enqueue("etag-order.bin", &bytes);
    let holds: Vec<PartHold> = (1..=3).map(|part| fx.server.hold_part(part)).collect();
    let task = spawn_upload(&fx, &job, window_options(3, 128), Arc::default());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 1).await;
    }
    for part in [3, 1, 2] {
        holds[part as usize - 1].release.notify_one();
        wait_completed(&fx, part).await;
    }
    task.await.unwrap().unwrap();
    assert_eq!(fx.server.put_completions(), vec![3, 1, 2]);
    let (session, parts, _) = fx.db.job_session_state(job.id).unwrap();
    let session = session.unwrap();
    let saved: Vec<(i64, String)> = serde_json::from_str(&parts.unwrap()).unwrap();
    let expected: Vec<(i64, String)> = (1..=3)
        .map(|part| (part, format!("etag-{session}-{part}")))
        .collect();
    assert_eq!(saved, expected, "every part keeps its own ETag");
    assert_eq!(fx.server.finalize_requests(), vec![expected]);
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// Crash khi part 1 và 3 đã xong còn part 2 (và 4, 5) đang chạy: chỉ 1 và 3 được lưu; mở lại
/// DB, `recover_jobs`, resume CÙNG session; 1 và 3 không bị PUT lại; object đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn crash_with_parts_one_and_three_done_resumes_only_missing_parts() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(6 * SMALL_PART as usize, 43);
    let job = fx.write_and_enqueue("crash-window.bin", &bytes);
    let holds: Vec<(i64, PartHold)> = [2, 4, 5]
        .into_iter()
        .map(|part| (part, fx.server.hold_part(part)))
        .collect();
    let task = spawn_upload(&fx, &job, window_options(3, 128), Arc::default());
    for (part, hold) in &holds {
        wait_in_flight(hold, *part).await;
    }
    wait_completed(&fx, 1).await;
    wait_completed(&fx, 3).await;
    // Chờ task sở hữu job ghi ETag của part 3 (ghi sau khi server trả response).
    for _ in 0..400 {
        if saved_parts(&fx, job.id) == vec![1, 3] {
            break;
        }
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert_eq!(
        saved_parts(&fx, job.id),
        vec![1, 3],
        "only really completed parts"
    );
    let (session_before, _, _) = fx.db.job_session_state(job.id).unwrap();
    let reopened = Db::open(&fx.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.session_id, session_before, "same upload session");
    let report = run_upload_job_with(
        &fx.client,
        &reopened,
        &recovered,
        &reopened.owned(&recovered),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(report.parts_uploaded, 4, "parts 2, 4, 5, 6");
    let arrivals = fx.server.put_arrivals();
    let count = |part| arrivals.iter().filter(|arrived| **arrived == part).count();
    assert_eq!((count(1), count(3)), (1, 1), "{arrivals:?}");
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// Pause khi part 1, 2, 3 cùng đang chạy (cửa sổ 3). Semantics đã chốt ở Stage A: không lên lịch
/// part 4+, các PUT đang bay bị HỦY (không có ETag), job về `pending` không tăng `attempt_count`
/// và không ghi lỗi; Resume gửi lại đúng các part còn thiếu và object đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn pause_with_parts_one_to_three_active_defines_the_resume_semantics() {
    let fx = Arc::new(fixture(SMALL_PART).await);
    let bytes = content(6 * SMALL_PART as usize, 44);
    let job = fx.write_and_enqueue("pause-first-window.bin", &bytes);
    let holds: Vec<PartHold> = (1..=3).map(|part| fx.server.hold_part(part)).collect();
    let paused = Arc::new(AtomicBool::new(false));
    let task = spawn_upload(&fx, &job, window_options(3, 128), paused.clone());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 1).await;
    }
    paused.store(true, Ordering::SeqCst);
    let result = tokio::time::timeout(Duration::from_secs(3), task)
        .await
        .expect("pause stops the job")
        .unwrap();
    assert!(matches!(result, Err(AppError::Paused)), "{result:?}");
    assert!(
        !fx.server.put_arrivals().contains(&4),
        "no part 4+ after pause"
    );
    assert!(
        saved_parts(&fx, job.id).is_empty(),
        "interrupted parts have no ETag"
    );
    settle_stopped_job(&fx.db, &job, &fx.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let paused_row = fx.job(job.id);
    assert_eq!(paused_row.status, "pending");
    assert_eq!(paused_row.attempt_count, job.attempt_count);
    assert_eq!(paused_row.last_error, None);
    let resumed = fx.db.next_job().unwrap().unwrap();
    let report = run_upload_job_with(
        &fx.client,
        &fx.db,
        &resumed,
        &fx.db.owned(&resumed),
        &window_options(3, 128),
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(report.parts_uploaded, 6);
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}

/// Một tệp 8 part (1 MiB) với cửa sổ 8 nhưng ngân sách chỉ 4 MiB: đúng 4 buffer được giữ và
/// 4 PUT bay khi 4 part đầu bị giữ; part 5 không bắt đầu tới khi có ngân sách.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn budget_of_four_limits_a_window_of_eight_to_four_buffers() {
    let part = BUDGET_UNIT_BYTES as i64;
    let fx = Arc::new(fixture(part).await);
    let bytes = content(8 * part as usize, 45);
    let job = fx.write_and_enqueue("eight-parts.bin", &bytes);
    let budget = PartBudget::new(4);
    let holds: Vec<PartHold> = (1..=4).map(|number| fx.server.hold_part(number)).collect();
    let options = UploadOptions {
        part_concurrency: 8,
        budget: budget.clone(),
    };
    let task = spawn_upload(&fx, &job, options, Arc::default());
    for (index, hold) in holds.iter().enumerate() {
        wait_in_flight(hold, index as i64 + 1).await;
    }
    tokio::time::sleep(Duration::from_millis(200)).await;
    assert_eq!(budget.in_use_mib(), 4);
    assert_eq!(fx.server.puts_in_flight(), 4);
    assert!(
        !fx.server.put_arrivals().contains(&5),
        "part 5 waits for budget"
    );
    for hold in &holds {
        hold.release.notify_one();
    }
    task.await.unwrap().unwrap();
    assert!(budget.peak_mib() <= 4);
    assert_eq!(fx.server.versions()[0].actual_hash, sha(&bytes));
}
