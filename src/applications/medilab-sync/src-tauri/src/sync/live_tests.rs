//! Live test upload/download với Odoo + MinIO thật của dev stack (`task up`). Mặc định bị bỏ
//! qua; chạy bằng:
//!
//! `MEDILAB_E2E_URL=http://localhost:8069 MEDILAB_E2E_LOGIN=… MEDILAB_E2E_PASSWORD=…
//!  cargo test --manifest-path src-tauri/Cargo.toml live_tests -- --ignored --test-threads=1`
//!
//! `live_proxy_*` phải chạy trong tiến trình riêng (`--exact`) vì nó đặt `HTTP_PROXY` cho client
//! HTTP dùng chung của cả tiến trình.
//!
//! Luật integrity: applications/laboratory-file-sync-application/docs/contract.md#direct-minio-upload

use crate::api::ApiClient;
use crate::error::AppError;
use crate::storage::{Db, JobRow};
use crate::sync::dispatcher::settle_stopped_job;
use crate::sync::download::{download_object, download_temp_path};
use crate::sync::engine::{run_download_job, run_upload_job, UploadOutcome, ACCESS_PAUSED_MESSAGE};
use crate::sync::hash::{sha256_file, unix_mtime};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};

const MIB: usize = 1024 * 1024;

/// Đọc biến môi trường bắt buộc của live test.
fn env(name: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| panic!("{name} not set"))
}

/// Môi trường live: client đã đăng nhập, folder mới trên server, DB + thư mục cục bộ đã bind.
struct Live {
    dir: tempfile::TempDir,
    db_path: PathBuf,
    db: Db,
    local: PathBuf,
    folder_id: i64,
    remote_folder_id: i64,
    client: ApiClient,
    /// API key và device id của thiết bị e2e, để tiến trình con (worker bị kill) dùng lại.
    api_key: String,
    device_id: i64,
}

/// Đăng nhập, tạo một folder mới trên server và bind nó vào thư mục tạm.
async fn live(base: &str) -> Live {
    let uid = format!("transfer-e2e-{}", uuid::Uuid::new_v4());
    let session = ApiClient::login(
        base,
        &env("MEDILAB_E2E_LOGIN"),
        &env("MEDILAB_E2E_PASSWORD"),
        "transfer-e2e",
        "linux",
        "e2e",
        &uid,
    )
    .await
    .unwrap();
    let client = ApiClient::new(base, &session.api_key, session.device_id).unwrap();
    let root = format!("e2e-{}", uuid::Uuid::new_v4());
    let remote = client.create_folder(&root, &root, &[]).await.unwrap();
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("t.db");
    let db = Db::open(&db_path).unwrap();
    let local = dir.path().join("up");
    std::fs::create_dir_all(&local).unwrap();
    let folder_id = db
        .upsert_folder(local.to_str().unwrap(), &root, Some(remote.id), true, &[])
        .unwrap();
    Live {
        dir,
        db_path,
        db,
        local,
        folder_id,
        remote_folder_id: remote.id,
        client,
        api_key: session.api_key,
        device_id: session.device_id,
    }
}

/// Nội dung ngẫu nhiên `len` byte.
fn random_bytes(len: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(len + 16);
    while out.len() < len {
        out.extend_from_slice(uuid::Uuid::new_v4().as_bytes());
    }
    out.truncate(len);
    out
}

/// SHA-256 hex của một buffer.
fn sha(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(bytes))
}

