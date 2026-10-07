//! Test dispatcher transfer song song: claim nguyên tử, loại trừ theo tệp, giới hạn slot, không
//! chặn đầu hàng, version mới khi đang download, compare-and-set, và Pause/restart/mất quyền với
//! upload thật trên server giả.
//!
//! Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#concurrent-transfers

use crate::api::ApiClient;
use crate::error::AppError;
use crate::storage::{Db, JobRow};
use crate::sync::dispatcher::{
    settle_stopped_job, Dispatcher, StopProbe, TransferLimits, SMALL_TRANSFER_BYTES,
};
use crate::sync::engine::{run_upload_job, ACCESS_PAUSED_MESSAGE, LEGACY_PART_SIZE};
use crate::sync::hash::{sha256_file, unix_mtime};
use crate::sync::test_server::MockSyncServer;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Barrier, Mutex};
use std::time::{Duration, Instant};

/// DB tạm với một folder đã bind.
fn temp_db() -> (tempfile::TempDir, Db, i64) {
    let dir = tempfile::tempdir().unwrap();
    let db = Db::open(&dir.path().join("t.db")).unwrap();
    let folder = db
        .upsert_folder(dir.path().to_str().unwrap(), "R", Some(7), true, &[])
        .unwrap();
    (dir, db, folder)
}

/// Tạo dòng tệp `name` rồi xếp hàng upload `bytes` byte cho nó; trả `(file_id, job_id)`.
fn queue_upload(db: &Db, folder: i64, name: &str, bytes: i64) -> (i64, i64) {
    let file = db.upsert_file(folder, name, bytes, 1, name).unwrap();
    let job = db
        .enqueue_upload(folder, file, name, bytes, None, None)
        .unwrap();
    (file, job)
}

/// Xếp hàng download `bytes` byte cho tệp `name` (tạo dòng tệp nếu chưa có).
fn queue_download(db: &Db, folder: i64, name: &str, bytes: i64, version: i64) -> (i64, i64) {
    static NEXT_REMOTE_ID: std::sync::atomic::AtomicI64 = std::sync::atomic::AtomicI64::new(100);
    let remote_file_id = NEXT_REMOTE_ID.fetch_add(1, Ordering::SeqCst);
    let file = db
        .ensure_remote_mapping(folder, name, remote_file_id, Some(version))
        .unwrap();
    let job = db
        .enqueue_download(
            folder,
            file,
            name,
            bytes,
            remote_file_id,
            version,
            "hash",
            None,
        )
        .unwrap();
    (file, job)
}

/// Đọc lại một job.
fn job(db: &Db, job_id: i64) -> JobRow {
    db.list_jobs()
        .unwrap()
        .into_iter()
        .find(|job| job.id == job_id)
        .unwrap()
}

/// Hai kết nối SQLite, tám thread cùng claim: mỗi job được giao đúng một lần.
#[test]
fn concurrent_claims_never_hand_out_the_same_job() {
    let (dir, db, folder) = temp_db();
    for index in 0..60 {
        queue_upload(&db, folder, &format!("f{index}"), 10);
    }
    let second = Db::open(&dir.path().join("t.db")).unwrap();
    let claimed = Arc::new(Mutex::new(Vec::new()));
    let threads: Vec<_> = (0..8)
        .map(|index| {
            let db = if index % 2 == 0 {
                db.clone()
            } else {
                second.clone()
            };
            let claimed = claimed.clone();
            std::thread::spawn(move || {
                while let Some(job) = db.claim_next_job(None, None).unwrap() {
                    claimed.lock().unwrap().push(job.id);
                }
            })
        })
        .collect();
    for thread in threads {
        thread.join().unwrap();
    }
    let claimed = claimed.lock().unwrap();
    let unique: HashSet<i64> = claimed.iter().copied().collect();
    assert_eq!(claimed.len(), 60);
    assert_eq!(unique.len(), 60, "a job was claimed twice");
}

/// Upload và download của CÙNG một tệp không bao giờ cùng `running`.
#[test]
fn upload_and_download_of_same_file_are_mutually_exclusive() {
    let (_dir, db, folder) = temp_db();
    let (file, upload) = queue_upload(&db, folder, "same.bin", 10);
    let download = db
        .enqueue_download(folder, file, "same.bin", 10, 100, 5, "h5", None)
        .unwrap();
    assert_eq!(
        db.claim_next_job(Some("upload"), None).unwrap().unwrap().id,
        upload
    );
    assert!(db.claim_next_job(Some("download"), None).unwrap().is_none());
    assert!(db.claim_next_job(None, None).unwrap().is_none());
    assert!(db
        .transition_running_job(upload, "completed", None, 0, None, None, None)
        .unwrap());
    assert_eq!(
        db.claim_next_job(Some("download"), None)
            .unwrap()
            .unwrap()
            .id,
        download
    );
}

/// Slot tệp nhỏ chỉ nhận job ≤ ngưỡng; FIFO giữ nguyên trong từng loại.
#[test]
fn claim_filters_by_operation_and_size_in_fifo_order() {
    let (_dir, db, folder) = temp_db();
    let (_, large) = queue_upload(&db, folder, "large", SMALL_TRANSFER_BYTES + 1);
    let (_, small) = queue_upload(&db, folder, "small", 10);
    let (_, download) = queue_download(&db, folder, "down", 10, 1);
    let first_small = db
        .claim_next_job(Some("upload"), Some(SMALL_TRANSFER_BYTES))
        .unwrap()
        .unwrap();
    assert_eq!(first_small.id, small);
    assert_eq!(
        db.claim_next_job(Some("upload"), None).unwrap().unwrap().id,
        large
    );
    assert_eq!(
        db.claim_next_job(Some("download"), None)
            .unwrap()
            .unwrap()
            .id,
        download
    );
}

/// v5 đang download → change feed báo v6 → v5 xong: job quay lại `pending` NGAY để tải v6
/// (không chờ reconcile), và base đã lưu là hash của đúng byte v5 vừa tải.
#[test]
fn new_remote_version_during_running_download_is_not_lost() {
    let (_dir, db, folder) = temp_db();
    let (file, job_id) = queue_download(&db, folder, "doc.pdf", 10, 5);
    let running = db.claim_next_job(Some("download"), None).unwrap().unwrap();
    assert_eq!(running.id, job_id);
    let remote_file_id = job(&db, job_id).remote_file_id.unwrap();
    let again = db
        .enqueue_download(
            folder,
            file,
            "doc.pdf",
            12,
            remote_file_id,
            6,
            "h6",
            Some(6),
        )
        .unwrap();
    assert_eq!(again, job_id, "one active download per file");
    assert_eq!(
        job(&db, job_id).remote_version_id,
        Some(5),
        "running target untouched"
    );
    // Lượt v5 ghi hash của đúng byte nó tải rồi hoàn tất.
    db.save_job_session(job_id, 0, "[]", "h5", None).unwrap();
    assert!(db
        .transition_running_job(
            job_id,
            "completed",
            None,
            0,
            None,
            Some(remote_file_id),
            Some(5)
        )
        .unwrap());
    let rerun = job(&db, job_id);
    assert_eq!(rerun.status, "pending", "v6 must still be queued");
    assert_eq!(rerun.attempt_count, 0);
    let row = db.file_by_id(file).unwrap().unwrap();
    assert_eq!(row.last_synced_hash.as_deref(), Some("h5"));
    assert_eq!(
        db.claim_next_job(Some("download"), None)
            .unwrap()
            .unwrap()
            .id,
        job_id
    );
}

/// Tệp đổi trong lúc đang upload: job chạy lại sau lượt hiện tại thay vì bị nuốt.
#[test]
fn local_change_during_running_upload_reruns_the_job() {
    let (_dir, db, folder) = temp_db();
    let (file, job_id) = queue_upload(&db, folder, "a.txt", 10);
    db.claim_next_job(Some("upload"), None).unwrap().unwrap();
    assert_eq!(
        db.enqueue_upload(folder, file, "a.txt", 11, None, None)
            .unwrap(),
        job_id
    );
    db.transition_running_job(job_id, "completed", None, 0, None, Some(1), Some(1))
        .unwrap();
    assert_eq!(job(&db, job_id).status, "pending");
}