impl Live {
    /// Ghi tệp rồi xếp hàng upload giống watcher, và claim job như worker.
    fn write_and_enqueue(&self, relative: &str, bytes: &[u8]) -> JobRow {
        let path = self.local.join(relative);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, bytes).unwrap();
        let file_id = self
            .db
            .upsert_file(
                self.folder_id,
                relative,
                bytes.len() as i64,
                unix_mtime(&path),
                &sha256_file(&path).unwrap(),
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

    /// Ghi tệp và xếp hàng upload nhưng KHÔNG claim (để một tiến trình khác claim); trả id job.
    fn write_and_enqueue_pending(&self, relative: &str, bytes: &[u8]) -> i64 {
        let path = self.local.join(relative);
        std::fs::write(&path, bytes).unwrap();
        let file_id = self
            .db
            .upsert_file(
                self.folder_id,
                relative,
                bytes.len() as i64,
                unix_mtime(&path),
                &sha256_file(&path).unwrap(),
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
            .unwrap()
    }

    /// Chứng minh server lưu đúng nội dung: hash canonical trên Odoo bằng `expected`, và byte
    /// thật của object tải về từ MinIO cũng có SHA-256 đó. Trả `(remote_file_id, version_id)`.
    async fn assert_server_content(
        &self,
        relative: &str,
        expected: &str,
        size: usize,
    ) -> (i64, i64) {
        let page = self
            .client
            .folder_files(self.remote_folder_id, 50, 0)
            .await
            .unwrap();
        let item = page
            .items
            .iter()
            .find(|item| item.logical_path == relative)
            .unwrap_or_else(|| panic!("{relative} not on server"));
        let current = item.current_version.as_ref().expect("canonical version");
        assert_eq!(current.content_hash, expected, "Odoo hash");
        assert_eq!(current.size, size as i64, "Odoo size");
        let auth = self
            .client
            .authorize_download(item.id, current.id)
            .await
            .unwrap();
        let temp = self
            .dir
            .path()
            .join(format!("verify-{}", uuid::Uuid::new_v4()));
        download_object(&auth.url, &temp, current.size, || false)
            .await
            .unwrap();
        assert_eq!(
            sha256_file(&temp).unwrap(),
            expected,
            "MinIO object SHA-256"
        );
        std::fs::remove_file(temp).unwrap();
        (item.id, current.id)
    }

    /// Số version canonical hiện có của một đường dẫn trên server (0 nếu chưa có).
    async fn has_canonical_version(&self, relative: &str) -> bool {
        let page = self
            .client
            .folder_files(self.remote_folder_id, 50, 0)
            .await
            .unwrap();
        page.items
            .iter()
            .any(|item| item.logical_path == relative && item.current_version.is_some())
    }

    /// Đọc lại dòng job hiện tại.
    fn job(&self, db: &Db, job_id: i64) -> JobRow {
        db.list_jobs()
            .unwrap()
            .into_iter()
            .find(|job| job.id == job_id)
            .unwrap()
    }

    /// Bind một thư mục cục bộ thứ hai vào cùng folder server và xếp hàng download một tệp.
    fn enqueue_download(
        &self,
        relative: &str,
        remote_file_id: i64,
        version_id: i64,
        hash: &str,
        size: usize,
    ) -> (i64, PathBuf, JobRow) {
        let local = self.dir.path().join("down");
        std::fs::create_dir_all(&local).unwrap();
        let folder_id = self
            .db
            .upsert_folder(
                local.to_str().unwrap(),
                "down",
                Some(self.remote_folder_id),
                true,
                &[],
            )
            .unwrap();
        let file_id = self
            .db
            .ensure_remote_mapping(folder_id, relative, remote_file_id, Some(version_id))
            .unwrap();
        self.db
            .enqueue_download(
                folder_id,
                file_id,
                relative,
                size as i64,
                remote_file_id,
                version_id,
                hash,
                None,
            )
            .unwrap();
        (folder_id, local, self.db.next_job().unwrap().unwrap())
    }
}

/// Test A + B + C (live): upload nhỏ, upload multipart, và tệp đổi giữa các part không bao giờ
/// tạo version trộn trên Odoo/MinIO thật.
#[tokio::test]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables"]
async fn live_upload_integrity() {
    let lv = live(&env("MEDILAB_E2E_URL")).await;

    // A — tệp nhỏ: một part.
    let small = random_bytes(3000);
    let job = lv.write_and_enqueue("small.txt", &small);
    let report = run_upload_job(&lv.client, &lv.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    assert!(matches!(report.outcome, UploadOutcome::Finalized(ref f) if f.status != "conflict"));
    assert_eq!((report.parts_uploaded, report.total_parts), (1, 1));
    lv.assert_server_content("small.txt", &sha(&small), small.len())
        .await;
    println!("[A] small upload ok: 1 part, SHA server == local == MinIO object");

    // B — multipart 40 MiB: 3 part 16 MiB.
    let large = random_bytes(40 * MIB);
    let job = lv.write_and_enqueue("nested/large.bin", &large);
    let report = run_upload_job(&lv.client, &lv.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    assert_eq!((report.parts_uploaded, report.total_parts), (3, 3));
    lv.assert_server_content("nested/large.bin", &sha(&large), large.len())
        .await;
    println!("[B] multipart ok: 3/3 parts, SHA server == local == MinIO object");

    // C — AAAA → BBBB sau khi part 1 đã đọc: object trộn không được finalize.
    let a = random_bytes(40 * MIB);
    let b = random_bytes(a.len());
    let job = lv.write_and_enqueue("mixed.bin", &a);
    let path = lv.local.join("mixed.bin");
    let err = run_upload_job(
        &lv.client,
        &lv.db,
        &job,
        |_, _| {},
        || false,
        |part| {
            if part == 1 {
                let modified = std::fs::metadata(&path).unwrap().modified().unwrap();
                std::fs::write(&path, &b).unwrap();
                let file = std::fs::OpenOptions::new().write(true).open(&path).unwrap();
                file.set_modified(modified).unwrap();
            }
        },
    )
    .await
    .unwrap_err();
    assert!(err.to_string().contains("đã thay đổi trong lúc tải lên"));
    assert!(
        !lv.has_canonical_version("mixed.bin").await,
        "mixed object finalized"
    );
    println!("[C] mixed A|B|B object rejected before finalize; no canonical version on server");
    lv.db
        .mark_job(job.id, "pending", None, 1, None, None, None)
        .unwrap();
    let retried = lv.db.next_job().unwrap().unwrap();
    run_upload_job(&lv.client, &lv.db, &retried, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    lv.assert_server_content("mixed.bin", &sha(&b), b.len())
        .await;
    println!("[C] retry uploaded the new content B; SHA verified on MinIO");
}

/// Test D + F (live): Pause giữa multipart upload rồi Resume; tắt app giữa upload rồi mở lại.
#[tokio::test]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables"]
async fn live_upload_pause_and_restart() {
    let lv = live(&env("MEDILAB_E2E_URL")).await;

    // D — Pause sau part đầu.
    let bytes = random_bytes(40 * MIB);
    let job = lv.write_and_enqueue("pause.bin", &bytes);
    let uploaded = AtomicUsize::new(0);
    let err = run_upload_job(
        &lv.client,
        &lv.db,
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
    assert_eq!(
        uploaded.load(Ordering::SeqCst),
        1,
        "next part must not start"
    );
    settle_stopped_job(&lv.db, &job, &lv.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let paused = lv.job(&lv.db, job.id);
    assert_eq!(paused.status, "pending");
    assert_eq!(paused.attempt_count, job.attempt_count);
    assert_eq!(paused.last_error, None);
    let (session, parts, _) = lv.db.job_session_state(job.id).unwrap();
    let parts: Vec<(i64, String)> = serde_json::from_str(&parts.unwrap()).unwrap();
    assert_eq!(parts.len(), 1);
    println!(
        "[D] paused after part 1: status=pending attempt={} error=None etags=1",
        paused.attempt_count
    );
    let resumed = lv.db.next_job().unwrap().unwrap();
    assert_eq!(resumed.session_id, session, "multipart session reused");
    let report = run_upload_job(&lv.client, &lv.db, &resumed, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    assert_eq!((report.parts_uploaded, report.total_parts), (2, 3));
    lv.assert_server_content("pause.bin", &sha(&bytes), bytes.len())
        .await;
    println!("[D] resumed same session: 2 remaining parts uploaded, SHA verified on MinIO");

    // F — tắt app giữa upload: future bị hủy sau part đầu, job kẹt `running`.
    let bytes = random_bytes(40 * MIB);
    let job = lv.write_and_enqueue("restart.bin", &bytes);
    let first = Arc::new(tokio::sync::Notify::new());
    let signal = first.clone();
    tokio::select! {
        _ = run_upload_job(&lv.client, &lv.db, &job, |_, _| signal.notify_one(), || false, |_| {}) => {
            panic!("upload finished before the simulated shutdown");
        }
        _ = first.notified() => {}
    }
    assert_eq!(lv.job(&lv.db, job.id).status, "running");
    let reopened = Db::open(&lv.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job.id);
    assert!(recovered.session_id.is_some());
    let report = run_upload_job(
        &lv.client,
        &reopened,
        &recovered,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert!(report.parts_uploaded < report.total_parts);
    lv.assert_server_content("restart.bin", &sha(&bytes), bytes.len())
        .await;
    println!(
        "[F] restart: running->pending, session resumed, {}/{} parts uploaded after restart, SHA verified",
        report.parts_uploaded, report.total_parts
    );
}

/// Test E + G (live): Pause giữa download rồi Resume bằng Range; tắt app giữa download rồi mở lại.
#[tokio::test]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables"]
async fn live_download_pause_and_restart() {
    let lv = live(&env("MEDILAB_E2E_URL")).await;
    let bytes = random_bytes(64 * MIB);
    let job = lv.write_and_enqueue("down.bin", &bytes);
    run_upload_job(&lv.client, &lv.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    let hash = sha(&bytes);
    let (remote_file_id, version_id) = lv
        .assert_server_content("down.bin", &hash, bytes.len())
        .await;

    // E — Pause sau vài chunk.
    let (_, local, job) =
        lv.enqueue_download("down.bin", remote_file_id, version_id, &hash, bytes.len());
    let chunks = AtomicUsize::new(0);
    let err = run_download_job(
        &lv.client,
        &lv.db,
        &job,
        |_, _, _| {},
        || chunks.fetch_add(1, Ordering::SeqCst) >= 50,
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused));
    let temp = download_temp_path(&local.join("down.bin"), job.id);
    let partial = std::fs::metadata(&temp).unwrap().len();
    assert!(
        partial > 0 && partial < bytes.len() as u64,
        "partial temp kept: {partial}"
    );
    assert!(!local.join("down.bin").exists(), "destination untouched");
    settle_stopped_job(&lv.db, &job, &lv.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let paused = lv.job(&lv.db, job.id);
    assert_eq!(
        (paused.status.as_str(), paused.attempt_count),
        ("pending", job.attempt_count)
    );
    assert_eq!(paused.last_error, None);
    println!(
        "[E] paused download: temp kept with {partial} bytes, status=pending attempt unchanged"
    );
    let resumed = lv.db.next_job().unwrap().unwrap();
    let report = run_download_job(&lv.client, &lv.db, &resumed, |_, _, _| {}, || false)
        .await
        .unwrap();
    assert_eq!(
        report.resumed_from, partial as i64,
        "Range resume from temp"
    );
    assert_eq!(sha256_file(&local.join("down.bin")).unwrap(), hash);
    assert!(!temp.exists());
    println!("[E] resumed with Range from byte {partial}; final SHA-256 matches");

    // G — tắt app giữa download: future bị hủy sau vài chunk, job kẹt `running`.
    std::fs::remove_file(local.join("down.bin")).unwrap();
    lv.db
        .enqueue_download(
            resumed.folder_id,
            resumed.file_id,
            "down.bin",
            bytes.len() as i64,
            remote_file_id,
            version_id,
            &hash,
            None,
        )
        .unwrap();
    let job = lv.db.next_job().unwrap().unwrap();
    let chunks = AtomicUsize::new(0);
    let reached = Arc::new(tokio::sync::Notify::new());
    let signal = reached.clone();
    tokio::select! {
        _ = run_download_job(&lv.client, &lv.db, &job, |_, _, _| {}, || {
            if chunks.fetch_add(1, Ordering::SeqCst) == 50 { signal.notify_one(); }
            false
        }) => panic!("download finished before the simulated shutdown"),
        _ = reached.notified() => {}
    }
    // Chờ các lượt ghi đang dở của tokio::fs hoàn tất như khi tiến trình thật thoát.
    tokio::time::sleep(Duration::from_millis(300)).await;
    let temp = download_temp_path(&local.join("down.bin"), job.id);
    let partial = std::fs::metadata(&temp).unwrap().len();
    assert!(partial > 0 && partial < bytes.len() as u64);
    let reopened = Db::open(&lv.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job.id);
    let report = run_download_job(&lv.client, &reopened, &recovered, |_, _, _| {}, || false)
        .await
        .unwrap();
    assert_eq!(report.resumed_from, partial as i64);
    assert_eq!(sha256_file(&local.join("down.bin")).unwrap(), hash);
    println!(
        "[G] restart: running->pending, Range resume from byte {partial}; final SHA-256 matches"
    );
}

/// Thống kê của proxy: số kết nối TCP theo host đích và header của từng request.
#[derive(Default)]
struct ProxyStats {
    connections: HashMap<String, usize>,
    requests: Vec<ProxiedRequest>,
    /// Số body PUT đang được chuyển tiếp cùng lúc, và mức cao nhất.
    puts_in_flight: usize,
    max_puts_in_flight: usize,
}

/// Giảm bộ đếm PUT đang chuyển tiếp khi body xong hoặc kết nối bị hủy giữa chừng.
struct PutInFlight(Arc<Mutex<ProxyStats>>);

impl Drop for PutInFlight {
    /// Trả lại một chỗ trong bộ đếm PUT đang chuyển tiếp.
    fn drop(&mut self) {
        if let Ok(mut stats) = self.0.lock() {
            stats.puts_in_flight -= 1;
        }
    }
}

/// Một request đi qua proxy.
#[derive(Clone, Debug)]
struct ProxiedRequest {
    host: String,
    method: String,
    has_authorization: bool,
    has_cookie: bool,
    /// `partNumber` của PUT part presigned (query của MinIO), nếu có.
    part_number: Option<i64>,
    /// Đường dẫn của request, bỏ query (không giữ chữ ký presigned).
    path: String,
}

/// HTTP forward proxy tối giản cho test: ghi nhận kết nối/header và giới hạn tốc độ chiều
/// client → server (byte body) theo `rate` (byte/giây, 0 = không giới hạn). Chữ ký SigV4 của
/// presigned URL giữ nguyên vì request đi nguyên vẹn, kể cả header `Host`.
struct ThrottleProxy {
    addr: String,
    rate: Arc<AtomicU64>,
    stats: Arc<Mutex<ProxyStats>>,
}

impl ThrottleProxy {
    /// Mở proxy trên cổng ngẫu nhiên của loopback.
    async fn start() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = format!("http://{}", listener.local_addr().unwrap());
        let rate = Arc::new(AtomicU64::new(0));
        let stats = Arc::new(Mutex::new(ProxyStats::default()));
        let (accept_rate, accept_stats) = (rate.clone(), stats.clone());
        tokio::spawn(async move {
            while let Ok((client, _)) = listener.accept().await {
                let (rate, stats) = (accept_rate.clone(), accept_stats.clone());
                tokio::spawn(async move { proxy_connection(client, rate, stats).await });
            }
        });
        Self { addr, rate, stats }
    }
}

/// Chuyển tiếp một kết nối của client: đọc từng request (absolute-form), mở kết nối tới host
/// đích ở request đầu, chép body theo giới hạn tốc độ, và chép nguyên chiều response.
async fn proxy_connection(client: TcpStream, rate: Arc<AtomicU64>, stats: Arc<Mutex<ProxyStats>>) {
    let (client_read, client_write) = client.into_split();
    let mut client_write = Some(client_write);
    let mut reader = BufReader::new(client_read);
    let mut upstream_write: Option<tokio::net::tcp::OwnedWriteHalf> = None;
    let mut upstream_host = String::new();
    loop {
        let mut head = Vec::new();
        let mut content_length = 0usize;
        let mut request = ProxiedRequest {
            host: String::new(),
            method: String::new(),
            has_authorization: false,
            has_cookie: false,
            part_number: None,
            path: String::new(),
        };
        loop {
            let mut line = String::new();
            if reader.read_line(&mut line).await.unwrap_or(0) == 0 {
                return;
            }
            if head.is_empty() {
                let mut parts = line.split_whitespace();
                request.method = parts.next().unwrap_or_default().to_string();
                let target = parts.next().unwrap_or_default();
                request.part_number = target
                    .split(['?', '&'])
                    .find_map(|pair| pair.strip_prefix("partNumber="))
                    .and_then(|number| number.parse().ok());
                let without_scheme = target.trim_start_matches("http://");
                request.host = without_scheme
                    .split('/')
                    .next()
                    .unwrap_or_default()
                    .to_string();
                request.path = without_scheme
                    .find('/')
                    .map(|start| &without_scheme[start..])
                    .unwrap_or("/")
                    .split('?')
                    .next()
                    .unwrap_or_default()
                    .to_string();
            } else if let Some((name, value)) = line.trim_end().split_once(':') {
                let name = name.to_ascii_lowercase();
                if name == "content-length" {
                    content_length = value.trim().parse().unwrap_or(0);
                }
                request.has_authorization |= name == "authorization";
                request.has_cookie |= name == "cookie";
            }
            head.extend_from_slice(line.as_bytes());
            if line == "\r\n" {
                break;
            }
        }
        if upstream_write.is_none() {
            let upstream = TcpStream::connect(&request.host).await.unwrap();
            let (mut upstream_read, write) = upstream.into_split();
            upstream_write = Some(write);
            upstream_host = request.host.clone();
            *stats
                .lock()
                .unwrap()
                .connections
                .entry(request.host.clone())
                .or_default() += 1;
            // Chiều response chép nguyên trong task riêng, sở hữu nửa ghi của client.
            let mut response_sink = client_write.take().unwrap();
            tokio::spawn(async move {
                let _ = tokio::io::copy(&mut upstream_read, &mut response_sink).await;
                let _ = response_sink.shutdown().await;
            });
        }
        assert_eq!(
            request.host, upstream_host,
            "one destination per connection"
        );
        let is_put = request.method == "PUT";
        stats.lock().unwrap().requests.push(request);
        let _put_guard = is_put.then(|| {
            let mut locked = stats.lock().unwrap();
            locked.puts_in_flight += 1;
            locked.max_puts_in_flight = locked.max_puts_in_flight.max(locked.puts_in_flight);
            PutInFlight(stats.clone())
        });
        let upstream = upstream_write.as_mut().unwrap();
        if upstream.write_all(&head).await.is_err() {
            return;
        }
        let started = Instant::now();
        let mut sent = 0u64;
        let mut remaining = content_length;
        let mut buf = vec![0u8; 16 * 1024];
        while remaining > 0 {
            let want = remaining.min(buf.len());
            if reader.read_exact(&mut buf[..want]).await.is_err()
                || upstream.write_all(&buf[..want]).await.is_err()
            {
                return;
            }
            remaining -= want;
            sent += want as u64;
            let limit = rate.load(Ordering::SeqCst);
            if limit > 0 {
                let due = Duration::from_secs_f64(sent as f64 / limit as f64);
                if let Some(wait) = due.checked_sub(started.elapsed()) {
                    tokio::time::sleep(wait).await;
                }
            }
        }
    }
}

/// Qua proxy thật: (1) 3 client HTTP dùng chung tái sử dụng kết nối và không lộ header xác thực
/// Odoo sang MinIO; (2) một part 16 MiB mất hơn 120 giây (timeout cũ) vẫn upload thành công.
#[tokio::test]
#[ignore = "needs a running dev stack, MEDILAB_E2E_* variables, and its own process (--exact)"]
async fn live_proxy_connection_reuse_and_slow_upload() {
    let proxy = ThrottleProxy::start().await;
    // Đặt trước khi client dùng chung đầu tiên được dựng trong tiến trình này.
    for name in [
        "NO_PROXY",
        "no_proxy",
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
    ] {
        std::env::remove_var(name);
    }
    std::env::set_var("HTTP_PROXY", &proxy.addr);
    std::env::set_var("http_proxy", &proxy.addr);
    let lv = live(&env("MEDILAB_E2E_URL")).await;

    let bytes = random_bytes(40 * MIB);
    let job = lv.write_and_enqueue("reuse.bin", &bytes);
    run_upload_job(&lv.client, &lv.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    lv.assert_server_content("reuse.bin", &sha(&bytes), bytes.len())
        .await;
    let storage_host = "localhost:29000";
    {
        let stats = proxy.stats.lock().unwrap();
        let storage: Vec<&ProxiedRequest> = stats
            .requests
            .iter()
            .filter(|request| request.host == storage_host)
            .collect();
        let odoo: Vec<&ProxiedRequest> = stats
            .requests
            .iter()
            .filter(|request| request.host != storage_host)
            .collect();
        println!(
            "[reuse] connections per host: {:?}; storage requests={} odoo requests={}",
            stats.connections,
            storage.len(),
            odoo.len()
        );
        assert_eq!(storage.iter().filter(|r| r.method == "PUT").count(), 3);
        assert!(storage
            .iter()
            .all(|r| !r.has_authorization && !r.has_cookie));
        assert!(odoo.iter().all(|r| !r.has_cookie));
        let unauthenticated = odoo.iter().filter(|r| !r.has_authorization).count();
        assert_eq!(
            unauthenticated, 1,
            "only login goes to Odoo without Authorization"
        );
        // 3 PUT + 1 GET qua 2 client storage (upload, download): tái sử dụng ⇒ 2 kết nối.
        assert_eq!(stats.connections.get(storage_host), Some(&2));
    }

    // Slow upload: 96 KiB/s ⇒ một part 16 MiB mất ~170 giây, quá timeout cố định 120 giây cũ.
    proxy.rate.store(96 * 1024, Ordering::SeqCst);
    let slow = random_bytes(16 * MIB);
    let job = lv.write_and_enqueue("slow.bin", &slow);
    let started = Instant::now();
    let report = run_upload_job(&lv.client, &lv.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    let elapsed = started.elapsed();
    proxy.rate.store(0, Ordering::SeqCst);
    assert_eq!(report.total_parts, 1);
    assert!(
        elapsed > Duration::from_secs(125),
        "throttle too weak: {elapsed:?}"
    );
    lv.assert_server_content("slow.bin", &sha(&slow), slow.len())
        .await;
    println!(
        "[slow] one 16 MiB part took {elapsed:?} (> old 120 s timeout); SHA verified on MinIO"
    );
}

/// Một transfer trong timeline live: loại, giây bắt đầu/kết thúc tính từ mốc của timeline.
#[derive(Clone, Debug)]
struct Span {
    job_id: i64,
    operation: String,
    name: String,
    bytes: i64,
    start: f64,
    end: f64,
}

/// Timeline các transfer của một lượt chạy dispatcher live.
struct Timeline {
    origin: Instant,
    spans: Mutex<Vec<Span>>,
}

impl Timeline {
    /// Timeline mới, mốc thời gian là lúc tạo.
    fn new() -> Arc<Self> {
        Arc::new(Self {
            origin: Instant::now(),
            spans: Mutex::new(Vec::new()),
        })
    }

    /// Các transfer đã ghi, theo thời điểm bắt đầu.
    fn spans(&self) -> Vec<Span> {
        let mut spans = self.spans.lock().unwrap().clone();
        spans.sort_by(|a, b| a.start.total_cmp(&b.start));
        spans
    }

    /// In timeline START/DONE để nhìn thấy overlap.
    fn print(&self, label: &str) {
        for span in self.spans() {
            println!(
                "[{label}] job {:>3} {:<8} {:<16} {:>9} B  START {:>7.3}s  DONE {:>7.3}s",
                span.job_id, span.operation, span.name, span.bytes, span.start, span.end
            );
        }
    }
}

/// Hai khoảng thời gian có giao nhau.
fn overlaps(a: &Span, b: &Span) -> bool {
    a.start < b.end && b.start < a.end
}

/// Dispatcher live chạy upload/download thật: dừng ở điểm an toàn theo `StopProbe`, upload dừng ở
/// `gate` sau khi đọc part 2, `crash` làm transfer panic ở điểm an toàn (giả lập tắt app).
fn live_dispatcher(
    client: &ApiClient,
    db: &Db,
    limits: crate::sync::dispatcher::TransferLimits,
    paused: Arc<AtomicBool>,
    crash: Arc<AtomicBool>,
    gate: Option<(Arc<std::sync::Barrier>, Arc<std::sync::Barrier>)>,
    timeline: Arc<Timeline>,
) -> crate::sync::dispatcher::Dispatcher<
    impl FnMut(JobRow) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>>,
> {
    let (client, runner_db) = (client.clone(), db.clone());
    crate::sync::dispatcher::Dispatcher::new(
        db.clone(),
        limits,
        move |job: JobRow| -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>> {
            let (client, db, paused, crash, gate, timeline) = (
                client.clone(),
                runner_db.clone(),
                paused.clone(),
                crash.clone(),
                gate.clone(),
                timeline.clone(),
            );
            Box::pin(async move {
                let start = timeline.origin.elapsed().as_secs_f64();
                let probe = crate::sync::dispatcher::StopProbe::new(
                    db.clone(),
                    paused,
                    job.folder_id,
                    Duration::ZERO,
                );
                let should_stop = || {
                    if crash.load(Ordering::SeqCst) {
                        panic!("simulated app shutdown");
                    }
                    probe.should_stop()
                };
                let result = if job.operation == "download" {
                    run_download_job(&client, &db, &job, |_, _, _| {}, should_stop)
                        .await
                        .map(|_| ())
                } else {
                    run_upload_job(
                        &client,
                        &db,
                        &job,
                        |_, _| {},
                        should_stop,
                        |part| {
                            if let Some((arrive, release)) = &gate {
                                if part == 2 {
                                    arrive.wait();
                                    release.wait();
                                }
                            }
                        },
                    )
                    .await
                    .map(|_| ())
                };
                match result {
                    Ok(()) => {}
                    Err(AppError::Paused) => {
                        settle_stopped_job(&db, &job, &db.owned(&job), ACCESS_PAUSED_MESSAGE)
                            .unwrap();
                    }
                    Err(err) => panic!("transfer {} failed: {err}", job.id),
                }
                timeline.spans.lock().unwrap().push(Span {
                    job_id: job.id,
                    operation: job.operation.clone(),
                    name: job.relative_path.clone(),
                    bytes: job.bytes_total,
                    start,
                    end: timeline.origin.elapsed().as_secs_f64(),
                });
            })
        },
    )
}

impl Live {
    /// Ghi tệp và xếp hàng upload như watcher, KHÔNG claim (để dispatcher claim).
    fn queue_upload(&self, relative: &str, bytes: &[u8]) -> i64 {
        let path = self.local.join(relative);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, bytes).unwrap();
        let file_id = self
            .db
            .upsert_file(
                self.folder_id,
                relative,
                bytes.len() as i64,
                unix_mtime(&path),
                &sha256_file(&path).unwrap(),
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
            .unwrap()
    }

    /// Xếp hàng download một tệp đã có trên server vào thư mục thứ hai, KHÔNG claim.
    fn queue_download(
        &self,
        relative: &str,
        remote_file_id: i64,
        version_id: i64,
        hash: &str,
        size: usize,
    ) -> (PathBuf, i64) {
        let local = self.dir.path().join("down");
        std::fs::create_dir_all(&local).unwrap();
        let folder_id = self
            .db
            .upsert_folder(
                local.to_str().unwrap(),
                "down",
                Some(self.remote_folder_id),
                true,
                &[],
            )
            .unwrap();
        let file_id = self
            .db
            .ensure_remote_mapping(folder_id, relative, remote_file_id, Some(version_id))
            .unwrap();
        let job_id = self
            .db
            .enqueue_download(
                folder_id,
                file_id,
                relative,
                size as i64,
                remote_file_id,
                version_id,
                hash,
                None,
            )
            .unwrap();
        (local.join(relative), job_id)
    }
}

use std::sync::atomic::AtomicBool;

/// Case A–D + mất quyền (live): nhiều upload thật sự overlap; download bắt đầu khi 2 upload lớn
/// còn chạy; Pause/Resume và restart khi nhiều transfer đang chạy; folder mất quyền giữa chừng.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables"]
async fn live_concurrent_transfers() {
    use crate::sync::dispatcher::TransferLimits;
    let base = env("MEDILAB_E2E_URL");

    // A — 4 × 64 MiB upload cùng lúc.
    let lv = live(&base).await;
    let files: Vec<(String, Vec<u8>)> = (0..4)
        .map(|index| (format!("concurrent-{index}.bin"), random_bytes(64 * MIB)))
        .collect();
    for (name, bytes) in &files {
        lv.queue_upload(name, bytes);
    }
    let timeline = Timeline::new();
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        TransferLimits::default(),
        Arc::default(),
        Arc::default(),
        None,
        timeline.clone(),
    );
    dispatcher.run_until_idle().await.unwrap();
    timeline.print("A");
    let spans = timeline.spans();
    let overlapping = spans
        .iter()
        .enumerate()
        .flat_map(|(i, a)| spans[i + 1..].iter().map(move |b| (a, b)))
        .filter(|(a, b)| overlaps(a, b))
        .count();
    assert!(overlapping >= 1, "no overlapping uploads");
    for (name, bytes) in &files {
        lv.assert_server_content(name, &sha(bytes), bytes.len())
            .await;
    }
    println!("[A] {overlapping} overlapping upload pairs; all 4 SHA-256 verified on MinIO");

    // B — 2 upload lớn đang chạy, server có tệp mới cho download.
    let lv = live(&base).await;
    let seed = random_bytes(24 * MIB);
    let seed_job = lv.write_and_enqueue("remote.bin", &seed);
    run_upload_job(&lv.client, &lv.db, &seed_job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    let (remote_file_id, version_id) = lv
        .assert_server_content("remote.bin", &sha(&seed), seed.len())
        .await;
    let large: Vec<Vec<u8>> = (0..2).map(|_| random_bytes(160 * MIB)).collect();
    let large_jobs: Vec<i64> = large
        .iter()
        .enumerate()
        .map(|(index, bytes)| lv.queue_upload(&format!("large-{index}.bin"), bytes))
        .collect();
    let (download_path, download_job) = lv.queue_download(
        "remote.bin",
        remote_file_id,
        version_id,
        &sha(&seed),
        seed.len(),
    );
    let timeline = Timeline::new();
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        TransferLimits::default(),
        Arc::default(),
        Arc::default(),
        None,
        timeline.clone(),
    );
    dispatcher.run_until_idle().await.unwrap();
    timeline.print("B");
    let spans = timeline.spans();
    let span = |id: i64| spans.iter().find(|span| span.job_id == id).unwrap().clone();
    let download = span(download_job);
    let uploads_end = large_jobs
        .iter()
        .map(|id| span(*id).end)
        .fold(f64::MAX, f64::min);
    assert!(
        download.end < uploads_end,
        "download waited for the large uploads"
    );
    assert_eq!(sha256_file(&download_path).unwrap(), sha(&seed));
    println!(
        "[B] download started {:.3}s, done {:.3}s; first large upload done {:.3}s",
        download.start, download.end, uploads_end
    );

    // C và D cần 3 upload lớn chạy cùng lúc: 3 slot chung, không dành slot cho tệp nhỏ.
    let three_uploads = TransferLimits {
        uploads: 3,
        downloads: 1,
        small_lane: false,
    };
    // C — Pause khi 3 upload đang chạy, rồi Resume.
    let lv = live(&base).await;
    let files: Vec<(String, Vec<u8>)> = (0..3)
        .map(|index| (format!("pause-{index}.bin"), random_bytes(40 * MIB)))
        .collect();
    let ids: Vec<i64> = files
        .iter()
        .map(|(name, bytes)| lv.queue_upload(name, bytes))
        .collect();
    let paused = Arc::new(AtomicBool::new(false));
    let (arrive, release) = (
        Arc::new(std::sync::Barrier::new(4)),
        Arc::new(std::sync::Barrier::new(4)),
    );
    let coordinator = {
        let (arrive, release, paused) = (arrive.clone(), release.clone(), paused.clone());
        tokio::task::spawn_blocking(move || {
            arrive.wait();
            paused.store(true, Ordering::SeqCst);
            release.wait();
        })
    };
    let timeline = Timeline::new();
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        three_uploads,
        paused.clone(),
        Arc::default(),
        Some((arrive, release)),
        timeline.clone(),
    );
    dispatcher.fill_slots().await.unwrap();
    while dispatcher.running() > 0 {
        dispatcher.wait(Duration::from_millis(20)).await;
    }
    coordinator.await.unwrap();
    for id in &ids {
        let row = lv.job(&lv.db, *id);
        assert_eq!(
            (
                row.status.as_str(),
                row.attempt_count,
                row.last_error.clone()
            ),
            ("pending", 0, None)
        );
        let (session, parts, _) = lv.db.job_session_state(*id).unwrap();
        assert!(session.is_some());
        let parts: Vec<(i64, String)> = serde_json::from_str(&parts.unwrap()).unwrap();
        assert_eq!(parts.len(), 1, "stopped after the part in flight");
    }
    println!("[C] 3 running uploads paused at the part boundary: pending, attempt 0, 1 etag each");
    paused.store(false, Ordering::SeqCst);
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        three_uploads,
        paused,
        Arc::default(),
        None,
        Timeline::new(),
    );
    dispatcher.run_until_idle().await.unwrap();
    for (name, bytes) in &files {
        lv.assert_server_content(name, &sha(bytes), bytes.len())
            .await;
    }
    println!("[C] resumed; all 3 SHA-256 verified on MinIO");

    // D — tắt app khi 3 upload đang chạy, mở lại, resume.
    let lv = live(&base).await;
    let files: Vec<(String, Vec<u8>)> = (0..3)
        .map(|index| (format!("restart-{index}.bin"), random_bytes(40 * MIB)))
        .collect();
    let ids: Vec<i64> = files
        .iter()
        .map(|(name, bytes)| lv.queue_upload(name, bytes))
        .collect();
    let crash = Arc::new(AtomicBool::new(false));
    let (arrive, release) = (
        Arc::new(std::sync::Barrier::new(4)),
        Arc::new(std::sync::Barrier::new(4)),
    );
    let coordinator = {
        let (arrive, release, crash) = (arrive.clone(), release.clone(), crash.clone());
        tokio::task::spawn_blocking(move || {
            arrive.wait();
            crash.store(true, Ordering::SeqCst);
            release.wait();
        })
    };
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        three_uploads,
        Arc::default(),
        crash,
        Some((arrive, release)),
        Timeline::new(),
    );
    dispatcher.run_until_idle().await.unwrap();
    coordinator.await.unwrap();
    drop(dispatcher);
    let reopened = Db::open(&lv.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    for id in &ids {
        assert_eq!(lv.job(&reopened, *id).status, "pending");
    }
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &reopened,
        three_uploads,
        Arc::default(),
        Arc::default(),
        None,
        Timeline::new(),
    );
    dispatcher.run_until_idle().await.unwrap();
    for (name, bytes) in &files {
        lv.assert_server_content(name, &sha(bytes), bytes.len())
            .await;
    }
    println!(
        "[D] restart with 3 running uploads: all recovered to pending, resumed, SHA-256 verified"
    );

    // Mất quyền — giả lập bằng trạng thái `denied` cục bộ (cái `refresh_folder_access` ghi khi
    // server trả 403); không thu hồi được membership của chính owner trên dev stack.
    let lv = live(&base).await;
    let files: Vec<(String, Vec<u8>)> = (0..4)
        .map(|index| (format!("revoke-{index}.bin"), random_bytes(40 * MIB)))
        .collect();
    let ids: Vec<i64> = files
        .iter()
        .map(|(name, bytes)| lv.queue_upload(name, bytes))
        .collect();
    let (arrive, release) = (
        Arc::new(std::sync::Barrier::new(4)),
        Arc::new(std::sync::Barrier::new(4)),
    );
    let coordinator = {
        let (arrive, release, db, folder) =
            (arrive.clone(), release.clone(), lv.db.clone(), lv.folder_id);
        tokio::task::spawn_blocking(move || {
            arrive.wait();
            db.set_folder_access_state(folder, "denied").unwrap();
            release.wait();
        })
    };
    let limits = TransferLimits {
        uploads: 3,
        downloads: 1,
        small_lane: false,
    };
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        limits,
        Arc::default(),
        Arc::default(),
        Some((arrive, release)),
        Timeline::new(),
    );
    dispatcher.run_until_idle().await.unwrap();
    coordinator.await.unwrap();
    let stopped = ids
        .iter()
        .filter(|id| lv.job(&lv.db, **id).last_error.as_deref() == Some(ACCESS_PAUSED_MESSAGE))
        .count();
    assert_eq!(stopped, 3);
    assert!(ids.iter().all(|id| lv.job(&lv.db, *id).status == "pending"));
    assert!(files.iter().all(|(name, _)| lv.local.join(name).is_file()));
    for (name, _) in &files {
        assert!(!lv.has_canonical_version(name).await);
    }
    println!(
        "[revoke] 3 running uploads stopped with the access message; 4th never claimed; files kept"
    );
    lv.db.set_folder_access_state(lv.folder_id, "ok").unwrap();
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        limits,
        Arc::default(),
        Arc::default(),
        None,
        Timeline::new(),
    );
    dispatcher.run_until_idle().await.unwrap();
    for (name, bytes) in &files {
        lv.assert_server_content(name, &sha(bytes), bytes.len())
            .await;
    }
    println!("[revoke] re-granted: all 4 resumed and verified");
}

/// Chạy một workload upload qua dispatcher live với `limits`; trả `(tổng giây, timeline)`.
async fn run_upload_workload(
    base: &str,
    limits: crate::sync::dispatcher::TransferLimits,
    files: &[(String, Vec<u8>)],
) -> (f64, Vec<Span>) {
    let lv = live(base).await;
    for (name, bytes) in files {
        lv.queue_upload(name, bytes);
    }
    let timeline = Timeline::new();
    let started = Instant::now();
    let mut dispatcher = live_dispatcher(
        &lv.client,
        &lv.db,
        limits,
        Arc::default(),
        Arc::default(),
        None,
        timeline.clone(),
    );
    dispatcher.run_until_idle().await.unwrap();
    let total = started.elapsed().as_secs_f64();
    assert_eq!(timeline.spans().len(), files.len());
    (total, timeline.spans())
}

/// Benchmark live BEFORE (1 worker FIFO như trước) vs AFTER (dispatcher mặc định) trên cùng máy:
/// 100 tệp nhỏ, 10 tệp 32 MiB, và 2 tệp 128 MiB xếp trước 20 tệp nhỏ. Mỗi lượt dùng nội dung
/// ngẫu nhiên mới nên không có dedup.
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables; run with --release"]
async fn live_benchmark_transfers() {
    use crate::sync::dispatcher::TransferLimits;
    let base = env("MEDILAB_E2E_URL");
    let before = TransferLimits {
        uploads: 1,
        downloads: 1,
        small_lane: false,
    };
    let after = TransferLimits::default();
    let small = |count: usize| -> Vec<(String, Vec<u8>)> {
        (0..count)
            .map(|index| {
                let size = 10 * 1024 + (index * 9 * 1024) % (90 * 1024);
                (format!("small-{index}.bin"), random_bytes(size))
            })
            .collect()
    };
    for (label, limits) in [("BEFORE", before), ("AFTER", after)] {
        let files = small(100);
        let (total, _) = run_upload_workload(&base, limits, &files).await;
        println!(
            "[bench] {label:<6} 100 small files: {total:.2}s, {:.1} files/s",
            100.0 / total
        );

        let files: Vec<(String, Vec<u8>)> = (0..10)
            .map(|index| (format!("medium-{index}.bin"), random_bytes(32 * MIB)))
            .collect();
        let (total, _) = run_upload_workload(&base, limits, &files).await;
        println!(
            "[bench] {label:<6} 10 x 32 MiB: {total:.2}s, {:.1} MiB/s",
            320.0 / total
        );

        let mut files: Vec<(String, Vec<u8>)> = (0..2)
            .map(|index| (format!("big-{index}.bin"), random_bytes(128 * MIB)))
            .collect();
        files.extend(small(20));
        let (total, spans) = run_upload_workload(&base, limits, &files).await;
        let first_small = spans
            .iter()
            .filter(|span| span.name.starts_with("small-"))
            .map(|span| span.end)
            .fold(f64::MAX, f64::min);
        let last_small = spans
            .iter()
            .filter(|span| span.name.starts_with("small-"))
            .map(|span| span.end)
            .fold(0.0, f64::max);
        println!(
            "[bench] {label:<6} mixed 2 x 128 MiB + 20 small: total {total:.2}s, first small done {first_small:.2}s, all small done {last_small:.2}s"
        );
    }
}

/// Gắn một thiết bị thứ hai (đăng nhập với `client_uid` khác, DB và thư mục cục bộ riêng) vào
/// cùng folder server của `first`.
async fn attach_second_device(base: &str, first: &Live) -> Live {
    let uid = format!("second-device-{}", uuid::Uuid::new_v4());
    let session = ApiClient::login(
        base,
        &env("MEDILAB_E2E_LOGIN"),
        &env("MEDILAB_E2E_PASSWORD"),
        "second-device",
        "linux",
        "e2e",
        &uid,
    )
    .await
    .unwrap();
    assert_ne!(
        session.device_id,
        first.client_device_id(),
        "second device must be a distinct device"
    );
    let client = ApiClient::new(base, &session.api_key, session.device_id).unwrap();
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("b.db");
    let db = Db::open(&db_path).unwrap();
    let local = dir.path().join("b");
    std::fs::create_dir_all(&local).unwrap();
    let folder_id = db
        .upsert_folder(
            local.to_str().unwrap(),
            "second",
            Some(first.remote_folder_id),
            true,
            &[],
        )
        .unwrap();
    Live {
        dir,
        db_path,
        db,
        local,
        folder_id,
        remote_folder_id: first.remote_folder_id,
        client,
        api_key: session.api_key,
        device_id: session.device_id,
    }
}

impl Live {
    /// Device id của client (để phân biệt hai thiết bị).
    fn client_device_id(&self) -> i64 {
        self.client.device_id()
    }

    /// Sửa tệp rồi xếp hàng upload như watcher: base version là version đã đồng bộ của tệp.
    fn edit_and_enqueue(&self, relative: &str, bytes: &[u8]) -> JobRow {
        let path = self.local.join(relative);
        std::fs::write(&path, bytes).unwrap();
        let file_id = self
            .db
            .upsert_file(
                self.folder_id,
                relative,
                bytes.len() as i64,
                unix_mtime(&path),
                &sha256_file(&path).unwrap(),
            )
            .unwrap();
        let (remote_file_id, remote_version_id) = self.db.file_remote_ids(file_id).unwrap();
        self.db
            .enqueue_upload(
                self.folder_id,
                file_id,
                relative,
                bytes.len() as i64,
                remote_file_id,
                remote_version_id,
            )
            .unwrap();
        self.db
            .claim_next_job(Some("upload"), None)
            .unwrap()
            .unwrap()
    }

    /// Một lượt poll change feed như `EngineHandle::poll_remote_changes` (qua
    /// `plan_remote_change`), rồi chạy mọi download được xếp hàng. Trả các kết quả áp dụng.
    async fn poll_and_download(&self) -> Vec<crate::sync::engine::RemoteOutcome> {
        use crate::sync::engine::plan_remote_change;
        let folder = self
            .db
            .list_folders()
            .unwrap()
            .into_iter()
            .find(|folder| folder.id == self.folder_id)
            .unwrap();
        let mut outcomes = Vec::new();
        let mut after = self.db.change_cursor(self.remote_folder_id).unwrap();
        loop {
            let page = self
                .client
                .folder_changes(self.remote_folder_id, after, 50)
                .await
                .unwrap();
            for change in page.changes {
                outcomes.push(
                    plan_remote_change(&self.db, &folder, &change)
                        .await
                        .unwrap(),
                );
                self.db
                    .set_change_cursor(self.remote_folder_id, change.id)
                    .unwrap();
            }
            if !page.has_more {
                break;
            }
            after = page.next_cursor;
        }
        while let Some(job) = self.db.claim_next_job(Some("download"), None).unwrap() {
            run_download_job(&self.client, &self.db, &job, |_, _, _| {}, || false)
                .await
                .unwrap();
        }
        outcomes
    }
}

/// A6 — hai thiết bị (hai `client_uid`, hai DB) cùng một folder server:
/// (1) A upload → B poll change feed và download → SHA khớp;
/// (2) A và B cùng sửa một tệp từ cùng base → A commit, B nhận `conflict` qua cơ chế hiện có; cả
/// hai bản được giữ (canonical của A trên server, bản của B còn nguyên trên máy B và có trong
/// lịch sử version không canonical), và lượt poll sau của B không ghi đè bản của B.
/// Chỉ verify hành vi hiện có, không đổi semantics conflict.
#[tokio::test]
#[ignore = "needs a running dev stack and MEDILAB_E2E_* variables"]
async fn live_two_devices_sync_and_conflict() {
    use crate::sync::engine::RemoteOutcome;
    let base = env("MEDILAB_E2E_URL");
    let a = live(&base).await;
    let b = attach_second_device(&base, &a).await;

    let v1 = random_bytes(300_000);
    let job = a.write_and_enqueue("shared.txt", &v1);
    run_upload_job(&a.client, &a.db, &job, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    let outcomes = b.poll_and_download().await;
    assert!(
        outcomes.contains(&RemoteOutcome::DownloadQueued),
        "{outcomes:?}"
    );
    assert_eq!(sha256_file(&b.local.join("shared.txt")).unwrap(), sha(&v1));
    println!(
        "[two-devices] A uploaded v1; B polled the change feed and downloaded it; SHA matches"
    );

    let v2a = random_bytes(310_000);
    let v2b = random_bytes(320_000);
    let job_a = a.edit_and_enqueue("shared.txt", &v2a);
    let job_b = b.edit_and_enqueue("shared.txt", &v2b);
    assert_eq!(
        job_a.remote_version_id, job_b.remote_version_id,
        "same base version"
    );
    let report_a = run_upload_job(&a.client, &a.db, &job_a, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    assert!(matches!(report_a.outcome, UploadOutcome::Finalized(ref f) if f.status != "conflict"));
    let report_b = run_upload_job(&b.client, &b.db, &job_b, |_, _| {}, || false, |_| {})
        .await
        .unwrap();
    let conflict = match &report_b.outcome {
        UploadOutcome::Finalized(finalized) => finalized.clone(),
        other => panic!("expected a finalize result, got {other:?}"),
    };
    assert_eq!(conflict.status, "conflict", "{conflict:?}");
    assert_eq!(b.job(&b.db, job_b.id).status, "conflict");
    let b_row = b.db.file_by_id(job_b.file_id).unwrap().unwrap();
    assert_eq!(b_row.status, "conflict");
    assert_eq!(
        sha256_file(&b.local.join("shared.txt")).unwrap(),
        sha(&v2b),
        "B's copy kept"
    );
    assert_eq!(
        sha256_file(&a.local.join("shared.txt")).unwrap(),
        sha(&v2a),
        "A's copy kept"
    );
    let (remote_file_id, _) = a
        .assert_server_content("shared.txt", &sha(&v2a), v2a.len())
        .await;
    let versions = a
        .client
        .get_file_versions(remote_file_id, 50, 0)
        .await
        .unwrap();
    let hashes: Vec<(String, bool)> = versions
        .items
        .iter()
        .map(|version| (version.content_hash.clone(), version.is_canonical))
        .collect();
    assert!(hashes.contains(&(sha(&v2a), true)), "{hashes:?}");
    assert!(
        hashes.contains(&(sha(&v2b), false)),
        "B's bytes kept on the server as a non-canonical version: {hashes:?}"
    );
    println!(
        "[two-devices] concurrent edit: A committed v2 (canonical), B got conflict {:?}; B's bytes kept locally and as non-canonical server version",
        conflict.conflict_id
    );

    let outcomes = b.poll_and_download().await;
    assert!(
        !outcomes.contains(&RemoteOutcome::DownloadQueued),
        "{outcomes:?}"
    );
    assert_eq!(sha256_file(&b.local.join("shared.txt")).unwrap(), sha(&v2b));
    println!("[two-devices] B's next poll skipped the conflicted file ({outcomes:?}); local copy untouched");
}

/// Kết quả một lượt upload đo đạc.
struct MeasuredUpload {
    seconds: f64,
    mib_per_second: f64,
    peak_budget_mib: usize,
}

/// Upload `bytes` (một job mới) với cửa sổ `window`, ngân sách 128 MiB riêng; kiểm SHA-256 của
/// object trên MinIO; trả thời gian, throughput và mức ngân sách cao nhất.
async fn measured_upload(lv: &Live, name: &str, bytes: &[u8], window: usize) -> MeasuredUpload {
    use crate::sync::engine::{run_upload_job_with, UploadOptions};
    use crate::sync::part_budget::{PartBudget, DEFAULT_PART_BUDGET_MIB};
    let job = lv.write_and_enqueue(name, bytes);
    let options = UploadOptions {
        part_concurrency: window,
        budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
    };
    let started = Instant::now();
    run_upload_job_with(
        &lv.client,
        &lv.db,
        &job,
        &lv.db.owned(&job),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    let seconds = started.elapsed().as_secs_f64();
    lv.assert_server_content(name, &sha(bytes), bytes.len())
        .await;
    MeasuredUpload {
        seconds,
        mib_per_second: bytes.len() as f64 / MIB as f64 / seconds,
        peak_budget_mib: options.budget.peak_mib(),
    }
}

/// Etag đã lưu của job (part number, tăng dần).
fn saved_part_numbers(db: &Db, job_id: i64) -> Vec<i64> {
    let (_, parts, _) = db.job_session_state(job_id).unwrap();
    let mut numbers: Vec<i64> = parts
        .map(|raw| serde_json::from_str::<Vec<(i64, String)>>(&raw).unwrap())
        .unwrap_or_default()
        .into_iter()
        .map(|(number, _)| number)
        .collect();
    numbers.sort_unstable();
    numbers
}

/// Stage B qua proxy giới hạn tốc độ THEO KẾT NỐI (mô phỏng link BDP cao): benchmark 256 MiB với
/// `part_concurrency` 1 và 3; Pause khi nhiều part đang bay rồi Resume; kill giữa cửa sổ rồi
/// restart. SHA-256 của object trên MinIO được kiểm ở mọi case. Chạy riêng tiến trình, release:
/// `cargo test --release -- --ignored --exact sync::live_tests::live_multipart_proxy_benchmark_and_failures --nocapture`
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "needs a running dev stack, MEDILAB_E2E_* variables, --release and its own process (--exact)"]
async fn live_multipart_proxy_benchmark_and_failures() {
    use crate::sync::engine::{run_upload_job_with, UploadOptions};
    use crate::sync::part_budget::{PartBudget, DEFAULT_PART_BUDGET_MIB};
    let per_connection = 4 * MIB as u64;
    let proxy = ThrottleProxy::start().await;
    for name in [
        "NO_PROXY",
        "no_proxy",
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
    ] {
        std::env::remove_var(name);
    }
    std::env::set_var("HTTP_PROXY", &proxy.addr);
    std::env::set_var("http_proxy", &proxy.addr);
    let lv = live(&env("MEDILAB_E2E_URL")).await;
    proxy.rate.store(per_connection, Ordering::SeqCst);

    for window in [1, 3] {
        proxy.stats.lock().unwrap().max_puts_in_flight = 0;
        let bytes = random_bytes(256 * MIB);
        let measured =
            measured_upload(&lv, &format!("bench-proxy-{window}.bin"), &bytes, window).await;
        let max_in_flight = proxy.stats.lock().unwrap().max_puts_in_flight;
        println!(
            "[bench-proxy] part_concurrency={window} 256 MiB: {:.2}s, {:.2} MiB/s, max concurrent PUTs={max_in_flight}, peak budget={} MiB, SHA verified",
            measured.seconds, measured.mib_per_second, measured.peak_budget_mib
        );
        assert!(max_in_flight <= window, "window exceeded");
        assert!(measured.peak_budget_mib <= DEFAULT_PART_BUDGET_MIB);
    }

    // Pause khi ≥ 1 part đã xong và ≥ 2 PUT còn đang bay.
    let bytes = random_bytes(128 * MIB);
    let job = lv.write_and_enqueue("pause-proxy.bin", &bytes);
    let paused = AtomicBool::new(false);
    let options = UploadOptions {
        part_concurrency: 3,
        budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
    };
    let err = run_upload_job_with(
        &lv.client,
        &lv.db,
        &job,
        &lv.db.owned(&job),
        &options,
        |_, _| {
            if proxy.stats.lock().unwrap().puts_in_flight >= 2 {
                paused.store(true, Ordering::SeqCst);
            }
        },
        || paused.load(Ordering::SeqCst),
        |_| {},
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused), "{err:?}");
    let saved = saved_part_numbers(&lv.db, job.id);
    assert!(!saved.is_empty() && saved.len() < 8, "{saved:?}");
    settle_stopped_job(&lv.db, &job, &lv.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap();
    let resumed = lv.db.next_job().unwrap().unwrap();
    let report = run_upload_job_with(
        &lv.client,
        &lv.db,
        &resumed,
        &lv.db.owned(&resumed),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_eq!(
        report.parts_uploaded as usize,
        8 - saved.len(),
        "only missing parts resent"
    );
    lv.assert_server_content("pause-proxy.bin", &sha(&bytes), bytes.len())
        .await;
    println!(
        "[pause-proxy] paused with several PUTs in flight; saved ETags {saved:?}; resume sent {} of 8 parts; SHA verified",
        report.parts_uploaded
    );

    // Kill giữa cửa sổ: hủy task khi ≥ 1 part đã lưu và ≥ 2 PUT đang bay; mở lại DB, resume.
    let bytes = random_bytes(128 * MIB);
    let job = lv.write_and_enqueue("restart-proxy.bin", &bytes);
    let task = {
        let (client, db, job, options) = (
            lv.client.clone(),
            lv.db.clone(),
            job.clone(),
            options.clone(),
        );
        tokio::spawn(async move {
            run_upload_job_with(
                &client,
                &db,
                &job,
                &db.owned(&job),
                &options,
                |_, _| {},
                || false,
                |_| {},
            )
            .await
        })
    };
    loop {
        let in_flight = proxy.stats.lock().unwrap().puts_in_flight;
        if !saved_part_numbers(&lv.db, job.id).is_empty() && in_flight >= 2 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    task.abort();
    let _ = task.await;
    let saved = saved_part_numbers(&lv.db, job.id);
    let before: Vec<i64> = proxy
        .stats
        .lock()
        .unwrap()
        .requests
        .iter()
        .filter_map(|request| request.part_number)
        .collect();
    let reopened = Db::open(&lv.db_path).unwrap();
    reopened.recover_jobs().unwrap();
    let recovered = reopened.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job.id);
    let report = run_upload_job_with(
        &lv.client,
        &reopened,
        &recovered,
        &reopened.owned(&recovered),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    let after: Vec<i64> = proxy
        .stats
        .lock()
        .unwrap()
        .requests
        .iter()
        .filter_map(|request| request.part_number)
        .skip(before.len())
        .collect();
    for part in &saved {
        assert!(
            !after.contains(part),
            "completed part {part} re-sent after restart"
        );
    }
    assert_eq!(report.parts_uploaded as usize, 8 - saved.len());
    lv.assert_server_content("restart-proxy.bin", &sha(&bytes), bytes.len())
        .await;
    println!(
        "[restart-proxy] killed with PUTs in flight; saved ETags {saved:?} not re-sent; resumed {} parts; SHA verified",
        report.parts_uploaded
    );
    proxy.rate.store(0, Ordering::SeqCst);
}

/// Stage B trên loopback tới MinIO local, không giới hạn tốc độ: 256 MiB với `part_concurrency`
/// 1 và 3, mỗi mức hai lượt. Chạy release:
/// `cargo test --release -- --ignored --exact sync::live_tests::live_multipart_loopback_benchmark --nocapture`
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "needs a running dev stack, MEDILAB_E2E_* variables and --release"]
async fn live_multipart_loopback_benchmark() {
    let lv = live(&env("MEDILAB_E2E_URL")).await;
    for round in 1..=2 {
        for window in [1, 3] {
            let bytes = random_bytes(256 * MIB);
            let measured = measured_upload(
                &lv,
                &format!("bench-loop-{round}-{window}.bin"),
                &bytes,
                window,
            )
            .await;
            println!(
                "[bench-loopback] round {round} part_concurrency={window} 256 MiB: {:.2}s, {:.1} MiB/s, peak budget={} MiB, SHA verified",
                measured.seconds, measured.mib_per_second, measured.peak_budget_mib
            );
        }
    }
}

/// Số part của tệp 128 MiB với part 16 MiB của server dev.
const KILL_TEST_PARTS: i64 = 8;

/// Các request proxy ghi nhận từ vị trí `start` trở đi.
fn requests_since(proxy: &ThrottleProxy, start: usize) -> Vec<ProxiedRequest> {
    proxy.stats.lock().unwrap().requests[start..].to_vec()
}

/// Lượt resume chỉ được: PUT đúng các part còn thiếu (mỗi part một lần, không part đã lưu ETag),
/// không `prepare` session mới, và finalize đúng session cũ `session_id`.
fn assert_resumed_only_missing(requests: &[ProxiedRequest], saved: &[i64], session_id: i64) {
    let mut put: Vec<i64> = requests
        .iter()
        .filter(|request| request.method == "PUT")
        .filter_map(|request| request.part_number)
        .collect();
    put.sort_unstable();
    let missing: Vec<i64> = (1..=KILL_TEST_PARTS)
        .filter(|part| !saved.contains(part))
        .collect();
    assert_eq!(put, missing, "resume PUTs exactly the missing parts once");
    assert!(
        !requests
            .iter()
            .any(|request| request.path.ends_with("/uploads/prepare")),
        "resume must not prepare a new session"
    );
    let finalize = format!("/uploads/{session_id}/finalize");
    assert!(
        requests
            .iter()
            .any(|request| request.path.ends_with(&finalize)),
        "finalize on the same upload session {session_id}"
    );
}

/// Pause/Resume và kill TIẾN TRÌNH giữa multipart trên Odoo + MinIO thật, không cần GUI:
///
/// 1–3. Pause (qua `StopProbe` như app) khi ≥ 2 PUT đang bay → Resume dùng cùng
///      `upload_session_id`, chỉ PUT part còn thiếu.
/// 4–8. Worker là tiến trình con (`live_multipart_kill_worker`) bị SIGKILL khi ≥ 1 part đã lưu
///      ETag và ≥ 2 PUT đang bay → mở lại SQLite hiện tại, `recover_jobs`, resume cùng session,
///      không PUT lại part đã lưu, SHA-256 của object trên MinIO khớp.
///
/// Mọi request (kể cả của tiến trình con) đi qua proxy giới hạn 4 MiB/s mỗi kết nối để multipart
/// kéo dài đủ lâu; proxy đặt `HTTP_PROXY` nên chạy riêng tiến trình:
/// `cargo test -- --ignored --exact sync::live_tests::live_multipart_pause_resume_and_process_kill --nocapture`
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "needs a running dev stack, MEDILAB_E2E_* variables and its own process (--exact)"]
async fn live_multipart_pause_resume_and_process_kill() {
    use crate::sync::dispatcher::{StopProbe, StoppedAs, ACCESS_CHECK_INTERVAL};
    use crate::sync::engine::{run_upload_job_with, UploadOptions};
    use crate::sync::part_budget::{PartBudget, DEFAULT_PART_BUDGET_MIB};
    use std::sync::atomic::AtomicBool;
    let proxy = ThrottleProxy::start().await;
    for name in [
        "NO_PROXY",
        "no_proxy",
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
    ] {
        std::env::remove_var(name);
    }
    std::env::set_var("HTTP_PROXY", &proxy.addr);
    std::env::set_var("http_proxy", &proxy.addr);
    let lv = live(&env("MEDILAB_E2E_URL")).await;
    proxy.rate.store(4 * MIB as u64, Ordering::SeqCst);
    let options = UploadOptions {
        part_concurrency: 3,
        budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
    };

    // 1. Pause multipart đang chạy, đúng đường của app: cờ pause + StopProbe.
    let bytes = random_bytes(KILL_TEST_PARTS as usize * 16 * MIB);
    let job = lv.write_and_enqueue("pause-resume.bin", &bytes);
    let paused = Arc::new(AtomicBool::new(false));
    let probe = StopProbe::new(
        lv.db.clone(),
        paused.clone(),
        job.folder_id,
        ACCESS_CHECK_INTERVAL,
    );
    let err = run_upload_job_with(
        &lv.client,
        &lv.db,
        &job,
        &lv.db.owned(&job),
        &options,
        |_, _| {
            if proxy.stats.lock().unwrap().puts_in_flight >= 2 {
                paused.store(true, Ordering::SeqCst);
            }
        },
        || probe.should_stop(),
        |_| {},
    )
    .await
    .unwrap_err();
    assert!(matches!(err, AppError::Paused), "{err:?}");
    let session = lv.db.job_session_state(job.id).unwrap().0.expect("session");
    let saved = saved_part_numbers(&lv.db, job.id);
    assert!(
        !saved.is_empty() && (saved.len() as i64) < KILL_TEST_PARTS,
        "{saved:?}"
    );
    assert_eq!(
        settle_stopped_job(&lv.db, &job, &lv.db.owned(&job), ACCESS_PAUSED_MESSAGE).unwrap(),
        StoppedAs::Paused
    );
    println!("[pause] session {session}: paused with saved ETags {saved:?}, job pending");

    // 2–3. Resume: cùng upload_session_id, chỉ PUT part còn thiếu.
    paused.store(false, Ordering::SeqCst);
    let mark = proxy.stats.lock().unwrap().requests.len();
    let resumed = lv.db.next_job().unwrap().unwrap();
    assert_eq!(resumed.id, job.id);
    assert_eq!(resumed.session_id, Some(session), "same upload_session_id");
    let report = run_upload_job_with(
        &lv.client,
        &lv.db,
        &resumed,
        &lv.db.owned(&resumed),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_resumed_only_missing(&requests_since(&proxy, mark), &saved, session);
    assert_eq!(report.parts_uploaded, KILL_TEST_PARTS - saved.len() as i64);
    lv.assert_server_content("pause-resume.bin", &sha(&bytes), bytes.len())
        .await;
    println!(
        "[resume] same session {session}: PUT only {} missing parts, SHA verified on MinIO",
        report.parts_uploaded
    );

    // 4. Kill TIẾN TRÌNH giữa multipart: worker con claim job và upload qua cùng proxy.
    let bytes = random_bytes(KILL_TEST_PARTS as usize * 16 * MIB);
    let job_id = lv.write_and_enqueue_pending("process-kill.bin", &bytes);
    let mut child = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--ignored",
            "--exact",
            "sync::live_tests::live_multipart_kill_worker",
            "--nocapture",
        ])
        .env("MEDILAB_KILL_WORKER_DB", &lv.db_path)
        .env("MEDILAB_KILL_WORKER_KEY", &lv.api_key)
        .env("MEDILAB_KILL_WORKER_DEVICE", lv.device_id.to_string())
        .stdout(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(180);
    loop {
        assert!(
            child.try_wait().unwrap().is_none(),
            "worker exited before the kill"
        );
        assert!(Instant::now() < deadline, "worker made no progress");
        let in_flight = proxy.stats.lock().unwrap().puts_in_flight;
        if !saved_part_numbers(&lv.db, job_id).is_empty() && in_flight >= 2 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    child.kill().unwrap();
    let status = child.wait().unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        assert_eq!(status.signal(), Some(9), "worker killed by SIGKILL");
    }
    assert!(!status.success());
    let saved = saved_part_numbers(&lv.db, job_id);
    let session = lv.db.job_session_state(job_id).unwrap().0.expect("session");
    assert_eq!(
        lv.job(&lv.db, job_id).status,
        "running",
        "killed mid-transfer"
    );
    println!("[kill] worker SIGKILLed: session {session}, saved ETags {saved:?}");

    // 5–8. Restart từ SQLite hiện tại: job về pending, resume cùng session, không PUT lại part đã
    // lưu, SHA-256 khớp.
    let mark = proxy.stats.lock().unwrap().requests.len();
    let restarted = Db::open(&lv.db_path).unwrap();
    restarted.recover_jobs().unwrap();
    let recovered = restarted.next_job().unwrap().unwrap();
    assert_eq!(recovered.id, job_id);
    assert_eq!(
        recovered.session_id,
        Some(session),
        "same upload_session_id"
    );
    let report = run_upload_job_with(
        &lv.client,
        &restarted,
        &recovered,
        &restarted.owned(&recovered),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await
    .unwrap();
    assert_resumed_only_missing(&requests_since(&proxy, mark), &saved, session);
    assert_eq!(report.parts_uploaded, KILL_TEST_PARTS - saved.len() as i64);
    lv.assert_server_content("process-kill.bin", &sha(&bytes), bytes.len())
        .await;
    println!(
        "[restart] same session {session}: completed parts {saved:?} not re-sent, {} missing parts PUT, SHA verified on MinIO",
        report.parts_uploaded
    );
    proxy.rate.store(0, Ordering::SeqCst);
}

/// Tiến trình con của `live_multipart_pause_resume_and_process_kill`: mở SQLite của tiến trình
/// cha, claim job upload và chạy multipart (3 PUT/tệp) tới khi bị SIGKILL. Chạy độc lập (không có
/// `MEDILAB_KILL_WORKER_DB`) thì không làm gì.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "child process of live_multipart_pause_resume_and_process_kill"]
async fn live_multipart_kill_worker() {
    use crate::sync::engine::{run_upload_job_with, UploadOptions};
    use crate::sync::part_budget::{PartBudget, DEFAULT_PART_BUDGET_MIB};
    let Ok(db_path) = std::env::var("MEDILAB_KILL_WORKER_DB") else {
        println!("skipped: runs only as the child of live_multipart_pause_resume_and_process_kill");
        return;
    };
    let client = ApiClient::new(
        &env("MEDILAB_E2E_URL"),
        &env("MEDILAB_KILL_WORKER_KEY"),
        env("MEDILAB_KILL_WORKER_DEVICE").parse().unwrap(),
    )
    .unwrap();
    let db = Db::open(std::path::Path::new(&db_path)).unwrap();
    let job = db.next_job().unwrap().expect("queued upload job");
    let options = UploadOptions {
        part_concurrency: 3,
        budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
    };
    let result = run_upload_job_with(
        &client,
        &db,
        &job,
        &db.owned(&job),
        &options,
        |_, _| {},
        || false,
        |_| {},
    )
    .await;
    panic!(
        "worker must be killed before the upload ends: {:?}",
        result.map(|report| report.parts_uploaded)
    );
}