/// Upload đang chạy bị chuyển sang `conflict` (remote đổi): worker cũ không được ghi đè.
#[test]
fn cancelled_running_upload_is_not_overwritten_by_worker() {
    let (_dir, db, folder) = temp_db();
    let (file, job_id) = queue_upload(&db, folder, "c.txt", 10);
    db.claim_next_job(Some("upload"), None).unwrap().unwrap();
    db.cancel_active_uploads(file).unwrap();
    assert!(!db
        .transition_running_job(job_id, "completed", None, 0, None, Some(1), Some(1))
        .unwrap());
    assert!(!db
        .transition_running_job(job_id, "retry_wait", Some("boom"), 1, Some(1), None, None)
        .unwrap());
    assert_eq!(job(&db, job_id).status, "conflict");
    assert_ne!(db.file_by_id(file).unwrap().unwrap().status, "synced");
}

/// Ghi nhận khởi động/kết thúc của các transfer giả để đo mức song song.
#[derive(Default)]
struct Tracker {
    current: AtomicUsize,
    max: AtomicUsize,
    per_file: Mutex<HashMap<i64, usize>>,
    same_file_overlap: AtomicBool,
    events: Mutex<Vec<(Instant, i64, &'static str)>>,
}

impl Tracker {
    /// Ghi nhận một transfer bắt đầu.
    fn start(&self, job: &JobRow) {
        let now = self.current.fetch_add(1, Ordering::SeqCst) + 1;
        self.max.fetch_max(now, Ordering::SeqCst);
        let mut per_file = self.per_file.lock().unwrap();
        let count = per_file.entry(job.file_id).or_default();
        *count += 1;
        if *count > 1 {
            self.same_file_overlap.store(true, Ordering::SeqCst);
        }
        self.events
            .lock()
            .unwrap()
            .push((Instant::now(), job.id, "start"));
    }

    /// Ghi nhận một transfer kết thúc.
    fn end(&self, job: &JobRow) {
        self.current.fetch_sub(1, Ordering::SeqCst);
        *self.per_file.lock().unwrap().get_mut(&job.file_id).unwrap() -= 1;
        self.events
            .lock()
            .unwrap()
            .push((Instant::now(), job.id, "end"));
    }

    /// Thời điểm một sự kiện của job.
    fn at(&self, job_id: i64, kind: &str) -> Instant {
        self.events
            .lock()
            .unwrap()
            .iter()
            .find(|(_, id, event)| *id == job_id && *event == kind)
            .map(|(at, _, _)| *at)
            .unwrap()
    }
}

/// Chạy mọi job đang chờ bằng runner giả: job lớn chạy `large`, job nhỏ chạy `small`.
async fn run_fake(
    db: &Db,
    limits: TransferLimits,
    large: Duration,
    small: Duration,
) -> Arc<Tracker> {
    let tracker = Arc::new(Tracker::default());
    let (runner_db, runner_tracker) = (db.clone(), tracker.clone());
    let mut dispatcher = Dispatcher::new(db.clone(), limits, move |job: JobRow| {
        let (db, tracker) = (runner_db.clone(), runner_tracker.clone());
        async move {
            tracker.start(&job);
            let wait = if job.bytes_total > SMALL_TRANSFER_BYTES {
                large
            } else {
                small
            };
            tokio::time::sleep(wait).await;
            tracker.end(&job);
            db.transition_running_job(job.id, "completed", None, 0, None, None, None)
                .unwrap();
        }
    });
    dispatcher.run_until_idle().await.unwrap();
    assert_eq!(dispatcher.running(), 0);
    tracker
}

/// Giới hạn slot không đơn giản.
fn limits(uploads: usize, downloads: usize) -> TransferLimits {
    TransferLimits {
        uploads,
        downloads,
        small_lane: false,
    }
}

/// 10 upload khác tệp: chạy song song đúng tới giới hạn, không vượt, và đều hoàn tất.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn dispatcher_never_exceeds_upload_limit() {
    let (_dir, db, folder) = temp_db();
    for index in 0..10 {
        queue_upload(&db, folder, &format!("f{index}"), 10);
    }
    let tracker = run_fake(&db, limits(2, 2), Duration::ZERO, Duration::from_millis(40)).await;
    assert_eq!(tracker.max.load(Ordering::SeqCst), 2);
    assert!(db
        .list_jobs()
        .unwrap()
        .iter()
        .all(|job| job.status == "completed"));
}

/// Upload + download cùng tệp qua dispatcher: không bao giờ chạy cùng lúc, cả hai hoàn tất.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn dispatcher_serializes_transfers_of_the_same_file() {
    let (_dir, db, folder) = temp_db();
    for index in 0..4 {
        let (file, _) = queue_upload(&db, folder, &format!("f{index}"), 10);
        db.enqueue_download(folder, file, &format!("f{index}"), 10, 100, 2, "h", None)
            .unwrap();
    }
    let tracker = run_fake(&db, limits(2, 2), Duration::ZERO, Duration::from_millis(30)).await;
    assert!(!tracker.same_file_overlap.load(Ordering::SeqCst));
    assert!(
        tracker.max.load(Ordering::SeqCst) >= 2,
        "different files overlap"
    );
    assert_eq!(db.list_jobs().unwrap().len(), 8);
    assert!(db
        .list_jobs()
        .unwrap()
        .iter()
        .all(|job| job.status == "completed"));
}

/// 2 upload + 2 download khác tệp: cả 4 chạy cùng lúc.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn uploads_and_downloads_run_together() {
    let (_dir, db, folder) = temp_db();
    queue_upload(&db, folder, "u1", 10);
    queue_upload(&db, folder, "u2", 10);
    queue_download(&db, folder, "d1", 10, 1);
    queue_download(&db, folder, "d2", 10, 1);
    let tracker = run_fake(&db, limits(2, 2), Duration::ZERO, Duration::from_millis(80)).await;
    assert_eq!(tracker.max.load(Ordering::SeqCst), 4);
}

/// 6 upload lớn xếp trước, rồi 1 download và 2 upload nhỏ: với giới hạn mặc định, download và
/// tệp nhỏ bắt đầu trước khi upload lớn đầu tiên xong (không còn chặn đầu hàng FIFO toàn cục).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn small_and_download_jobs_do_not_wait_behind_large_uploads() {
    let (_dir, db, folder) = temp_db();
    let large: Vec<i64> = (0..6)
        .map(|index| queue_upload(&db, folder, &format!("large{index}"), 100 << 20).1)
        .collect();
    let (_, download) = queue_download(&db, folder, "down", 10, 1);
    let (_, small_a) = queue_upload(&db, folder, "small-a", 10);
    let (_, small_b) = queue_upload(&db, folder, "small-b", 10);
    let tracker = run_fake(
        &db,
        TransferLimits::default(),
        Duration::from_millis(300),
        Duration::from_millis(20),
    )
    .await;
    let first_large_done = large.iter().map(|id| tracker.at(*id, "end")).min().unwrap();
    for id in [download, small_a, small_b] {
        assert!(tracker.at(id, "end") < first_large_done, "job {id} blocked");
    }
    // Slot tệp nhỏ không dành cho tệp lớn: tối đa 2 upload lớn cùng lúc.
    let peak_large = large
        .iter()
        .filter(|id| tracker.at(**id, "start") < first_large_done)
        .count();
    assert_eq!(peak_large, 2);
}

/// Môi trường upload thật trên server giả cho các test Pause/restart/mất quyền.
struct Uploads {
    _dir: tempfile::TempDir,
    db_path: PathBuf,
    db: Db,
    root: PathBuf,
    server: MockSyncServer,
    client: ApiClient,
}

/// Dựng môi trường với part bằng `LEGACY_PART_SIZE` để resume dùng lại session.
async fn uploads() -> Uploads {
    let server = MockSyncServer::start(LEGACY_PART_SIZE).await;
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("t.db");
    let db = Db::open(&db_path).unwrap();
    let root = dir.path().to_path_buf();
    let client = ApiClient::new(&server.base, "test-key", 1).unwrap();
    Uploads {
        _dir: dir,
        db_path,
        db,
        root,
        server,
        client,
    }
}

impl Uploads {
    /// Bind folder con `name`.
    fn folder(&self, name: &str) -> i64 {
        let path = self.root.join(name);
        std::fs::create_dir_all(&path).unwrap();
        self.db
            .upsert_folder(path.to_str().unwrap(), name, Some(7), true, &[])
            .unwrap()
    }

    /// Ghi tệp 2 part vào folder và xếp hàng upload như watcher; trả `(job_id, sha, path)`.
    fn queue(&self, folder: i64, name: &str, seed: u8) -> (i64, String, PathBuf) {
        let path = self.db.folder_path(folder).unwrap().join(name);
        // Xorshift64 tất định, không tuần hoàn, để các part khác nhau thật.
        let mut state: u64 = 0x2545_F491_4F6C_DD1D ^ u64::from(seed);
        let bytes: Vec<u8> = (0..LEGACY_PART_SIZE as usize + 4096)
            .map(|_| {
                state ^= state << 13;
                state ^= state >> 7;
                state ^= state << 17;
                (state >> 24) as u8
            })
            .collect();
        std::fs::write(&path, &bytes).unwrap();
        let digest = sha256_file(&path).unwrap();
        let file = self
            .db
            .upsert_file(folder, name, bytes.len() as i64, unix_mtime(&path), &digest)
            .unwrap();
        let job = self
            .db
            .enqueue_upload(folder, file, name, bytes.len() as i64, None, None)
            .unwrap();
        (job, digest, path)
    }
}

/// Điều khiển các transfer giả lập: mọi job của folder `gated_folder` dừng ở barrier sau khi đọc
/// part 2 (tức đã PUT xong part 1); điều phối viên đổi state rồi thả tất cả cùng lúc.
struct Gate {
    arrive: Arc<Barrier>,
    release: Arc<Barrier>,
}

impl Gate {
    /// Gate cho `jobs` transfer cộng một điều phối viên.
    fn new(jobs: usize) -> Self {
        Self {
            arrive: Arc::new(Barrier::new(jobs + 1)),
            release: Arc::new(Barrier::new(jobs + 1)),
        }
    }

    /// Chạy `action` khi mọi transfer đã tới barrier, rồi thả chúng.
    fn coordinate(&self, action: impl FnOnce() + Send + 'static) -> tokio::task::JoinHandle<()> {
        let (arrive, release) = (self.arrive.clone(), self.release.clone());
        tokio::task::spawn_blocking(move || {
            arrive.wait();
            action();
            release.wait();
        })
    }
}

/// Dispatcher chạy upload thật: dừng ở điểm an toàn theo `StopProbe`, job của `gated_folder`
/// chờ ở gate sau khi đọc part 2; `crash` làm transfer panic ở điểm an toàn (giả lập tắt app).
fn upload_dispatcher(
    env: &Uploads,
    uploads: usize,
    paused: Arc<AtomicBool>,
    crash: Arc<AtomicBool>,
    gate: Option<(&Gate, i64)>,
) -> Dispatcher<impl FnMut(JobRow) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>>>
{
    let (client, db) = (env.client.clone(), env.db.clone());
    let gate = gate.map(|(gate, folder)| (gate.arrive.clone(), gate.release.clone(), folder));
    Dispatcher::new(
        env.db.clone(),
        limits(uploads, 0),
        move |job: JobRow| -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>> {
            let (client, db, paused, crash, gate) = (
                client.clone(),
                db.clone(),
                paused.clone(),
                crash.clone(),
                gate.clone(),
            );
            Box::pin(async move {
                let probe = StopProbe::new(db.clone(), paused, job.folder_id, Duration::ZERO);
                let result = run_upload_job(
                    &client,
                    &db,
                    &job,
                    |_, _| {},
                    || {
                        if crash.load(Ordering::SeqCst) {
                            panic!("simulated app shutdown");
                        }
                        probe.should_stop()
                    },
                    |part| {
                        if let Some((arrive, release, folder)) = &gate {
                            if part == 2 && job.folder_id == *folder {
                                arrive.wait();
                                release.wait();
                            }
                        }
                    },
                )
                .await;
                match result {
                    Ok(_) => {}
                    Err(AppError::Paused) => {
                        settle_stopped_job(&db, &job, &db.owned(&job), ACCESS_PAUSED_MESSAGE)
                            .unwrap();
                    }
                    Err(err) => panic!("upload failed: {err}"),
                }
            })
        },
    )
}

/// 4 upload đang chạy → Pause: không claim thêm, cả 4 dừng sau part đang gửi, về `pending` không
/// tăng attempt/không lỗi; Resume dùng lại session và hoàn tất đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
async fn pause_stops_every_running_transfer_at_a_safe_point() {
    let env = uploads().await;
    let folder = env.folder("f");
    let files: Vec<_> = (0..5)
        .map(|index| env.queue(folder, &format!("p{index}.bin"), index))
        .collect();
    let paused = Arc::new(AtomicBool::new(false));
    let gate = Gate::new(4);
    let flag = paused.clone();
    let coordinator = gate.coordinate(move || flag.store(true, Ordering::SeqCst));
    let mut dispatcher = upload_dispatcher(
        &env,
        4,
        paused.clone(),
        Arc::default(),
        Some((&gate, folder)),
    );
    // Pause: vòng claim của app dừng; chỉ thu các transfer đang chạy.
    dispatcher.fill_slots().await.unwrap();
    while dispatcher.running() > 0 {
        dispatcher.wait(Duration::from_millis(20)).await;
    }
    coordinator.await.unwrap();
    assert_eq!(
        env.server.put_count(),
        4,
        "each running job finished only its current part"
    );
    assert!(env.server.versions().is_empty());
    for (job_id, _, _) in &files {
        let row = job(&env.db, *job_id);
        assert_eq!(row.status, "pending");
        assert_eq!(row.attempt_count, 0);
        assert_eq!(row.last_error, None);
    }
    paused.store(false, Ordering::SeqCst);
    let mut resumed = upload_dispatcher(&env, 4, paused, Arc::default(), None);
    resumed.run_until_idle().await.unwrap();
    assert_eq!(
        env.server.put_count(),
        4 + 4 + 2,
        "only missing parts uploaded"
    );
    let hashes: HashSet<String> = env
        .server
        .versions()
        .iter()
        .map(|version| {
            assert_eq!(version.actual_hash, version.declared_hash);
            version.actual_hash.clone()
        })
        .collect();
    let expected: HashSet<String> = files.iter().map(|(_, sha, _)| sha.clone()).collect();
    assert_eq!(hashes, expected);
}

/// Tắt app khi 3 transfer đang chạy (task bị hủy, job kẹt `running`): mở lại DB, `recover_jobs`
/// đưa tất cả về `pending`, rồi resume session và hoàn tất đúng SHA-256.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
async fn restart_recovers_every_running_transfer() {
    let env = uploads().await;
    let folder = env.folder("f");
    let files: Vec<_> = (0..3)
        .map(|index| env.queue(folder, &format!("r{index}.bin"), index + 10))
        .collect();
    let crash = Arc::new(AtomicBool::new(false));
    let gate = Gate::new(3);
    let flag = crash.clone();
    let coordinator = gate.coordinate(move || flag.store(true, Ordering::SeqCst));
    let mut dispatcher = upload_dispatcher(&env, 3, Arc::default(), crash, Some((&gate, folder)));
    dispatcher.run_until_idle().await.unwrap();
    coordinator.await.unwrap();
    drop(dispatcher);
    for (job_id, _, _) in &files {
        assert_eq!(job(&env.db, *job_id).status, "running");
    }
    let reopened = Db::open(&env.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    for (job_id, _, _) in &files {
        assert_eq!(job(&reopened, *job_id).status, "pending");
    }
    let restarted = Uploads {
        _dir: tempfile::tempdir().unwrap(),
        db_path: env.db_path.clone(),
        db: reopened,
        root: env.root.clone(),
        server: env.server.clone(),
        client: env.client.clone(),
    };
    let mut dispatcher = upload_dispatcher(&restarted, 3, Arc::default(), Arc::default(), None);
    dispatcher.run_until_idle().await.unwrap();
    assert_eq!(
        env.server.put_count(),
        3 + 3,
        "sessions resumed, part 1 not re-sent"
    );
    let hashes: HashSet<String> = env
        .server
        .versions()
        .iter()
        .map(|version| version.actual_hash.clone())
        .collect();
    let expected: HashSet<String> = files.iter().map(|(_, sha, _)| sha.clone()).collect();
    assert_eq!(hashes, expected);
}

/// Folder mất quyền khi 3 upload của nó đang chạy: cả 3 dừng ở điểm an toàn với thông báo mất
/// quyền, job của folder đó không được claim thêm (folder khác vẫn chạy), tệp cục bộ còn nguyên;
/// cấp lại quyền thì resume và hoàn tất.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
async fn revoked_folder_stops_running_transfers_and_blocks_new_claims() {
    let env = uploads().await;
    let revoked = env.folder("revoked");
    let other = env.folder("other");
    let files: Vec<_> = (0..4)
        .map(|index| env.queue(revoked, &format!("x{index}.bin"), index + 20))
        .collect();
    let (other_job, other_sha, _) = env.queue(other, "y.bin", 30);
    let gate = Gate::new(3);
    let db = env.db.clone();
    let coordinator =
        gate.coordinate(move || db.set_folder_access_state(revoked, "denied").unwrap());
    let mut dispatcher = upload_dispatcher(
        &env,
        3,
        Arc::default(),
        Arc::default(),
        Some((&gate, revoked)),
    );
    dispatcher.run_until_idle().await.unwrap();
    coordinator.await.unwrap();
    for (job_id, _, path) in &files {
        let row = job(&env.db, *job_id);
        assert_eq!(row.status, "pending", "job {job_id}");
        assert!(path.is_file(), "local file kept");
    }
    let stopped: Vec<_> = files
        .iter()
        .filter(|(job_id, _, _)| {
            job(&env.db, *job_id).last_error.as_deref() == Some(ACCESS_PAUSED_MESSAGE)
        })
        .collect();
    assert_eq!(
        stopped.len(),
        3,
        "the three running jobs report lost access"
    );
    assert_eq!(job(&env.db, other_job).status, "completed");
    let versions = env.server.versions();
    assert_eq!(versions.len(), 1);
    assert_eq!(versions[0].actual_hash, other_sha);

    env.db.set_folder_access_state(revoked, "ok").unwrap();
    let mut regranted = upload_dispatcher(&env, 3, Arc::default(), Arc::default(), None);
    regranted.run_until_idle().await.unwrap();
    assert_eq!(env.server.versions().len(), 5);
    for (job_id, _, _) in &files {
        assert_eq!(job(&env.db, *job_id).status, "completed");
    }
}

/// Setting concurrency ẩn được kẹp `1..=4`; giá trị hợp lệ giữ nguyên.
#[test]
fn concurrency_settings_are_clamped() {
    use crate::config::AppSettings;
    use crate::sync::dispatcher::clamp_concurrency;
    let settings = AppSettings {
        upload_concurrency: 0,
        download_concurrency: 99,
        ..AppSettings::default()
    };
    let limits = TransferLimits::from_settings(&settings);
    assert_eq!((limits.uploads, limits.downloads), (1, 4));
    assert_eq!(
        TransferLimits::from_settings(&AppSettings::default()),
        TransferLimits::default()
    );
    for (value, expected) in [
        (-5, 1),
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
        (5, 4),
        (99, 4),
    ] {
        assert_eq!(clamp_concurrency(value), expected, "{value}");
    }
}
