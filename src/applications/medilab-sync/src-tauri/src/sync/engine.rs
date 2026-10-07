use crate::api::{ApiClient, FolderChangeDto, RuleDto};
use crate::auth;
use crate::config::AppSettings;
use crate::error::{is_odoo_auth_failure, AppError, AppResult};
use crate::storage::{
    apply_remote_base_on, cancel_active_uploads_on, clear_file_conflict_on, clear_job_session_on,
    enqueue_download_on, file_fingerprint_on, file_row_matches, last_synced_hash_on,
    mark_file_conflict_on, save_job_session_on, set_file_fingerprint_on, set_job_content_hash_on,
    set_progress_on, set_suppress_hash_on, transition_running_job_on, Db, FileFingerprint,
    FolderRow, JobRow, RunningJob,
};
use crate::sync::decision::{decide_sync_action, SyncAction};
use crate::sync::dispatcher::{
    clamp_concurrency, settle_stopped_job, Dispatcher, StopProbe, TransferLimits,
    ACCESS_CHECK_INTERVAL,
};
use crate::sync::download::{
    atomic_replace, download_object, download_temp_path, fsync_path, is_internal_path,
    preserve_local_copy, verify_download,
};
use crate::sync::hash::{is_stable, sha256_file, unix_mtime};
use crate::sync::part_budget::{PartBudget, PartPermit, DEFAULT_PART_BUDGET_MIB};
use crate::sync::resume::{resume_transfers, RefreshTrigger};
use crate::sync::retry::{is_connectivity_error, is_retryable, next_status};
use crate::sync::rules::{matches_rules, relative_path, SyncRule};
use crate::sync::status_events::{
    run_status_coalescer, StatusEventHub, DEFAULT_STATUS_COALESCE_INTERVAL,
};
use notify::{Config, EventKind, PollWatcher, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};
use tokio::sync::Mutex;
use tokio::task::JoinSet;
use tracing::Instrument;

/// Thông báo gắn vào job bị tạm dừng vì folder mất quyền truy cập (job vẫn `pending`).
pub const ACCESS_PAUSED_MESSAGE: &str = "Mất quyền truy cập — đồng bộ đã tạm dừng.";

/// Khoảng thời gian dùng lại kết quả đối chiếu quyền folder cho các job cùng gặp 403.
const ACCESS_REFRESH_COALESCE: Duration = Duration::from_secs(5);
/// Xin lại URL presigned sớm hơn hạn server báo một khoảng này, để PUT không bắt đầu sát lúc hết hạn.
const PRESIGN_EXPIRY_MARGIN: Duration = Duration::from_secs(60);
const STABLE_WAIT: Duration = Duration::from_millis(400);
/// Kích thước part khi tiếp tục một session của job lưu trước khi có cột `sync_job.part_size`;
/// bằng `PART_SIZE` phía server lúc đó (`src/modules/medilab_sync/services/object_storage.py`).
pub(crate) const LEGACY_PART_SIZE: i64 = 16 * 1024 * 1024;
/// Thông báo lỗi (đáng thử lại) khi nội dung đọc để upload không khớp expected hash.
const CHANGED_DURING_UPLOAD: &str = "Tệp đã thay đổi trong lúc tải lên, sẽ thử lại";

/// Chạy một công việc đồng bộ nặng trên blocking pool và giữ ngữ cảnh tracing hiện tại.
async fn run_blocking<T, F>(work: F) -> AppResult<T>
where
    T: Send + 'static,
    F: FnOnce() -> AppResult<T> + Send + 'static,
{
    let span = tracing::Span::current();
    tokio::task::spawn_blocking(move || span.in_scope(work))
        .await
        .map_err(|err| AppError::Message(format!("Tác vụ blocking thất bại: {err}")))?
}

/// Tuần tự hóa các công việc blocking dùng chung một tài nguyên trước khi đưa chúng sang pool.
async fn run_serialized_blocking<T, F>(gate: Arc<Mutex<()>>, work: F) -> AppResult<T>
where
    T: Send + 'static,
    F: FnOnce() -> AppResult<T> + Send + 'static,
{
    let _guard = gate.lock().await;
    run_blocking(work).await
}

/// Tay cầm dùng chung tới engine đồng bộ nền: state cục bộ, cờ tạm dừng/degraded/hết phiên, và
/// cấu hình đang tải.
#[derive(Clone)]
pub struct EngineHandle {
    pub db: Db,
    pub paused: Arc<AtomicBool>,
    pub degraded: Arc<AtomicBool>,
    /// Phiên đăng nhập: API key giữ trong bộ nhớ + trạng thái xác thực. Không bao giờ đọc keyring.
    pub session: Arc<auth::Session>,
    pub settings: Arc<Mutex<AppSettings>>,
    reconcile_gate: Arc<Mutex<()>>,
    /// Thời điểm lần đối chiếu quyền folder gần nhất do job gặp 403; nhiều job cùng gặp 403 chỉ
    /// gọi `GET /folders` một lần.
    access_refresh: Arc<Mutex<Option<Instant>>>,
    /// Lượt poll + đối soát chạy nền sau khi bỏ tạm dừng (gộp các lần Tiếp tục dồn dập).
    resume_refresh: RefreshTrigger,
    /// Ngân sách buffer part dùng chung cho mọi upload của tiến trình.
    part_budget: Arc<PartBudget>,
    /// Số PUT part song song của một tệp, chốt từ settings ẩn khi dispatcher khởi động.
    part_concurrency: Arc<std::sync::atomic::AtomicUsize>,
    file_revision: Arc<AtomicU64>,
    status_hub: StatusEventHub,
    status_rx: Arc<std::sync::Mutex<Option<tokio::sync::mpsc::Receiver<()>>>>,
    app: AppHandle,
}

/// Delta tiến độ của một job đồng bộ (upload hoặc download).
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ProgressDeltaDto {
    pub job_id: i64,
    pub done: i64,
    pub total: i64,
}

/// Sự kiện thông báo danh sách tệp đã thay đổi về mặt ngữ nghĩa, kèm số thứ tự phiên bản tăng dần.
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct FilesChangedDto {
    pub revision: u64,
}

/// Snapshot trạng thái đồng bộ gửi cho frontend: phiên đăng nhập, số job theo loại, folder và
/// job hiện có.
#[derive(Clone, Serialize)]
pub struct StatusDto {
    pub paused: bool,
    pub degraded: bool,
    pub logged_in: bool,
    pub session_expired: bool,
    /// Trạng thái xác thực chi tiết; `logged_in`/`session_expired` giữ lại cho tương thích.
    pub auth_state: auth::AuthState,
    pub user_name: Option<String>,
    pub odoo_url: String,
    pub pending: i64,
    pub uploading: i64,
    pub downloading: i64,
    pub failed: i64,
    pub conflict: i64,
    pub completed: i64,
    pub folders: Vec<FolderRow>,
    pub jobs: Vec<JobRow>,
}

impl EngineHandle {
    /// Dựng engine với state ban đầu từ cấu hình đã lưu.
    pub fn new(db: Db, settings: AppSettings, app: AppHandle) -> Self {
        let (status_hub, status_rx) = StatusEventHub::new();
        Self {
            paused: Arc::new(AtomicBool::new(settings.paused)),
            degraded: Arc::new(AtomicBool::new(false)),
            session: Arc::new(auth::Session::default()),
            settings: Arc::new(Mutex::new(settings)),
            reconcile_gate: Arc::new(Mutex::new(())),
            access_refresh: Arc::new(Mutex::new(None)),
            resume_refresh: RefreshTrigger::default(),
            part_budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
            part_concurrency: Arc::new(std::sync::atomic::AtomicUsize::new(1)),
            file_revision: Arc::new(AtomicU64::new(0)),
            status_hub,
            status_rx: Arc::new(std::sync::Mutex::new(Some(status_rx))),
            db,
            app,
        }
    }

    /// Khởi động engine: phục hồi job dở dang, dọn tệp tạm mồ côi, rồi chạy các vòng lặp nền
    /// (watcher, reconcile định kỳ, poll thay đổi, worker xử lý job, bộ gộp sự kiện trạng thái).
    pub fn start(&self) {
        let _ = self.db.recover_jobs();
        let _ = self.cleanup_stale_temps();
        let watcher = self.clone();
        std::thread::spawn(move || watcher.watch_loop());
        let engine = self.clone();
        tauri::async_runtime::spawn(async move {
            engine.reconcile_loop().await;
        });
        let poller = self.clone();
        tauri::async_runtime::spawn(async move {
            poller.change_poll_loop().await;
        });
        let dispatcher = self.clone();
        tauri::async_runtime::spawn(async move {
            dispatcher.dispatch_loop().await;
        });
        let rx_opt = self.status_rx.lock().unwrap().take();
        if let Some(status_rx) = rx_opt {
            let status_engine = self.clone();
            tauri::async_runtime::spawn(async move {
                run_status_coalescer(status_rx, DEFAULT_STATUS_COALESCE_INTERVAL, move || {
                    let engine = status_engine.clone();
                    let app = engine.app.clone();
                    async move {
                        let snapshot =
                            tokio::task::spawn_blocking(move || engine.status_snapshot()).await;
                        if let Ok(Ok(status)) = snapshot {
                            let _ = app.emit("sync-status-changed", &status);
                        }
                    }
                })
                .await;
            });
        }
    }

    /// Bật/tắt tạm dừng và lưu vào cấu hình. Tạm dừng có hiệu lực ngay (transfer dừng ở điểm an
    /// toàn). Bỏ tạm dừng cũng trả về ngay: poll change feed + đối soát chạy nền, gộp các lần
    /// Tiếp tục dồn dập, để nút Tạm dừng dùng lại được trong lúc đối soát còn chạy.
    ///
    /// Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#concurrent-transfers
    pub async fn set_paused(&self, paused: bool) {
        tracing::info!(
            paused,
            "{}",
            if paused {
                "pause requested"
            } else {
                "resume requested"
            }
        );
        if paused {
            self.paused.store(true, Ordering::SeqCst);
        }
        let mut settings = self.settings.lock().await;
        settings.paused = paused;
        let _ = self.db.save_settings(&settings);
        drop(settings);
        if !paused {
            let engine = self.clone();
            resume_transfers(&self.paused, &self.resume_refresh, move || {
                let engine = engine.clone();
                async move { engine.refresh_after_resume().await }
            })
            .await;
        }
        self.emit_status();
    }

    /// Lượt nền sau khi bỏ tạm dừng: hỏi change feed rồi đối soát toàn bộ (qua `reconcile_gate`
    /// như mọi lượt đối soát khác). Bỏ qua nếu người dùng đã tạm dừng lại; lỗi được log.
    async fn refresh_after_resume(&self) {
        if self.paused.load(Ordering::SeqCst) {
            tracing::info!("post-resume refresh skipped: sync paused again");
            return;
        }
        if let Err(err) = self.poll_remote_changes().await {
            tracing::warn!("post-resume change poll failed: {err}");
        }
        if let Err(err) = self.reconcile_all().await {
            tracing::warn!("post-resume reconciliation failed: {err}");
        }
    }

    /// Gửi tín hiệu thông báo trạng thái thay đổi vào kênh gộp sự kiện nền (không chặn).
    #[tracing::instrument(level = "debug", name = "sync.emit_status", skip_all)]
    pub fn emit_status(&self) {
        self.status_hub.notify();
    }

    /// Gửi sự kiện `sync-files-changed` cho frontend khi danh sách tệp có thay đổi ngữ nghĩa.
    #[tracing::instrument(level = "debug", name = "sync.emit_files_changed", skip_all)]
    pub fn emit_files_changed(&self) {
        let revision = self.file_revision.fetch_add(1, Ordering::SeqCst) + 1;
        let _ = self
            .app
            .emit("sync-files-changed", FilesChangedDto { revision });
    }

    /// Dựng snapshot trạng thái hiện tại từ DB cục bộ và state trong bộ nhớ.
    #[tracing::instrument(level = "debug", name = "sync.status_snapshot", skip_all)]
    pub fn status_snapshot(&self) -> AppResult<StatusDto> {
        let (pending, uploading, downloading, failed, conflict, completed) = self.db.counts()?;
        let settings = self.db.load_settings().unwrap_or_default();
        let auth_state = self.session.state();
        Ok(StatusDto {
            paused: self.paused.load(Ordering::SeqCst),
            degraded: self.degraded.load(Ordering::SeqCst),
            // Lấy từ bộ nhớ: dựng status (chạy rất thường xuyên) không được chạm keyring của OS.
            logged_in: auth_state == auth::AuthState::Authenticated,
            session_expired: auth_state == auth::AuthState::SessionExpired,
            auth_state,
            user_name: self.db.meta_get("user_name")?,
            odoo_url: settings.odoo_url,
            pending,
            uploading,
            downloading,
            failed,
            conflict,
            completed,
            folders: self.db.list_folders()?,
            jobs: self.db.list_jobs()?,
        })
    }

    /// Cổng chính: một folder chỉ được watch/quét/đối soát khi đang bật và chưa bị server từ
    /// chối quyền truy cập.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-work-with-a-mapped-folder
    fn folder_sync_allowed(folder: &FolderRow) -> bool {
        folder.enabled && folder.access_state != "denied"
    }

    /// Lưu ngữ cảnh mẫu LIMS mới nhất từ server vào DB cục bộ.
    fn apply_remote_lab_context(
        &self,
        folder_id: i64,
        remote: &crate::api::FolderDto,
    ) -> AppResult<()> {
        self.db.apply_folder_lab_context(folder_id, remote)
    }

    /// Đối chiếu danh sách folder trên server: cập nhật ngữ cảnh mẫu cho folder còn thấy được,
    /// đánh dấu `denied` cho folder đã mất quyền truy cập.
    #[tracing::instrument(level = "debug", name = "sync.refresh_folder_access", skip_all)]
    async fn refresh_folder_access(&self, client: &ApiClient) -> AppResult<()> {
        let remotes = client.list_folders().await?;
        let remote_ids: HashSet<i64> = remotes.iter().map(|folder| folder.id).collect();
        for folder in self.db.list_folders()? {
            let Some(remote_id) = folder.remote_id else {
                continue;
            };
            if let Some(remote) = remotes.iter().find(|item| item.id == remote_id) {
                self.apply_remote_lab_context(folder.id, remote)?;
            } else if !remote_ids.contains(&remote_id) {
                self.db.set_folder_access_state(folder.id, "denied")?;
            }
        }
        Ok(())
    }

    /// Khi một job nhận 403/404: đối chiếu lại danh sách folder với server ngay (không chờ chu kỳ
    /// poll). Nếu folder của job đúng là đã mất quyền thì trả job về `pending` — tạm dừng, không
    /// đánh lỗi, không đụng tệp local — và trả `true`. 404 của riêng một tệp (folder vẫn còn
    /// quyền) trả `false` để xử lý như lỗi thường. 401 không đi qua đây: đó là phiên/thiết bị.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-work-with-a-mapped-folder
    async fn pause_job_if_access_lost(
        &self,
        job: &JobRow,
        owned: &RunningJob,
        err: &AppError,
    ) -> bool {
        if !matches!(err, AppError::Forbidden(_)) {
            return false;
        }
        {
            // Các job song song cùng gặp 403 chờ nhau ở đây; lần đối chiếu vừa xong thì dùng lại.
            let mut last_refresh = self.access_refresh.lock().await;
            if last_refresh.is_none_or(|at| at.elapsed() >= ACCESS_REFRESH_COALESCE) {
                if let Ok(client) = self.client().await {
                    if let Err(refresh_err) = self.refresh_folder_access(&client).await {
                        tracing::warn!("folder access refresh failed: {refresh_err}");
                    }
                }
                *last_refresh = Some(Instant::now());
            }
        }
        let denied = self
            .db
            .list_folders()
            .map(|folders| {
                folders.iter().any(|folder| {
                    folder.binding() == owned.binding && !Self::folder_sync_allowed(folder)
                })
            })
            .unwrap_or(false);
        if denied {
            let _ = self.db.transition_owned_job(
                owned,
                "pending",
                Some(ACCESS_PAUSED_MESSAGE),
                job.attempt_count,
                None,
                None,
                None,
            );
            tracing::warn!(
                job_id = job.id,
                logical_path = %job.relative_path,
                error_category = "access_denied",
                "folder access lost; job paused, queue preserved"
            );
            self.emit_status();
        }
        denied
    }

    /// Vòng lặp watcher chạy trên thread riêng: dùng watcher gốc của hệ điều hành, tự chuyển
    /// sang polling nếu watcher gốc không khả dụng.
    fn watch_loop(&self) {
        if self.run_native_watcher().is_err() {
            tracing::warn!("native watcher unavailable, switching to polling");
            self.degraded.store(true, Ordering::SeqCst);
            self.emit_status();
            let _ = self.run_poll_watcher();
        }
    }

    /// Chạy watcher gốc của hệ điều hành (inotify/FSEvents/...) cho mọi folder đang bật.
    fn run_native_watcher(&self) -> AppResult<()> {
        let (tx, rx) = std::sync::mpsc::channel();
        let mut watcher = RecommendedWatcher::new(tx, Config::default())
            .map_err(|err| AppError::Message(err.to_string()))?;
        self.watch_folders(&mut watcher, true)?;
        self.consume_events(&mut watcher, rx);
        Ok(())
    }

    /// Chạy watcher kiểu polling (mỗi 5 giây), dùng khi watcher gốc không khả dụng; đánh dấu
    /// engine ở chế độ degraded.
    fn run_poll_watcher(&self) -> AppResult<()> {
        let (tx, rx) = std::sync::mpsc::channel();
        let mut watcher = PollWatcher::new(
            tx,
            Config::default().with_poll_interval(Duration::from_secs(5)),
        )
        .map_err(|err| AppError::Message(err.to_string()))?;
        self.watch_folders(&mut watcher, true)?;
        self.degraded.store(true, Ordering::SeqCst);
        self.emit_status();
        self.consume_events(&mut watcher, rx);
        Ok(())
    }

    /// Đăng ký watch cho mọi folder được phép đồng bộ; `strict` quyết định lỗi watch có làm
    /// dừng hẳn hay chỉ log.
    fn watch_folders<W: Watcher>(&self, watcher: &mut W, strict: bool) -> AppResult<()> {
        for folder in self.db.list_folders()? {
            if Self::folder_sync_allowed(&folder) {
                if let Err(err) =
                    watcher.watch(Path::new(&folder.local_path), RecursiveMode::Recursive)
                {
                    if strict {
                        return Err(AppError::Message(err.to_string()));
                    }
                    tracing::debug!("watch {}: {err}", folder.local_path);
                }
            }
        }
        Ok(())
    }

    /// Vòng lặp chính của watcher: gộp (debounce) sự kiện theo đường dẫn, định kỳ đăng ký lại
    /// watch cho folder mới, rồi xử lý từng đường dẫn đã ổn định.
    fn consume_events<W: Watcher>(
        &self,
        watcher: &mut W,
        rx: std::sync::mpsc::Receiver<Result<notify::Event, notify::Error>>,
    ) {
        let debounce = Duration::from_millis(
            self.db
                .load_settings()
                .unwrap_or_default()
                .debounce_ms
                .clamp(500, 2000),
        );
        let mut pending: HashMap<PathBuf, Instant> = HashMap::new();
        loop {
            match rx.recv_timeout(debounce) {
                Ok(Ok(event)) => {
                    if matches!(
                        event.kind,
                        EventKind::Create(_) | EventKind::Modify(_) | EventKind::Remove(_)
                    ) {
                        for path in event.paths {
                            pending.insert(path, Instant::now());
                        }
                    }
                }
                Ok(Err(err)) => tracing::warn!("watcher error: {err}"),
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                    let _ = self.watch_folders(watcher, false);
                }
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
            }
            let now = Instant::now();
            let ready: Vec<_> = pending
                .iter()
                .filter(|(_, seen)| now.duration_since(**seen) >= debounce)
                .map(|(path, _)| path.clone())
                .collect();
            for path in ready {
                pending.remove(&path);
                if let Err(err) = self.handle_path(&path) {
                    tracing::warn!("failed handling {}: {err}", path.display());
                }
            }
        }
    }

    /// Vòng lặp định kỳ: quét lại toàn bộ folder cục bộ và đối soát danh sách tệp trên server.
    async fn reconcile_loop(&self) {
        loop {
            let secs = self.settings.lock().await.reconcile_secs.clamp(300, 900);
            if let Err(err) = self.reconcile_all().await {
                tracing::warn!("reconciliation failed: {err}");
            }
            if let Err(err) = self.reconcile_folder_files().await {
                tracing::warn!("remote file reconciliation failed: {err}");
            }
            tokio::time::sleep(Duration::from_secs(secs)).await;
        }
    }

    /// Vòng lặp định kỳ hỏi change feed của server; hết phiên thì đánh dấu để dừng poll cho tới
    /// khi đăng nhập lại.
    async fn change_poll_loop(&self) {
        loop {
            let secs = self.settings.lock().await.change_poll_secs.clamp(10, 120);
            if self.session.is_authenticated() {
                if let Err(err) = self.poll_remote_changes().await {
                    tracing::warn!("change poll failed: {err}");
                    if is_odoo_auth_failure(&err) && self.session.mark_expired("change_poll") {
                        self.emit_status();
                    }
                }
            }
            tokio::time::sleep(Duration::from_secs(secs)).await;
        }
    }

    /// Tuần tự hóa một lượt đối soát rồi chạy toàn bộ traversal/hash trên blocking pool.
    #[tracing::instrument(level = "debug", name = "sync.reconcile_all", skip_all)]
    pub async fn reconcile_all(&self) -> AppResult<()> {
        let engine = self.clone();
        let changed = run_serialized_blocking(self.reconcile_gate.clone(), move || {
            engine.reconcile_all_blocking()
        })
        .await?;
        if changed {
            self.emit_files_changed();
        }
        self.emit_status();
        Ok(())
    }

    /// Quét đồng bộ mọi folder; chỉ được gọi từ blocking pool hoặc thread watcher chuyên dụng.
    fn reconcile_all_blocking(&self) -> AppResult<bool> {
        reconcile_folders(&self.db, self.db.list_folders()?)
    }

    /// Xử lý một sự kiện watcher cho một đường dẫn cụ thể: tìm folder chứa nó, kiểm rule, rồi
    /// xếp hàng nếu có thay đổi thật.
    fn handle_path(&self, path: &Path) -> AppResult<()> {
        if !path.is_file() {
            return Ok(());
        }
        for folder in self.db.list_folders()? {
            if !Self::folder_sync_allowed(&folder) {
                continue;
            }
            let root = PathBuf::from(&folder.local_path);
            if let Some(rel) = relative_path(&root, path) {
                let rules = self.db.folder_rules(folder.id)?;
                if matches_rules(&rel, folder.recursive, &rules) {
                    if enqueue_if_changed(&self.db, &folder, path, &rel)? {
                        self.emit_files_changed();
                    }
                    self.emit_status();
                }
            }
        }
        Ok(())
    }

    /// Vòng lặp dispatcher: khi không tạm dừng và còn phiên đăng nhập, claim job cho mọi slot
    /// trống (upload/download có slot riêng, mỗi tệp tối đa một transfer) và chạy song song; chờ
    /// tới khi một transfer xong hoặc 750 ms rồi lặp lại.
    ///
    /// Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#concurrent-transfers
    async fn dispatch_loop(&self) {
        let engine = self.clone();
        // Setting concurrency ẩn áp dụng khi dispatcher khởi động (khởi động app).
        let (limits, part_concurrency) = {
            let settings = self.settings.lock().await;
            (
                TransferLimits::from_settings(&settings),
                clamp_concurrency(settings.part_concurrency),
            )
        };
        self.part_concurrency
            .store(part_concurrency, Ordering::SeqCst);
        tracing::info!(
            uploads = limits.uploads,
            downloads = limits.downloads,
            part_concurrency,
            part_budget_mib = self.part_budget.total_mib(),
            "transfer dispatcher started"
        );
        let mut dispatcher = Dispatcher::new(self.db.clone(), limits, move |job: JobRow| {
            let engine = engine.clone();
            async move { engine.process_transfer(job).await }
        });
        loop {
            dispatcher.reap();
            if !self.paused.load(Ordering::SeqCst) && self.session.is_authenticated() {
                match dispatcher.fill_slots().await {
                    Ok(started) if started > 0 => self.emit_status(),
                    Ok(_) => {}
                    Err(err) => tracing::warn!("claiming sync jobs failed: {err}"),
                }
            }
            dispatcher.wait(Duration::from_millis(750)).await;
        }
    }

    /// Chạy một job đã claim theo loại của nó rồi báo trạng thái mới cho frontend. Danh tính của
    /// job (`RunningJob`) được chụp MỘT lần ở đây; mọi lượt ghi bền sau đó, kể cả chốt lỗi/tạm
    /// dừng, phải chứng minh task vẫn sở hữu đúng job/tệp/binding này.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    async fn process_transfer(&self, job: JobRow) {
        match self.db.running_job(&job) {
            Ok(Some(owned)) if job.operation == "download" => {
                self.process_download_job(job, owned).await
            }
            Ok(Some(owned)) => self.process_job(job, owned).await,
            Ok(None) => log_superseded(&job, "before start"),
            // Job giữ `running` tới lần khởi động sau (`recover_jobs`): không ghi theo id trơn.
            Err(err) => tracing::warn!(
                job_id = job.id,
                "could not capture running job identity: {err}"
            ),
        }
        self.emit_status();
    }

    /// Chạy một job tải lên; hết phiên thì dừng worker và giữ nguyên hàng đợi, lỗi khác thì phân
    /// loại đáng-thử-lại hay thất bại hẳn.
    #[tracing::instrument(
        level = "debug",
        name = "sync.process_upload_job",
        skip_all,
        fields(job_id = job.id, folder_id = job.folder_id, attempt = job.attempt_count)
    )]
    async fn process_job(&self, job: JobRow, owned: RunningJob) {
        tracing::info!(
            job_id = job.id,
            logical_path = %job.relative_path,
            attempt = job.attempt_count,
            state = "running",
            "sync job started"
        );
        if let Err(err) = self.upload_job(&job, &owned).await {
            if matches!(err, AppError::Superseded) {
                log_superseded(&job, "upload");
                return;
            }
            if matches!(err, AppError::Paused) {
                self.requeue_paused_job(&job, &owned);
                return;
            }
            if is_odoo_auth_failure(&err) {
                self.session.mark_expired("sync_job");
                let _ = self.db.transition_owned_job(
                    &owned,
                    "pending",
                    Some("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."),
                    job.attempt_count,
                    None,
                    None,
                    None,
                );
                tracing::warn!(
                    job_id = job.id,
                    logical_path = %job.relative_path,
                    error_category = "unauthenticated",
                    "auth expired; pausing worker and preserving queue"
                );
                let _ = self.app.emit(
                    "sync-error",
                    serde_json::json!({
                        "jobId": job.id,
                        "path": job.relative_path,
                        "message": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
                        "category": "unauthenticated",
                    }),
                );
                self.emit_status();
                return;
            }
            if self.pause_job_if_access_lost(&job, &owned, &err).await {
                return;
            }
            let attempt = job.attempt_count + 1;
            let retryable = is_retryable(&err) || err.to_string().contains("409");
            let decision = match record_job_failure(&self.db, &job, &owned, &err) {
                Ok(Some(decision)) => decision,
                Ok(None) => return log_superseded(&job, "upload failure"),
                Err(db_err) => {
                    tracing::warn!(job_id = job.id, "could not record upload failure: {db_err}");
                    return;
                }
            };
            tracing::warn!(
                job_id = job.id,
                logical_path = %job.relative_path,
                attempt,
                error_category = if !retryable {
                    "fatal"
                } else if is_connectivity_error(&err) {
                    "connectivity"
                } else {
                    "server"
                },
                next_status = decision.status,
                error = %decision.message,
                "sync job failed"
            );
            let redacted = decision.message;
            let _ = self.app.emit(
                "sync-error",
                serde_json::json!({
                    "jobId": job.id,
                    "path": job.relative_path,
                    "message": redacted,
                }),
            );
        }
    }

    /// Đưa job dừng ở điểm an toàn (tạm dừng hoặc folder vừa mất quyền) về `pending` mà không
    /// tăng số lần thử. Etag các part đã upload và tệp tạm download được giữ nên lần sau tiếp tục
    /// từ chỗ dừng.
    fn requeue_paused_job(&self, job: &JobRow, owned: &RunningJob) {
        match settle_stopped_job(&self.db, job, owned, ACCESS_PAUSED_MESSAGE) {
            Ok(stopped) => tracing::info!(
                job_id = job.id,
                file_id = job.file_id,
                logical_path = %job.relative_path,
                operation = %job.operation,
                stopped_as = ?stopped,
                "sync job stopped at a safe point; progress kept for resume"
            ),
            Err(err) => tracing::warn!(job_id = job.id, "could not requeue stopped job: {err}"),
        }
        self.emit_status();
    }

    /// Điểm dừng an toàn cho transfer của `job`: tạm dừng, hoặc folder của nó vừa mất quyền.
    fn stop_probe(&self, job: &JobRow) -> StopProbe {
        StopProbe::new(
            self.db.clone(),
            self.paused.clone(),
            job.folder_id,
            ACCESS_CHECK_INTERVAL,
        )
    }

    /// Dựng `ApiClient` từ API key ĐANG GIỮ TRONG BỘ NHỚ và device id đã lưu. Không đọc keyring:
    /// hàm này chạy cho mọi job/poll. Chưa có key → `NotLoggedIn` (lỗi cục bộ, không phải 401).
    pub async fn client(&self) -> AppResult<ApiClient> {
        let key = self.session.api_key().ok_or(AppError::NotLoggedIn)?;
        let settings = self.settings.lock().await.clone();
        let device_id = self
            .db
            .meta_get("device_id")?
            .and_then(|value| value.parse().ok())
            .ok_or(AppError::NotLoggedIn)?;
        ApiClient::new(&settings.odoo_url, &key, device_id)
    }

    /// Tải lên một tệp qua `run_upload_job` rồi báo frontend (tiến độ, xung đột, danh sách tệp).
    /// Tệp cục bộ đổi sau khi byte đã được đọc để upload thì xếp hàng ngay version kế tiếp thay
    /// vì chờ chu kỳ đối soát.
    ///
    /// Luật integrity: applications/laboratory-file-sync-application/docs/contract.md#direct-minio-upload
    #[tracing::instrument(
        level = "debug",
        name = "sync.upload_job",
        skip_all,
        fields(job_id = job.id, folder_id = job.folder_id)
    )]
    async fn upload_job(&self, job: &JobRow, owned: &RunningJob) -> AppResult<()> {
        let client = self.client().await?;
        let probe = self.stop_probe(job);
        let options = UploadOptions {
            part_concurrency: self.part_concurrency.load(Ordering::SeqCst),
            budget: self.part_budget.clone(),
        };
        let report = run_upload_job_with(
            &client,
            &self.db,
            job,
            owned,
            &options,
            |done, total| {
                let _ = self.app.emit(
                    "upload-progress",
                    ProgressDeltaDto {
                        job_id: job.id,
                        done,
                        total,
                    },
                );
            },
            || probe.should_stop(),
            |_| {},
        )
        .await?;
        tracing::info!(
            job_id = job.id,
            logical_path = %job.relative_path,
            content_hash = %report.content_hash,
            parts_uploaded = report.parts_uploaded,
            total_parts = report.total_parts,
            part_concurrency = options.part_concurrency,
            part_budget_peak_mib = options.budget.peak_mib(),
            local_changed_after_read = report.local_changed_after_read,
            "upload job finished"
        );
        if let UploadOutcome::Finalized(finalized) = &report.outcome {
            if finalized.status == "conflict" {
                let _ = self.app.emit(
                    "conflict-created",
                    serde_json::json!({
                        "jobId": job.id,
                        "path": job.relative_path,
                        "conflictId": finalized.conflict_id,
                        "serverVersionId": finalized.server_version_id,
                    }),
                );
            }
        }
        self.emit_files_changed();
        if report.local_changed_after_read {
            self.requeue_changed_upload(job, owned).await;
        }
        Ok(())
    }

    /// Xếp hàng upload kế tiếp cho một tệp vừa đổi sau khi lượt upload trước đã đọc xong byte:
    /// hash lại nội dung hiện tại qua đúng đường `enqueue_if_changed` của watcher.
    async fn requeue_changed_upload(&self, job: &JobRow, owned: &RunningJob) {
        let engine = self.clone();
        let (binding, relative) = (owned.binding.clone(), owned.relative_path.clone());
        let result = run_blocking(move || {
            // Chỉ binding đã chụp lúc upload bắt đầu; binding mới trùng rowid tự quét tệp của nó.
            let Some(folder) = engine
                .db
                .list_folders()?
                .into_iter()
                .find(|folder| folder.binding() == binding)
            else {
                return Ok(false);
            };
            let path = PathBuf::from(&folder.local_path).join(&relative);
            enqueue_if_changed(&engine.db, &folder, &path, &relative)
        })
        .await;
        match result {
            Ok(true) => {
                tracing::info!(
                    job_id = job.id,
                    logical_path = %job.relative_path,
                    "local file changed after upload read; next version queued"
                );
                self.emit_status();
            }
            Ok(false) => {}
            Err(err) => tracing::warn!(
                job_id = job.id,
                logical_path = %job.relative_path,
                "could not requeue changed file: {err}"
            ),
        }
    }

    /// Chạy một job tải xuống; hết phiên thì dừng worker và giữ nguyên hàng đợi, lỗi khác thì
    /// phân loại đáng-thử-lại hay thất bại hẳn.
    #[tracing::instrument(
        level = "debug",
        name = "sync.process_download_job",
        skip_all,
        fields(job_id = job.id, folder_id = job.folder_id, attempt = job.attempt_count)
    )]
    async fn process_download_job(&self, job: JobRow, owned: RunningJob) {
        tracing::info!(
            job_id = job.id,
            logical_path = %job.relative_path,
            attempt = job.attempt_count,
            operation = "download",
            state = "running",
            "sync job started"
        );
        if let Err(err) = self.download_job(&job, &owned).await {
            if matches!(err, AppError::Superseded) {
                log_superseded(&job, "download");
                return;
            }
            if matches!(err, AppError::Paused) {
                self.requeue_paused_job(&job, &owned);
                return;
            }
            if is_odoo_auth_failure(&err) {
                self.session.mark_expired("sync_job");
                let _ = self.db.transition_owned_job(
                    &owned,
                    "pending",
                    Some("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."),
                    job.attempt_count,
                    None,
                    None,
                    None,
                );
                tracing::warn!(
                    job_id = job.id,
                    logical_path = %job.relative_path,
                    error_category = "unauthenticated",
                    "auth expired; pausing download worker and preserving queue"
                );
                self.emit_status();
                return;
            }
            if self.pause_job_if_access_lost(&job, &owned, &err).await {
                return;
            }
            let attempt = job.attempt_count + 1;
            let retryable = is_retryable(&err);
            let decision = match record_job_failure(&self.db, &job, &owned, &err) {
                Ok(Some(decision)) => decision,
                Ok(None) => return log_superseded(&job, "download failure"),
                Err(db_err) => {
                    tracing::warn!(
                        job_id = job.id,
                        "could not record download failure: {db_err}"
                    );
                    return;
                }
            };
            tracing::warn!(
                job_id = job.id,
                logical_path = %job.relative_path,
                attempt,
                error_category = if !retryable {
                    "fatal"
                } else if is_connectivity_error(&err) {
                    "connectivity"
                } else {
                    "server"
                },
                next_status = decision.status,
                error = %decision.message,
                "download job failed"
            );
            let redacted = decision.message;
            let _ = self.app.emit(
                "sync-error",
                serde_json::json!({
                    "jobId": job.id,
                    "path": job.relative_path,
                    "message": redacted,
                }),
            );
        }
    }

    /// Chạy một job tải xuống bằng client của phiên hiện tại và báo tiến độ cho frontend.
    #[tracing::instrument(
        level = "debug",
        name = "sync.download_job",
        skip_all,
        fields(job_id = job.id, folder_id = job.folder_id)
    )]
    async fn download_job(&self, job: &JobRow, owned: &RunningJob) -> AppResult<()> {
        let client = self.client().await?;
        let probe = self.stop_probe(job);
        run_download_job_with(
            &client,
            &self.db,
            job,
            owned,
            |done, total, _version_number| {
                let _ = self.app.emit(
                    "download-progress",
                    ProgressDeltaDto {
                        job_id: job.id,
                        done,
                        total,
                    },
                );
            },
            || probe.should_stop(),
            |_| {},
        )
        .await?;
        self.emit_files_changed();
        Ok(())
    }

    /// Hỏi change feed của mọi folder được phép đồng bộ, áp từng thay đổi, và cập nhật cursor
    /// đã xử lý; một folder mất quyền giữa chừng bị đánh dấu `denied` và bỏ qua phần còn lại.
    #[tracing::instrument(level = "debug", name = "sync.poll_remote_changes", skip_all)]
    pub async fn poll_remote_changes(&self) -> AppResult<()> {
        // Chưa có key cục bộ thì chỉ bỏ qua — KHÔNG đánh dấu hết hạn; chỉ 401 của Odoo mới làm thế.
        if !self.session.is_authenticated() {
            return Ok(());
        }
        let client = match self.client().await {
            Ok(client) => client,
            Err(AppError::NotLoggedIn) => return Ok(()),
            Err(err) => return Err(err),
        };
        if let Err(err) = self.refresh_folder_access(&client).await {
            tracing::warn!("folder access refresh failed: {err}");
        }
        // Folder vừa gắn mà chưa hydrate xong (ví dụ lúc gắn đang mất mạng) được thử lại ở đây.
        self.hydrate_pending_folders().await;
        let mut changes_applied = false;
        for folder in self.db.list_folders()? {
            if !Self::folder_sync_allowed(&folder) {
                continue;
            }
            let Some(remote_id) = folder.remote_id else {
                continue;
            };
            let mut after = self.db.change_cursor(remote_id)?;
            loop {
                let page = match client.folder_changes(remote_id, after, 50).await {
                    Ok(page) => page,
                    Err(AppError::Forbidden(_)) => {
                        let _ = self.db.set_folder_access_state(folder.id, "denied");
                        break;
                    }
                    Err(err) => return Err(err),
                };
                for change in page.changes {
                    self.apply_remote_change(&folder, &change).await?;
                    self.db.set_change_cursor(remote_id, change.id)?;
                    changes_applied = true;
                    tracing::info!(
                        cursor = change.id,
                        file_id = change.file_id,
                        version_id = ?change.current_version_id,
                        "processed remote change"
                    );
                }
                if !page.has_more {
                    break;
                }
                after = page.next_cursor;
            }
        }
        if changes_applied {
            self.emit_files_changed();
        }
        self.emit_status();
        Ok(())
    }

    /// Đối soát toàn bộ danh sách tệp trên server cho mọi folder được phép đồng bộ, coi mỗi tệp
    /// như một thay đổi để đảm bảo nhất quán kể cả khi bỏ lỡ change feed.
    #[tracing::instrument(level = "debug", name = "sync.reconcile_remote_files", skip_all)]
    async fn reconcile_folder_files(&self) -> AppResult<()> {
        if !self.session.is_authenticated() {
            return Ok(());
        }
        let client = match self.client().await {
            Ok(client) => client,
            Err(AppError::NotLoggedIn) => return Ok(()),
            Err(err) => return Err(err),
        };
        let mut changes_found = false;
        for folder in self.db.list_folders()? {
            if !Self::folder_sync_allowed(&folder) || folder.remote_id.is_none() {
                continue;
            }
            let summary = hydrate_folder(&client, &self.db, &folder).await?;
            if summary.remote_files > 0 || summary.downloads_queued > 0 || summary.conflicts > 0 {
                changes_found = true;
            }
            self.report_conflicts(&summary);
            self.db.set_needs_hydration(folder.id, false)?;
        }
        if changes_found {
            self.emit_files_changed();
        }
        Ok(())
    }

    /// Hydrate ngay các folder vừa được gắn (cờ bền `needs_hydration`): lấy trạng thái hiện tại của
    /// folder trên server và xếp hàng tải xuống những tệp còn thiếu/cũ, không chờ chu kỳ đối soát
    /// hay poll. Lỗi mạng/server giữ nguyên binding và cờ để lượt poll kế tiếp thử lại; mất quyền
    /// thì đánh dấu `denied` như thường. Không bao giờ gỡ binding.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#what-a-file-belongs-to
    #[tracing::instrument(level = "debug", name = "sync.hydrate_pending_folders", skip_all)]
    pub async fn hydrate_pending_folders(&self) {
        let Ok(folders) = self.db.list_folders() else {
            return;
        };
        let pending: Vec<FolderRow> = folders
            .into_iter()
            .filter(|folder| {
                Self::folder_sync_allowed(folder)
                    && folder.remote_id.is_some()
                    && self.db.needs_hydration(folder.id).unwrap_or(false)
            })
            .collect();
        if pending.is_empty() {
            return;
        }
        let Ok(client) = self.client().await else {
            return;
        };
        let mut hydrated_any = false;
        for folder in pending {
            match hydrate_folder(&client, &self.db, &folder).await {
                Ok(summary) => {
                    tracing::info!(
                        folder_id = folder.id,
                        remote_files = summary.remote_files,
                        downloads_queued = summary.downloads_queued,
                        conflicts = summary.conflicts,
                        failed_items = summary.failed_items,
                        "initial hydration finished"
                    );
                    if summary.remote_files > 0
                        || summary.downloads_queued > 0
                        || summary.conflicts > 0
                    {
                        hydrated_any = true;
                    }
                    self.report_conflicts(&summary);
                    if summary.failed_items == 0 {
                        let _ = self.db.set_needs_hydration(folder.id, false);
                    }
                }
                Err(AppError::Forbidden(_)) => {
                    let _ = self.db.set_folder_access_state(folder.id, "denied");
                }
                Err(err) => {
                    if is_odoo_auth_failure(&err) {
                        self.session.mark_expired("hydration");
                    }
                    tracing::warn!(
                        folder_id = folder.id,
                        "initial hydration failed; binding kept, will retry on next poll: {err}"
                    );
                }
            }
        }
        if hydrated_any {
            self.emit_files_changed();
        }
        self.emit_status();
    }

    /// Báo frontend làm mới khi một lượt hydrate/đối soát phát sinh xung đột.
    fn report_conflicts(&self, summary: &HydrationSummary) {
        if summary.conflicts > 0 {
            let _ = self.app.emit(
                "conflict-created",
                serde_json::json!({ "count": summary.conflicts }),
            );
        }
    }

    /// Áp một thay đổi từ server (xem `plan_remote_change`) và báo frontend nếu phát sinh xung đột.
    async fn apply_remote_change(
        &self,
        folder: &FolderRow,
        change: &FolderChangeDto,
    ) -> AppResult<()> {
        if let RemoteOutcome::Conflict { base } =
            plan_remote_change(&self.db, folder, change).await?
        {
            let _ = self.app.emit(
                "conflict-created",
                serde_json::json!({
                    "path": change.logical_path,
                    "serverVersionId": change.current_version_id,
                    "baseHash": base,
                }),
            );
        }
        Ok(())
    }

    /// Xử lý xung đột — chọn giữ bản server: sao lưu bản cục bộ (giữ cả hai), xóa cờ xung đột,
    /// rồi xếp hàng tải xuống bản server.
    pub fn accept_server_version(&self, file_id: i64) -> AppResult<()> {
        let device = self
            .db
            .meta_get("user_login")?
            .unwrap_or_else(|| "desktop".into());
        accept_server_version_in(&self.db, file_id, &device, || {})?;
        self.emit_files_changed();
        Ok(())
    }

    /// Xử lý xung đột — chọn giữ bản cục bộ: chỉ xóa cờ xung đột, không đụng tới tệp trên đĩa.
    pub fn keep_local_conflict(&self, file_id: i64) -> AppResult<()> {
        self.db
            .file_by_id(file_id)?
            .ok_or(AppError::FolderNotFound)?;
        self.db.dismiss_file_conflict(file_id)?;
        self.emit_files_changed();
        Ok(())
    }

    /// Xóa tệp tạm tải xuống mồ côi (không còn job đang chờ/chạy tương ứng) từ lần chạy trước.
    fn cleanup_stale_temps(&self) -> AppResult<()> {
        for folder in self.db.list_folders()? {
            let root = PathBuf::from(&folder.local_path);
            let active: HashSet<PathBuf> = self
                .db
                .list_download_temps(folder.id)?
                .into_iter()
                .map(|(job_id, rel)| download_temp_path(&root.join(rel), job_id))
                .collect();
            for path in walk(&root, folder.recursive) {
                let name = path
                    .file_name()
                    .and_then(|value| value.to_str())
                    .unwrap_or_default();
                if name.contains(".medilab-download-")
                    && name.ends_with(".tmp")
                    && !active.contains(&path)
                {
                    let _ = fs::remove_file(path);
                }
            }
        }
        Ok(())
    }
}

/// Quét mọi folder trong `folders` (danh sách đã đọc trước), bỏ qua folder không được đồng bộ.
#[tracing::instrument(level = "debug", name = "sync.reconcile_all_blocking", skip_all)]
pub(crate) fn reconcile_folders(db: &Db, folders: Vec<FolderRow>) -> AppResult<bool> {
    let mut changed = false;
    for folder in folders {
        if EngineHandle::folder_sync_allowed(&folder) && scan_folder(db, &folder)? {
            changed = true;
        }
    }
    Ok(changed)
}

/// Duyệt toàn bộ tệp của một folder, xếp hàng những tệp khớp rule và có thay đổi.
#[tracing::instrument(
    level = "debug",
    name = "sync.scan_folder",
    skip_all,
    fields(folder_id = folder.id)
)]
pub(crate) fn scan_folder(db: &Db, folder: &FolderRow) -> AppResult<bool> {
    let mut enqueued = false;
    let root = PathBuf::from(&folder.local_path);
    let rules = db.folder_rules(folder.id)?;
    for path in walk(&root, folder.recursive) {
        if let Some(rel) = relative_path(&root, &path) {
            if matches_rules(&rel, folder.recursive, &rules)
                && enqueue_if_changed(db, folder, &path, &rel)?
            {
                enqueued = true;
            }
        }
    }
    Ok(enqueued)
}

/// Xếp hàng tải lên nếu tệp thật sự thay đổi: bỏ qua tệp nội bộ/không ổn định/đang xung đột,
/// và bỏ qua sự kiện tự vọng lại của một lượt tải xuống vừa xong.
#[tracing::instrument(
    level = "debug",
    name = "sync.enqueue_if_changed",
    skip_all,
    fields(folder_id, byte_count = tracing::field::Empty)
)]
pub(crate) fn enqueue_if_changed(
    db: &Db,
    folder: &FolderRow,
    path: &Path,
    rel: &str,
) -> AppResult<bool> {
    let folder_id = folder.id;
    if is_internal_path(rel) {
        return Ok(false);
    }
    if !is_stable(path, STABLE_WAIT) {
        return Ok(false);
    }
    let size = fs::metadata(path)?.len() as i64;
    tracing::Span::current().record("byte_count", size);
    let mtime = unix_mtime(path);
    let digest = sha256_file(path)?;
    let mapped = db.file_by_path(folder_id, rel)?;
    if db.file_status(folder_id, rel)?.as_deref() == Some("conflict") {
        return Ok(false);
    }
    if should_skip_enqueue(
        mapped
            .as_ref()
            .and_then(|row| row.last_synced_hash.as_deref())
            .or(db.file_sha(folder_id, rel)?.as_deref()),
        &digest,
        mapped.as_ref().map(|row| row.status.as_str()),
        mapped.as_ref().and_then(|row| row.suppress_hash.as_deref()),
    ) {
        return Ok(false);
    }
    // Ghi nguyên tử và chỉ khi folder còn gắn đúng đường dẫn này: thư mục có thể bị gỡ trong lúc
    // tệp đang được hash ở trên.
    let recorded = db.record_local_change(&folder.binding(), rel, size, mtime, &digest)?;
    if recorded.is_none() {
        tracing::info!(
            folder_id,
            logical_path = %rel,
            "folder unbound during scan; local change skipped"
        );
        return Ok(false);
    }
    Ok(true)
}

/// Xử lý xung đột — giữ bản server cho tệp `file_id`: sao lưu bản cục bộ (giữ cả hai bản), xóa
/// cờ xung đột, rồi xếp hàng tải xuống bản server. `before_write` chạy ngay trước bước ghi DB
/// (hook cho test chèn đúng khe race).
pub(crate) fn accept_server_version_in(
    db: &Db,
    file_id: i64,
    device_label: &str,
    before_write: impl FnOnce(),
) -> AppResult<()> {
    // Đọc tệp CÙNG binding của nó trong một truy vấn: đường dẫn sao lưu và bước kiểm lại trước khi
    // ghi dùng đúng binding lúc đọc, không phải folder đang mang id đó về sau.
    let (mapped, binding) = db
        .file_with_binding(file_id)?
        .ok_or(AppError::FolderNotFound)?;
    let remote_file_id = mapped
        .remote_file_id
        .ok_or_else(|| AppError::Message("Thiếu mã tệp trên máy chủ".into()))?;
    let remote_version_id = mapped.remote_version_id.unwrap_or(0);
    let dest = PathBuf::from(&binding.local_path).join(&mapped.relative_path);
    // Sao lưu bản cục bộ trên đĩa nằm ngoài transaction SQLite.
    if dest.is_file() {
        preserve_local_copy(&dest, device_label)?;
    }
    before_write();
    // Xóa cờ + xếp hàng chỉ khi binding còn nguyên và tệp vẫn đúng là tệp đã đọc, trong một
    // transaction dưới cùng mutex với `delete_folder`.
    let written = db.with_bound_file(&binding, file_id, |conn| {
        if !file_row_matches(conn, file_id, &mapped.relative_path, remote_file_id)? {
            return Ok(false);
        }
        clear_file_conflict_on(conn, file_id)?;
        enqueue_download_on(
            conn,
            binding.id,
            file_id,
            &mapped.relative_path,
            0,
            remote_file_id,
            remote_version_id,
            mapped.last_synced_hash.as_deref().unwrap_or(""),
            None,
        )?;
        Ok(true)
    })?;
    if written != Some(true) {
        tracing::info!(
            folder_id = binding.id,
            file_id,
            logical_path = %mapped.relative_path,
            "folder unbound before accepting the server version; nothing queued"
        );
        return Err(AppError::FolderNotFound);
    }
    Ok(())
}

/// Kết quả áp một thay đổi/tệp trên server vào state cục bộ.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum RemoteOutcome {
    /// Không phải version chuẩn, đường dẫn nội bộ, không khớp rule, hoặc tệp đang xung đột.
    Skipped,
    DownloadQueued,
    BaseAdvanced,
    /// Bản cục bộ mới hơn base và server chưa đổi: để luồng upload xử lý.
    UploadPending,
    Conflict {
        base: Option<String>,
    },
}

/// Áp một thay đổi từ server: bỏ qua nếu không phải version chuẩn/không khớp rule, rồi quyết định
/// tải xuống, chỉ cập nhật base, bỏ qua (đang tải lên), hay đánh dấu xung đột — cùng một logic
/// quyết định cho change feed, đối soát định kỳ và hydrate lúc gắn folder (không có lối tắt ghi
/// đè). Chỉ cần DB + filesystem nên test được không cần app.
pub(crate) async fn plan_remote_change(
    db: &Db,
    folder: &FolderRow,
    change: &FolderChangeDto,
) -> AppResult<RemoteOutcome> {
    if change.change_type != "CANONICAL_VERSION" || is_internal_path(&change.logical_path) {
        return Ok(RemoteOutcome::Skipped);
    }
    let rules = db.folder_rules(folder.id)?;
    if !matches_rules(&change.logical_path, folder.recursive, &rules) {
        return Ok(RemoteOutcome::Skipped);
    }
    let remote_hash = change.content_hash.clone().unwrap_or_default();
    let Some(version_id) = change.current_version_id else {
        return Ok(RemoteOutcome::Skipped);
    };
    if remote_hash.is_empty() {
        return Ok(RemoteOutcome::Skipped);
    }
    // Mọi ghi dưới đây kiểm binding còn nguyên NGAY lúc ghi: danh sách folder đọc từ trước, và
    // giữa các bước có chờ HTTP/hash nên thư mục có thể đã bị gỡ (hoặc gắn lại trùng rowid).
    let binding = folder.binding();
    let Some(file_id) = db.ensure_remote_mapping_bound(
        &binding,
        &change.logical_path,
        change.file_id,
        Some(version_id),
    )?
    else {
        return Ok(skipped_unbound(folder, change));
    };
    let mapped = db.file_by_id(file_id)?;
    if mapped.as_ref().map(|row| row.status.as_str()) == Some("conflict") {
        return Ok(RemoteOutcome::Skipped);
    }
    let dest = PathBuf::from(&folder.local_path).join(&change.logical_path);
    let local_hash = if dest.is_file() {
        let path = dest.clone();
        Some(
            tokio::task::spawn_blocking(move || sha256_file(&path))
                .await
                .map_err(|err| AppError::Message(err.to_string()))??,
        )
    } else {
        None
    };
    let base = mapped.as_ref().and_then(|row| row.last_synced_hash.clone());
    match decide_sync_action(local_hash.as_deref(), base.as_deref(), &remote_hash) {
        SyncAction::Download => {
            let queued = db.with_bound_file(&binding, file_id, |conn| {
                enqueue_download_on(
                    conn,
                    folder.id,
                    file_id,
                    &change.logical_path,
                    change.size,
                    change.file_id,
                    version_id,
                    &remote_hash,
                    change.version_number,
                )
            })?;
            Ok(match queued {
                Some(_) => RemoteOutcome::DownloadQueued,
                None => skipped_unbound(folder, change),
            })
        }
        SyncAction::AdvanceBase => {
            let advanced = db.with_bound_file(&binding, file_id, |conn| {
                apply_remote_base_on(
                    conn,
                    file_id,
                    change.file_id,
                    version_id,
                    &remote_hash,
                    change.size,
                )
            })?;
            Ok(match advanced {
                Some(()) => RemoteOutcome::BaseAdvanced,
                None => skipped_unbound(folder, change),
            })
        }
        SyncAction::Upload => Ok(RemoteOutcome::UploadPending),
        SyncAction::Conflict => {
            let marked = db.with_bound_file(&binding, file_id, |conn| {
                cancel_active_uploads_on(conn, file_id)?;
                mark_file_conflict_on(
                    conn,
                    file_id,
                    Some(change.file_id),
                    Some(version_id),
                    "Xung đột: tệp cục bộ và máy chủ cùng thay đổi",
                )
            })?;
            Ok(match marked {
                Some(()) => RemoteOutcome::Conflict { base },
                None => skipped_unbound(folder, change),
            })
        }
    }
}

/// Log và trả `Skipped` khi binding của `folder` đã đổi giữa lúc đọc và lúc ghi (thư mục bị gỡ).
fn skipped_unbound(folder: &FolderRow, change: &FolderChangeDto) -> RemoteOutcome {
    tracing::info!(
        folder_id = folder.id,
        remote_folder_id = ?folder.remote_id,
        file_id = change.file_id,
        logical_path = %change.logical_path,
        "folder unbound during remote change; mapping skipped"
    );
    RemoteOutcome::Skipped
}

/// Số liệu một lượt hydrate/đối soát trạng thái hiện tại của một folder trên server.
#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct HydrationSummary {
    pub remote_files: usize,
    pub downloads_queued: usize,
    pub conflicts: usize,
    pub failed_items: usize,
}

/// Hydrate một folder cục bộ từ TRẠNG THÁI HIỆN TẠI của folder trên server — nguồn là
/// `GET /folders/{id}/files`, không phải change feed: folder có thể chứa tệp tạo từ rất lâu trước
/// khi máy này gắn nó, và cursor change feed lưu theo remote id nên sống sót qua "Ngừng đồng bộ"
/// → gắn lại (feed khi đó không còn gì "mới" để trả về).
///
/// Thứ tự an toàn và idempotent: (1) tua change feed tới đầu H mà KHÔNG áp dụng; (2) liệt kê rồi áp
/// từng tệp hiện tại qua `plan_remote_change` (trạng thái liệt kê ≥ H); (3) lưu cursor = H. Thay đổi
/// sau H đi tiếp qua poll thường; không phát lại lịch sử cũ (phát lại version cũ sẽ tải lùi tệp).
/// Một tệp lỗi không chặn các tệp khác.
#[tracing::instrument(
    level = "debug",
    name = "sync.hydrate_folder",
    skip_all,
    fields(folder_id = folder.id, remote_id = ?folder.remote_id)
)]
pub(crate) async fn hydrate_folder(
    client: &ApiClient,
    db: &Db,
    folder: &FolderRow,
) -> AppResult<HydrationSummary> {
    let Some(remote_id) = folder.remote_id else {
        return Ok(HydrationSummary::default());
    };
    let mut head = db.change_cursor(remote_id)?;
    loop {
        let page = client.folder_changes(remote_id, head, 100).await?;
        if let Some(last) = page.changes.last() {
            head = head.max(last.id);
        }
        if !page.has_more || page.changes.is_empty() {
            break;
        }
    }
    let mut summary = HydrationSummary::default();
    let mut offset = 0_i64;
    loop {
        let page = client.folder_files(remote_id, 50, offset).await?;
        for item in &page.items {
            let Some(current) = &item.current_version else {
                continue;
            };
            summary.remote_files += 1;
            let change = FolderChangeDto {
                id: 0,
                change_type: "CANONICAL_VERSION".into(),
                folder_id: item.folder_id,
                file_id: item.id,
                logical_path: item.logical_path.clone(),
                current_version_id: Some(current.id),
                version_number: Some(current.version_number),
                content_hash: Some(current.content_hash.clone()),
                size: current.size,
                source: Some(current.source.clone()),
                changed_at: None,
                changed_by_device_id: None,
            };
            match plan_remote_change(db, folder, &change).await {
                Ok(RemoteOutcome::DownloadQueued) => summary.downloads_queued += 1,
                Ok(RemoteOutcome::Conflict { .. }) => summary.conflicts += 1,
                Ok(_) => {}
                Err(err) => {
                    summary.failed_items += 1;
                    tracing::warn!(
                        folder_id = folder.id,
                        logical_path = %item.logical_path,
                        "hydration skipped one file: {err}"
                    );
                }
            }
        }
        offset += page.items.len() as i64;
        if offset >= page.total || page.items.is_empty() {
            break;
        }
    }
    db.set_change_cursor(remote_id, head)?;
    Ok(summary)
}

/// Số part tối thiểu mỗi lần presign (cửa sổ lớn hơn thì theo cửa sổ): giữ số request presign
/// tới Odoo như trước, không presign trước vô hạn.
const PRESIGN_BATCH: usize = 4;

/// Chu kỳ hỏi `is_paused` trong lúc một PUT part đang chạy.
const PAUSE_POLL_INTERVAL: Duration = Duration::from_millis(250);

/// Chạy `transfer` tới khi xong, nhưng hủy nó (drop future, tức hủy request HTTP) và trả
/// `AppError::Paused` nếu `is_paused()` bật trong lúc chờ; hỏi mỗi `PAUSE_POLL_INTERVAL`.
pub(crate) async fn unless_paused<T>(
    transfer: impl std::future::Future<Output = AppResult<T>>,
    is_paused: &impl Fn() -> bool,
) -> AppResult<T> {
    tokio::pin!(transfer);
    let mut ticker = tokio::time::interval(PAUSE_POLL_INTERVAL);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        tokio::select! {
            result = &mut transfer => return result,
            _ = ticker.tick() => {
                if is_paused() {
                    return Err(AppError::Paused);
                }
            }
        }
    }
}

/// PUT một part lên URL presigned và trả `(part, etag, byte)`, giữ `permit` ngân sách tới khi
/// xong hoặc bị drop. Storage từ chối URL (thường vì hết hạn) thì xin URL mới cho ĐÚNG part này
/// và gửi lại cùng buffer đã hash, một lần; lỗi lần hai để retry của job xử lý. Future này không
/// ghi state của job — task sở hữu job ghi ETag.
#[allow(clippy::too_many_arguments)]
async fn put_part_with_refresh(
    client: ApiClient,
    session_id: i64,
    part_number: i64,
    url: String,
    bytes: bytes::Bytes,
    permit: PartPermit,
    len: i64,
    span: tracing::Span,
) -> AppResult<(i64, String, i64)> {
    let _permit = permit;
    let etag = match ApiClient::put_part(&url, bytes.clone())
        .instrument(span.clone())
        .await
    {
        Err(AppError::PresignedUrlRejected(status)) => {
            tracing::warn!(
                upload_session_id = session_id,
                part_number,
                status,
                "presigned part URL rejected; presigning again"
            );
            let fresh_url = client
                .presign(session_id, &[part_number])
                .await?
                .into_iter()
                .find(|part| part.part_number == part_number)
                .map(|part| part.url)
                .ok_or_else(|| {
                    AppError::Message(format!("Thiếu URL presigned cho phần {part_number}"))
                })?;
            ApiClient::put_part(&fresh_url, bytes)
                .instrument(span)
                .await?
        }
        other => other?,
    };
    tracing::info!(upload_session_id = session_id, part_number, "part uploaded");
    Ok((part_number, etag, len))
}

/// Gộp kết quả join của một task PUT: task panic/bị hủy thành lỗi thường của job.
fn flatten_part_result(
    result: Result<AppResult<(i64, String, i64)>, tokio::task::JoinError>,
) -> AppResult<(i64, String, i64)> {
    result.map_err(|err| AppError::Message(format!("Tác vụ tải phần thất bại: {err}")))?
}

/// Ghi tiến độ và toàn bộ ETag đã có (theo thứ tự part) của session multipart, trên blocking
/// pool: nhiều transfer song song cùng tranh mutex SQLite, không được chặn executor.
#[allow(clippy::too_many_arguments)]
async fn persist_upload_progress(
    db: &Db,
    owned: &RunningJob,
    session_id: i64,
    completed: &BTreeMap<i64, String>,
    expected: &str,
    part_size: i64,
    done: i64,
) -> AppResult<()> {
    let serialized = serde_json::to_string(&completed.iter().collect::<Vec<_>>())?;
    let (db, owned, expected) = (db.clone(), owned.clone(), expected.to_string());
    run_blocking(move || {
        // Session/ETag chỉ được lưu vào đúng job task đang sở hữu (không vào job trùng rowid).
        db.with_running_job(&owned, |conn| {
            set_progress_on(conn, owned.job_id, done)?;
            save_job_session_on(
                conn,
                owned.job_id,
                session_id,
                &serialized,
                &expected,
                Some(part_size),
            )
        })?
        .ok_or(AppError::Superseded)
    })
    .await
}

/// Kết quả phía server của một lượt upload đã hoàn tất.
#[derive(Debug)]
pub(crate) enum UploadOutcome {
    /// Server đã có đúng nội dung này làm version hiện tại; không truyền byte nào.
    Deduplicated,
    /// Server đã finalize: version mới, hoặc artifact xung đột (`status == "conflict"`).
    Finalized(crate::api::FinalizeResponse),
}

/// Báo cáo một lượt upload đã hoàn tất.
#[derive(Debug)]
pub(crate) struct UploadReport {
    pub outcome: UploadOutcome,
    /// SHA-256 đã chứng minh cho nội dung được version hóa (bằng expected hash).
    pub content_hash: String,
    /// Số part thực sự PUT trong lượt này, không tính part đã upload ở lượt trước.
    pub parts_uploaded: i64,
    pub total_parts: i64,
    /// Tệp cục bộ đã khác nội dung vừa version hóa: metadata đổi so với lúc bắt đầu, hoặc
    /// watcher đã ghi SHA-256 mới vào `sync_file` trong lúc upload.
    pub local_changed_after_read: bool,
}

/// Metadata của tệp cục bộ tại một thời điểm: kích thước, mtime theo giây (khớp cột
/// `sync_file.mtime`) và mtime độ phân giải đầy đủ để so trong cùng tiến trình.
#[derive(Debug, Clone, PartialEq, Eq)]
struct LocalMetadata {
    size: i64,
    mtime_secs: i64,
    modified: Option<std::time::SystemTime>,
}

/// Đọc metadata hiện tại của tệp.
fn local_metadata(path: &Path) -> AppResult<LocalMetadata> {
    let meta = fs::metadata(path)?;
    let modified = meta.modified().ok();
    let mtime_secs = modified
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    Ok(LocalMetadata {
        size: meta.len() as i64,
        mtime_secs,
        modified,
    })
}

/// True nếu dấu vân tay đã lưu còn dùng được làm expected hash: có SHA-256 và size + mtime
/// (giây) khớp metadata hiện tại. Đây chỉ là điều kiện để khỏi đọc lại tệp, không phải bằng
/// chứng nội dung: byte upload vẫn phải khớp hash này bằng SHA-256 trước finalize.
fn fingerprint_matches(stored: Option<&FileFingerprint>, current: &LocalMetadata) -> bool {
    stored.is_some_and(|fingerprint| {
        fingerprint.sha256.is_some()
            && fingerprint.size == current.size
            && fingerprint.mtime == current.mtime_secs
    })
}

/// Hash lại toàn tệp và lưu làm dấu vân tay mới của tệp `owned`, để lượt thử sau không dùng lại
/// expected hash đã sai. Hash có thể mất nhiều giây: chỉ ghi nếu task vẫn sở hữu job, không thì
/// `AppError::Superseded` (không ghi vào dòng tệp trùng rowid của binding khác).
pub(crate) async fn refresh_file_fingerprint(
    db: &Db,
    owned: &RunningJob,
    path: &Path,
) -> AppResult<String> {
    let meta = local_metadata(path)?;
    let path_for_hash = path.to_path_buf();
    let digest = run_blocking(move || sha256_file(&path_for_hash)).await?;
    db.with_running_job(owned, |conn| {
        set_file_fingerprint_on(conn, owned.file_id, meta.size, meta.mtime_secs, &digest)
    })?
    .ok_or(AppError::Superseded)?;
    Ok(digest)
}

/// Trả `AppError::Superseded` nếu task không còn sở hữu job `owned` (xem `Db::with_running_job`).
fn ensure_owned(db: &Db, owned: &RunningJob) -> AppResult<()> {
    db.with_running_job(owned, |_| Ok(()))?
        .ok_or(AppError::Superseded)
}

/// Chọn expected hash cho lượt upload: dùng lại SHA-256 lúc enqueue khi dấu vân tay còn khớp,
/// ngược lại hash lại toàn tệp. Trả kèm `true` nếu đã dùng lại hash cũ.
async fn resolve_expected_hash(
    db: &Db,
    owned: &RunningJob,
    path: &Path,
    current: &LocalMetadata,
) -> AppResult<(String, bool)> {
    let stored = db
        .with_running_job(owned, |conn| file_fingerprint_on(conn, owned.file_id))?
        .ok_or(AppError::Superseded)?;
    if fingerprint_matches(stored.as_ref(), current) {
        if let Some(sha256) = stored.and_then(|fingerprint| fingerprint.sha256) {
            return Ok((sha256, true));
        }
    }
    Ok((refresh_file_fingerprint(db, owned, path).await?, false))
}

/// Lỗi đáng thử lại khi nội dung đọc được không khớp expected hash.
fn changed_during_upload() -> AppError {
    AppError::Message(CHANGED_DURING_UPLOAD.into())
}

/// Với nhánh không truyền byte (dedup/object reuse), chứng minh tệp hiện tại vẫn đúng là nội
/// dung `expected` bằng một lượt SHA-256 toàn tệp; khác thì lưu hash mới và trả lỗi thử lại.
async fn verify_content_without_stream(
    db: &Db,
    owned: &RunningJob,
    path: &Path,
    expected: &str,
) -> AppResult<()> {
    let current = refresh_file_fingerprint(db, owned, path).await?;
    if current != expected {
        return Err(changed_during_upload());
    }
    Ok(())
}

/// True nếu tệp cục bộ đã khác nội dung `content_hash` vừa version hóa (xem
/// `UploadReport::local_changed_after_read`).
fn local_changed_after_read(
    db: &Db,
    owned: &RunningJob,
    path: &Path,
    initial: &LocalMetadata,
    content_hash: &str,
) -> bool {
    let metadata_changed = local_metadata(path)
        .map(|now| now.size != initial.size || now.modified != initial.modified)
        .unwrap_or(true);
    // Job đã rời `running` sau finalize nên chỉ kiểm binding + tệp: không đọc dòng trùng rowid.
    let recorded_changed = db
        .with_bound_file(&owned.binding, owned.file_id, |conn| {
            file_fingerprint_on(conn, owned.file_id)
        })
        .ok()
        .flatten()
        .flatten()
        .and_then(|fingerprint| fingerprint.sha256)
        .is_some_and(|sha256| sha256 != content_hash);
    metadata_changed || recorded_changed
}

/// Chốt một lượt transfer lỗi (không phải tạm dừng, hết phiên hay mất quyền): upload gặp 409 bỏ
/// session cũ, và job sang trạng thái của `next_status` (lỗi kết nối thử lại vô hạn, lỗi
/// server/storage dừng ở trần retry). Chỉ ghi khi task vẫn sở hữu job `owned`; trả `None` và không
/// ghi gì nếu không — job của binding khác trùng rowid giữ nguyên status/attempt/lỗi.
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
pub(crate) fn record_job_failure(
    db: &Db,
    job: &JobRow,
    owned: &RunningJob,
    err: &AppError,
) -> AppResult<Option<crate::sync::retry::RetryDecision>> {
    let stale_session = job.operation == "upload" && err.to_string().contains("409");
    let attempt = job.attempt_count + 1;
    let retryable = is_retryable(err) || stale_session;
    let decision = next_status(err, attempt, retryable, now_ts());
    let changed = db.with_running_job(owned, |conn| {
        if stale_session {
            clear_job_session_on(conn, owned.job_id)?;
        }
        transition_running_job_on(
            conn,
            owned.job_id,
            decision.status,
            Some(&decision.message),
            attempt,
            decision.retry_at,
            None,
            None,
        )
    })?;
    Ok((changed == Some(true)).then_some(decision))
}

/// Log một job mà task không còn sở hữu (thư mục bị gỡ, rowid bị tái dùng, hoặc job đã bị chuyển
/// khỏi `running`): kết quả của task bị bỏ, không ghi gì vào DB.
fn log_superseded(job: &JobRow, stage: &str) {
    tracing::info!(
        job_id = job.id,
        file_id = job.file_id,
        operation = %job.operation,
        stage,
        "running job superseded: folder binding, file row or job changed; nothing recorded"
    );
}

/// Ghi kết quả finalize vào DB: xung đột thì đánh dấu job + tệp `conflict`, ngược lại job
/// `completed` (tệp thành `synced` với hash của job).
pub(crate) fn record_finalize_result(
    db: &Db,
    job: &JobRow,
    owned: &RunningJob,
    finalized: &crate::api::FinalizeResponse,
) -> AppResult<()> {
    let recorded = if finalized.status == "conflict" {
        // CAS job + đánh dấu tệp trong CÙNG transaction, chỉ khi job vẫn là job task đã claim:
        // không có khe hở để thư mục bị gỡ/gắn lại (rowid tái dùng) giữa hai lượt ghi.
        db.transition_running_job_with_conflict(
            owned,
            job.attempt_count,
            finalized.file_id,
            finalized.version_id,
            finalized.server_version_id.or(finalized.version_id),
            "Phát hiện xung đột",
        )?
    } else {
        // Hoàn tất (job + tệp `synced` với hash của job) chỉ khi task vẫn sở hữu job: kết quả của
        // một upload đã mất binding không được đánh dấu tệp của binding mới trùng rowid.
        db.transition_owned_job(
            owned,
            "completed",
            None,
            job.attempt_count,
            None,
            Some(finalized.file_id),
            finalized.version_id,
        )?
    };
    if !recorded {
        tracing::warn!(
            job_id = job.id,
            status = %finalized.status,
            "job left running before finalize was recorded; external state kept"
        );
    }
    Ok(())
}

/// Upload một tệp lên server theo invariant: chỉ finalize khi SHA-256 của đúng các byte đã PUT
/// bằng expected hash lấy từ một lượt đọc độc lập (lúc enqueue, hoặc hash lại trước upload).
///
/// 1. Expected hash: dùng lại hash lúc enqueue nếu size + mtime khớp, không thì hash lại.
/// 2. `prepare` với expected hash (hoặc tiếp tục session cũ có cùng hash).
/// 3. Đọc tuần tự mọi part — kể cả part đã upload ở lượt trước — vào một hasher; chỉ PUT part
///    còn thiếu, và PUT đúng buffer vừa hash.
/// 4. Hash stream khác expected hash → không finalize, bỏ session, hash lại, trả lỗi thử lại.
/// 5. Dedup/object reuse không có byte để stream → hash lại toàn tệp để chứng minh trước khi
///    ghi nhận.
///
/// `is_paused` được hỏi trước mỗi part cần PUT (part đang gửi không bị cắt); `after_part_read`
/// được gọi sau khi mỗi part đã đọc và hash, trước khi PUT (hook cho test).
///
/// Luật integrity: applications/laboratory-file-sync-application/docs/contract.md#direct-minio-upload
#[cfg(test)]
pub(crate) async fn run_upload_job(
    client: &ApiClient,
    db: &Db,
    job: &JobRow,
    on_progress: impl Fn(i64, i64),
    is_paused: impl Fn() -> bool,
    after_part_read: impl Fn(i64),
) -> AppResult<UploadReport> {
    let owned = db.running_job(job)?.ok_or(AppError::Superseded)?;
    run_upload_job_with(
        client,
        db,
        job,
        &owned,
        &UploadOptions::sequential(),
        on_progress,
        is_paused,
        after_part_read,
    )
    .await
}

/// Tùy chọn truyền part của một lượt upload.
#[derive(Debug, Clone)]
pub(crate) struct UploadOptions {
    /// Số PUT part của tệp này được bay cùng lúc (≥ 1).
    pub part_concurrency: usize,
    /// Ngân sách buffer part dùng chung với mọi upload khác của tiến trình.
    pub budget: Arc<PartBudget>,
}

impl UploadOptions {
    /// Một PUT mỗi lần, ngân sách mặc định riêng (cho test gọi `run_upload_job`).
    #[cfg(test)]
    pub(crate) fn sequential() -> Self {
        Self {
            part_concurrency: 1,
            budget: PartBudget::new(DEFAULT_PART_BUDGET_MIB),
        }
    }
}

/// Như `run_upload_job`, với số PUT part đồng thời và ngân sách bộ nhớ lấy từ `options`.
#[allow(clippy::too_many_arguments)]
#[tracing::instrument(
    level = "debug",
    name = "sync.run_upload_job",
    skip_all,
    fields(
        job_id = job.id,
        folder_id = job.folder_id,
        byte_count = tracing::field::Empty,
        part_count = tracing::field::Empty,
        expected_hash_reused = tracing::field::Empty
    )
)]
pub(crate) async fn run_upload_job_with(
    client: &ApiClient,
    db: &Db,
    job: &JobRow,
    owned: &RunningJob,
    options: &UploadOptions,
    on_progress: impl Fn(i64, i64),
    is_paused: impl Fn() -> bool,
    after_part_read: impl Fn(i64),
) -> AppResult<UploadReport> {
    // Nguồn và folder remote lấy từ binding đã chụp lúc bắt đầu, không đọc lại folder theo id.
    ensure_owned(db, owned)?;
    let remote_folder_id = owned
        .binding
        .remote_id
        .ok_or_else(|| AppError::Message("Thư mục chưa được đăng ký trên máy chủ".into()))?;
    if db.folder_access_denied(owned.binding.id)? {
        return Err(AppError::Forbidden(403));
    }
    let path = owned.local_path();
    if !path.is_file() {
        return Err(AppError::Message(format!(
            "Tệp không còn trên đĩa: {}",
            job.relative_path
        )));
    }
    let initial = local_metadata(&path)?;
    let size = initial.size;
    tracing::Span::current().record("byte_count", size);
    let (expected, reused) = resolve_expected_hash(db, owned, &path, &initial).await?;
    tracing::Span::current().record("expected_hash_reused", reused);
    let mut etags: Vec<(i64, String)> = job
        .uploaded_parts
        .as_ref()
        .and_then(|raw| serde_json::from_str(raw).ok())
        .unwrap_or_default();
    let (session_id, part_size) = match job.session_id {
        Some(existing) if should_resume_session(job.content_hash.as_deref(), &expected) => {
            // Session cũ: dùng đúng part size server đã cấp lúc prepare (lưu cùng session).
            (existing, job.part_size.unwrap_or(LEGACY_PART_SIZE))
        }
        _ => {
            // Hash có thể lâu: kiểm lại quyền sở hữu ngay trước khi mở session trên server.
            ensure_owned(db, owned)?;
            let prepared = client
                .prepare(
                    remote_folder_id,
                    &job.relative_path,
                    size,
                    &expected,
                    job.remote_version_id.unwrap_or(0),
                )
                .await?;
            if prepared.deduplicated {
                verify_content_without_stream(db, owned, &path, &expected).await?;
                // Hash của job và hoàn tất trong CÙNG transaction đã kiểm quyền sở hữu.
                db.with_running_job(owned, |conn| {
                    set_job_content_hash_on(conn, owned.job_id, &expected)?;
                    transition_running_job_on(
                        conn,
                        owned.job_id,
                        "completed",
                        None,
                        job.attempt_count,
                        None,
                        Some(prepared.file_id),
                        prepared.version_id,
                    )
                })?
                .ok_or(AppError::Superseded)?;
                let local_changed_after_read =
                    local_changed_after_read(db, owned, &path, &initial, &expected);
                return Ok(UploadReport {
                    outcome: UploadOutcome::Deduplicated,
                    content_hash: expected,
                    parts_uploaded: 0,
                    total_parts: 0,
                    local_changed_after_read,
                });
            }
            let session_id = prepared
                .session_id
                .ok_or_else(|| AppError::Message("Thiếu phiên tải lên".into()))?;
            if prepared.object_reused {
                verify_content_without_stream(db, owned, &path, &expected).await?;
                // Lưu session chỉ khi còn sở hữu job; không thì không finalize.
                db.with_running_job(owned, |conn| {
                    save_job_session_on(conn, owned.job_id, session_id, "[]", &expected, None)
                })?
                .ok_or(AppError::Superseded)?;
                let finalized = client.finalize(session_id, &[]).await?;
                record_finalize_result(db, job, owned, &finalized)?;
                let local_changed_after_read =
                    local_changed_after_read(db, owned, &path, &initial, &expected);
                return Ok(UploadReport {
                    outcome: UploadOutcome::Finalized(finalized),
                    content_hash: expected,
                    parts_uploaded: 0,
                    total_parts: 0,
                    local_changed_after_read,
                });
            }
            etags.clear();
            db.with_running_job(owned, |conn| {
                save_job_session_on(
                    conn,
                    owned.job_id,
                    session_id,
                    "[]",
                    &expected,
                    Some(prepared.part_size.max(1)),
                )
            })?
            .ok_or(AppError::Superseded)?;
            tracing::info!(
                job_id = job.id,
                logical_path = %job.relative_path,
                upload_session_id = session_id,
                file_id = prepared.file_id,
                "prepare completed"
            );
            (session_id, prepared.part_size.max(1))
        }
    };
    let total_parts = ((size + part_size - 1) / part_size).max(1);
    tracing::Span::current().record("part_count", total_parts);
    if job.session_id == Some(session_id) {
        let mut completed_parts: Vec<i64> = etags.iter().map(|(number, _)| *number).collect();
        completed_parts.sort_unstable();
        let done: HashSet<i64> = completed_parts.iter().copied().collect();
        tracing::info!(
            job_id = job.id,
            logical_path = %job.relative_path,
            upload_session_id = session_id,
            part_size,
            total_parts,
            completed_parts = ?completed_parts,
            missing_parts = ?missing_part_numbers(total_parts, &done),
            "resuming upload session"
        );
    }
    // Part lớn hơn toàn bộ ngân sách bộ nhớ thì không bao giờ lấy được permit: lỗi ngay.
    options.budget.ensure_fits(part_size as usize)?;
    let window = options.part_concurrency.max(1);
    // Chỉ task này ghi state multipart của job: future PUT chỉ trả (part, etag, byte).
    let mut completed: BTreeMap<i64, String> = etags.into_iter().collect();
    let mut done_parts: HashSet<i64> = completed.keys().copied().collect();
    let mut done = completed.keys().fold(0_i64, |acc, number| {
        let offset = (*number - 1) * part_size;
        acc + (size - offset).min(part_size)
    });
    let mut parts_uploaded = 0_i64;
    // Hasher đi qua đúng các byte đọc ra THEO THỨ TỰ part, kể cả part đã upload ở lượt trước
    // (đọc lại để hash, không PUT lại), nên đại diện cho TOÀN BỘ object sẽ finalize. Chỉ PUT chạy
    // song song; đọc và hash luôn tuần tự.
    let mut streamed_hasher = Sha256::new();
    // Mỗi PUT là một task riêng: chạy độc lập trong lúc task này chờ ngân sách/đọc part kế
    // tiếp, và drop `in_flight` (JoinSet) abort mọi PUT còn dở.
    let mut in_flight: JoinSet<AppResult<(i64, String, i64)>> = JoinSet::new();
    let mut urls: HashMap<i64, String> = HashMap::new();
    let mut urls_valid_until = Instant::now();
    let mut failure: Option<AppError> = None;
    let mut next_part = 1_i64;
    loop {
        // Ghi ngay các PUT đã xong (không chờ), rồi: cửa sổ đầy hoặc đã lên lịch hết thì chờ
        // một PUT xong (Pause thì dừng ngay).
        let finished = match in_flight.try_join_next() {
            Some(result) => Some(result),
            None if in_flight.len() >= window
                || (next_part > total_parts && !in_flight.is_empty()) =>
            {
                match unless_paused(async { Ok(in_flight.join_next().await) }, &is_paused).await {
                    Ok(result) => result,
                    Err(err) => {
                        failure = Some(err);
                        break;
                    }
                }
            }
            None => None,
        };
        if let Some(result) = finished {
            match flatten_part_result(result) {
                Ok((part_number, etag, len)) => {
                    completed.insert(part_number, etag);
                    done_parts.insert(part_number);
                    parts_uploaded += 1;
                    done += len;
                    persist_upload_progress(
                        db, owned, session_id, &completed, &expected, part_size, done,
                    )
                    .await?;
                    on_progress(done, size);
                }
                Err(err) => {
                    failure = Some(err);
                    break;
                }
            }
            continue;
        }
        if next_part > total_parts {
            break;
        }
        let part_number = next_part;
        next_part += 1;
        let offset = (part_number - 1) * part_size;
        let len = (size - offset).min(part_size);
        // Lấy ngân sách TRƯỚC khi cấp phát/đọc buffer; giữ tới khi PUT xong hoặc bị hủy.
        let permit = match unless_paused(options.budget.acquire(len as usize), &is_paused).await {
            Ok(permit) => permit,
            Err(err) => {
                failure = Some(err);
                break;
            }
        };
        let path_for_read = path.clone();
        let mut hasher = streamed_hasher;
        let (hasher, bytes) = run_blocking(move || {
            let bytes = read_slice(&path_for_read, offset as u64, len as usize)?;
            hasher.update(&bytes);
            Ok((hasher, bytes::Bytes::from(bytes)))
        })
        .await?;
        streamed_hasher = hasher;
        after_part_read(part_number);
        if done_parts.contains(&part_number) {
            continue;
        }
        if is_paused() {
            failure = Some(AppError::Paused);
            break;
        }
        // Presign sát lúc dùng, cho các part còn thiếu của cửa sổ sắp tới, và xin lại khi URL sắp
        // hết hạn theo tuổi thật của nó.
        if !urls.contains_key(&part_number) || Instant::now() >= urls_valid_until {
            let batch = window.max(PRESIGN_BATCH) as i64;
            let batch_end = (part_number + batch - 1).min(total_parts);
            let numbers: Vec<i64> = missing_part_numbers(batch_end, &done_parts)
                .into_iter()
                .filter(|number| *number >= part_number)
                .collect();
            tracing::info!(
                job_id = job.id,
                logical_path = %job.relative_path,
                upload_session_id = session_id,
                part_numbers = ?numbers,
                "presigning parts"
            );
            let presigned_at = Instant::now();
            let parts = match client.presign(session_id, &numbers).await {
                Ok(parts) => parts,
                Err(err) => {
                    failure = Some(err);
                    break;
                }
            };
            urls_valid_until = presigned_at + presigned_urls_lifetime(&parts);
            urls = parts
                .into_iter()
                .map(|part| (part.part_number, part.url))
                .collect();
        }
        let Some(part_url) = urls.remove(&part_number) else {
            failure = Some(AppError::Message(format!(
                "Thiếu URL presigned cho phần {part_number}"
            )));
            break;
        };
        let part_span = tracing::debug_span!(
            "sync.upload_part",
            job_id = job.id,
            upload_session_id = session_id,
            part_number,
            byte_count = len
        );
        in_flight.spawn(put_part_with_refresh(
            client.clone(),
            session_id,
            part_number,
            part_url,
            bytes,
            permit,
            len,
            part_span,
        ));
    }
    if let Some(err) = failure {
        // Giữ ETag của các PUT đã xong nhưng chưa kịp ghi; không chờ PUT còn dở. Drop
        // `in_flight` hủy các PUT dở (không có ETag, sẽ gửi lại khi resume).
        while let Some(result) = in_flight.try_join_next() {
            if let Ok((part_number, etag, len)) = flatten_part_result(result) {
                completed.insert(part_number, etag);
                done += len;
            }
        }
        in_flight.abort_all();
        drop(in_flight);
        persist_upload_progress(
            db, owned, session_id, &completed, &expected, part_size, done,
        )
        .await?;
        return Err(err);
    }
    drop(in_flight);
    let etags: Vec<(i64, String)> = completed.into_iter().collect();
    let streamed = hex::encode(streamed_hasher.finalize());
    if streamed != expected {
        // Byte đã đọc để upload không phải nội dung dự định version hóa (tệp đổi trước hoặc
        // giữa lúc đọc, có thể tạo object trộn hai trạng thái): không finalize session này.
        tracing::warn!(
            job_id = job.id,
            logical_path = %job.relative_path,
            upload_session_id = session_id,
            "streamed hash differs from expected hash; not finalizing"
        );
        db.with_running_job(owned, |conn| clear_job_session_on(conn, owned.job_id))?
            .ok_or(AppError::Superseded)?;
        refresh_file_fingerprint(db, owned, &path).await?;
        return Err(changed_during_upload());
    }
    // Không finalize version chuẩn cho một binding đã bị gỡ: kiểm quyền sở hữu ngay trước.
    ensure_owned(db, owned)?;
    let finalized = client.finalize(session_id, &etags).await?;
    tracing::info!(
        job_id = job.id,
        logical_path = %job.relative_path,
        upload_session_id = session_id,
        status = %finalized.status,
        "finalize completed"
    );
    record_finalize_result(db, job, owned, &finalized)?;
    let local_changed_after_read = local_changed_after_read(db, owned, &path, &initial, &expected);
    Ok(UploadReport {
        outcome: UploadOutcome::Finalized(finalized),
        content_hash: expected,
        parts_uploaded,
        total_parts,
        local_changed_after_read,
    })
}

/// Báo cáo một lượt download: số byte đã tiếp tục bằng Range (0 nếu tải từ đầu hoặc không cần
/// tải).
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub(crate) struct DownloadReport {
    pub resumed_from: i64,
    /// True nếu task mất quyền sở hữu job giữa chừng (thư mục bị gỡ, hoặc rowid job/tệp/folder
    /// đã được tái dùng cho binding khác): không ghi gì vào DB hay tệp đích.
    pub superseded: bool,
}

/// Điểm dừng tất định trong một lượt download, để test chen thao tác gỡ/gắn lại thư mục vào đúng
/// khe hở giữa lúc chụp danh tính và lúc ghi.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DownloadCheckpoint {
    /// Vừa chụp danh tính job/tệp/binding, trước mọi lượt await mạng.
    TargetCaptured,
    /// Tệp tạm đã tải và kiểm xong, ngay trước khi thay thế tệp đích và ghi DB.
    BeforeCommit,
}

/// Tải xuống version chuẩn hiện hành của một tệp: nếu bản cục bộ đã trùng thì chỉ cập nhật
/// base; nếu bản cục bộ khác cả base lẫn server thì đánh dấu xung đột thay vì ghi đè; nếu
/// không, tải vào tệp tạm, kiểm toàn vẹn, rồi thay thế nguyên tử.
#[cfg(test)]
#[tracing::instrument(
    level = "debug",
    name = "sync.run_download_job",
    skip_all,
    fields(
        job_id = job.id,
        folder_id = job.folder_id,
        file_id = job.file_id,
        byte_count = tracing::field::Empty
    )
)]
pub(crate) async fn run_download_job(
    client: &ApiClient,
    db: &Db,
    job: &JobRow,
    on_progress: impl Fn(i64, i64, i64),
    is_paused: impl Fn() -> bool,
) -> AppResult<DownloadReport> {
    if job.remote_file_id.is_none() {
        return Err(AppError::Message("Thiếu mã tệp trên máy chủ".into()));
    }
    // Chụp danh tính MỘT lần: mọi lượt ghi sau (DB và tệp đích) phải chứng minh nó còn nguyên.
    let Some(owned) = db.running_job(job)? else {
        return Ok(superseded_download(job, "before start"));
    };
    run_download_job_with(client, db, job, &owned, on_progress, is_paused, |_| {}).await
}

/// Như `run_download_job`, với danh tính `owned` đã chụp lúc task bắt đầu, và gọi `checkpoint`
/// tại các điểm dừng của `DownloadCheckpoint` (hook cho test race gỡ/gắn lại thư mục).
pub(crate) async fn run_download_job_with(
    client: &ApiClient,
    db: &Db,
    job: &JobRow,
    owned: &RunningJob,
    on_progress: impl Fn(i64, i64, i64),
    is_paused: impl Fn() -> bool,
    checkpoint: impl Fn(DownloadCheckpoint),
) -> AppResult<DownloadReport> {
    let remote_file_id = owned
        .remote_file_id
        .ok_or_else(|| AppError::Message("Thiếu mã tệp trên máy chủ".into()))?;
    let dest = owned.local_path();
    checkpoint(DownloadCheckpoint::TargetCaptured);
    let detail = client.get_file(remote_file_id).await?;
    let current = detail
        .current_version
        .as_ref()
        .ok_or_else(|| AppError::Message("Tệp trên máy chủ chưa có phiên bản chuẩn".into()))?;
    let version_id = current.id;
    let expected_hash = current.content_hash.clone();
    let expected_size = current.size;
    tracing::Span::current().record("byte_count", expected_size);
    let version_number = current.version_number;
    if dest.is_file() {
        let dest_for_hash = dest.clone();
        let local_hash = tokio::task::spawn_blocking(move || sha256_file(&dest_for_hash))
            .await
            .map_err(|err| AppError::Message(err.to_string()))??;
        // Quyết định (trùng / xung đột / tải) và lượt ghi của nó nằm trong CÙNG transaction đã
        // kiểm danh tính, để base đọc ra và dòng được ghi là của đúng tệp task đã bắt đầu.
        let settled = db.with_running_job(owned, |conn| {
            if local_hash == expected_hash {
                apply_remote_base_on(
                    conn,
                    owned.file_id,
                    remote_file_id,
                    version_id,
                    &expected_hash,
                    expected_size,
                )?;
                transition_running_job_on(
                    conn,
                    job.id,
                    "completed",
                    None,
                    job.attempt_count,
                    None,
                    Some(remote_file_id),
                    Some(version_id),
                )?;
                return Ok(true);
            }
            let base = last_synced_hash_on(conn, owned.file_id)?;
            if decide_sync_action(Some(&local_hash), base.as_deref(), &expected_hash)
                == SyncAction::Conflict
            {
                mark_file_conflict_on(
                    conn,
                    owned.file_id,
                    Some(remote_file_id),
                    Some(version_id),
                    "Xung đột: tệp cục bộ và máy chủ cùng thay đổi",
                )?;
                return Ok(true);
            }
            Ok(false)
        })?;
        match settled {
            None => return Ok(superseded_download(job, "before local comparison")),
            Some(true) => return Ok(DownloadReport::default()),
            Some(false) => {}
        }
    }
    let suppressed = db.with_running_job(owned, |conn| {
        set_suppress_hash_on(conn, owned.file_id, &expected_hash)
    })?;
    if suppressed.is_none() {
        return Ok(superseded_download(job, "before fetch"));
    }
    let temp = download_temp_path(&dest, job.id);
    tracing::info!(
        job_id = job.id,
        file_id = remote_file_id,
        version_id,
        "download authorized; fetching object"
    );
    let auth = client
        .authorize_download(remote_file_id, version_id)
        .await?;
    let downloaded = download_object(&auth.url, &temp, expected_size, is_paused).await?;
    let written = downloaded.written;
    let recorded = db.with_running_job(owned, |conn| set_progress_on(conn, job.id, written))?;
    if recorded.is_none() {
        discard_stale_temp(&temp);
        return Ok(superseded_download(job, "after fetch"));
    }
    on_progress(written, expected_size, version_number);
    let temp_for_verify = temp.clone();
    let hash_for_verify = expected_hash.clone();
    tokio::task::spawn_blocking(move || {
        verify_download(&temp_for_verify, expected_size, &hash_for_verify)?;
        // fsync trước, ngoài mutex DB: lượt thay thế bên dưới giữ mutex và chỉ còn rename.
        fsync_path(&temp_for_verify)
    })
    .await
    .map_err(|err| AppError::Message(err.to_string()))??;
    checkpoint(DownloadCheckpoint::BeforeCommit);
    // Kiểm danh tính, thay tệp đích và ghi DB trong CÙNG transaction, dưới cùng mutex với
    // `delete_folder`: thư mục không thể bị gỡ/gắn lại giữa lúc kiểm và lúc rename, nên tệp chỉ
    // được ghi xuống đĩa khi binding A còn là binding hiện hành.
    let commit_db = db.clone();
    let commit_owned = owned.clone();
    let (temp_for_replace, dest_for_replace) = (temp.clone(), dest.clone());
    let (job_id, attempt) = (job.id, job.attempt_count);
    let hash_for_commit = expected_hash.clone();
    let committed = tokio::task::spawn_blocking(move || {
        commit_db.with_running_job(&commit_owned, |conn| {
            atomic_replace(&temp_for_replace, &dest_for_replace).map_err(busy_replace_error)?;
            apply_remote_base_on(
                conn,
                commit_owned.file_id,
                remote_file_id,
                version_id,
                &hash_for_commit,
                expected_size,
            )?;
            save_job_session_on(conn, job_id, 0, "[]", &hash_for_commit, None)?;
            transition_running_job_on(
                conn,
                job_id,
                "completed",
                None,
                attempt,
                None,
                Some(remote_file_id),
                Some(version_id),
            )
        })
    })
    .await
    .map_err(|err| AppError::Message(err.to_string()))??;
    if committed.is_none() {
        discard_stale_temp(&temp);
        return Ok(superseded_download(job, "before replace"));
    }
    tracing::info!(
        job_id = job.id,
        file_id = remote_file_id,
        version_id,
        resumed_from = downloaded.resumed_from,
        "download completed"
    );
    Ok(DownloadReport {
        resumed_from: downloaded.resumed_from,
        superseded: false,
    })
}

/// Lỗi rename vì tệp đích đang bị chương trình khác giữ (Windows) được đổi thành thông báo thử
/// lại; lỗi khác giữ nguyên.
fn busy_replace_error(err: AppError) -> AppError {
    let text = err.to_string().to_ascii_lowercase();
    if text.contains("permission denied")
        || text.contains("os error 32")
        || text.contains("resource busy")
    {
        AppError::Message("Tệp đang được chương trình khác sử dụng, sẽ thử thay thế lại".into())
    } else {
        err
    }
}

/// Kết quả của một download mà task đã mất quyền sở hữu (thư mục bị gỡ, hoặc rowid bị tái dùng):
/// không ghi gì thêm, chỉ log.
fn superseded_download(job: &JobRow, stage: &str) -> DownloadReport {
    tracing::info!(
        job_id = job.id,
        file_id = job.file_id,
        stage,
        "download superseded: folder binding or file row changed; nothing committed"
    );
    DownloadReport {
        resumed_from: 0,
        superseded: true,
    }
}

/// Xóa tệp tạm của một download đã mất quyền sở hữu. Tệp tạm không bao giờ là tệp của người dùng
/// (`is_internal_path`: watcher và lượt quét bỏ qua), nên xóa không đụng dữ liệu của binding mới;
/// lỗi xóa chỉ được log.
fn discard_stale_temp(temp: &Path) {
    match fs::remove_file(temp) {
        Ok(()) => {}
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
        Err(err) => tracing::warn!(error = %err, "could not remove superseded download temp"),
    }
}

/// Chuyển rule đã lưu cục bộ sang định dạng DTO để gửi lên server.
pub fn to_rule_dtos(rules: &[SyncRule]) -> Vec<RuleDto> {
    rules
        .iter()
        .map(|rule| RuleDto {
            id: None,
            r#type: rule.kind.clone(),
            pattern: rule.pattern.clone(),
            recursive: rule.recursive,
            enabled: rule.enabled,
        })
        .collect()
}

/// Liệt kê mọi tệp dưới `root` (đệ quy nếu `recursive`), bảo vệ khỏi vòng lặp symlink bằng tập
/// thư mục đã thăm.
fn walk(root: &Path, recursive: bool) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    let mut seen = HashSet::new();
    while let Some(dir) = stack.pop() {
        if !seen.insert(dir.clone()) {
            continue;
        }
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                if recursive {
                    stack.push(path);
                }
            } else {
                out.push(path);
            }
        }
    }
    out
}

/// Đọc `len` byte của tệp bắt đầu từ `offset`, dùng để lấy đúng một phần khi tải lên multipart.
fn read_slice(path: &Path, offset: u64, len: usize) -> AppResult<Vec<u8>> {
    let mut file = std::fs::File::open(path)?;
    file.seek(SeekFrom::Start(offset))?;
    let mut buf = vec![0u8; len];
    file.read_exact(&mut buf)?;
    Ok(buf)
}

/// Thời điểm hiện tại tính bằng giây Unix epoch.
fn now_ts() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

/// True nếu không cần xếp hàng tải lên: hash khớp `suppress_hash` (tự vọng lại của một lượt tải
/// xuống), hoặc đã `synced` với đúng hash đã lưu.
pub(crate) fn should_skip_enqueue(
    saved_sha: Option<&str>,
    current: &str,
    status: Option<&str>,
    suppress_hash: Option<&str>,
) -> bool {
    if suppress_hash == Some(current) {
        return true;
    }
    if saved_sha == Some(current) && status == Some("synced") {
        return true;
    }
    false
}

/// True nếu phiên tải lên dở dang còn dùng được: hash nội dung đã lưu vẫn khớp nội dung hiện tại.
pub(crate) fn should_resume_session(saved_hash: Option<&str>, current: &str) -> bool {
    saved_hash == Some(current)
}

/// Thời gian còn dùng được của một lô URL presigned: TTL ngắn nhất trong lô trừ đi
/// `PRESIGN_EXPIRY_MARGIN`; lô rỗng hoặc TTL không hợp lệ thì coi như hết hạn ngay.
pub(crate) fn presigned_urls_lifetime(parts: &[crate::api::PresignPart]) -> Duration {
    let min_ttl = parts.iter().map(|part| part.expires_in).min().unwrap_or(0);
    Duration::from_secs(min_ttl.max(0) as u64).saturating_sub(PRESIGN_EXPIRY_MARGIN)
}

/// Số thứ tự các phần từ 1 đến `total_parts` chưa có trong `done`.
pub fn missing_part_numbers(total_parts: i64, done: &HashSet<i64>) -> Vec<i64> {
    (1..=total_parts)
        .filter(|number| !done.contains(number))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::missing_part_numbers;
    use crate::error::AppResult;
    use std::collections::HashSet;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::time::{Duration, Instant};

    /// Delta tiến độ phải serialize đúng camelCase (jobId, done, total) cho frontend.
    #[test]
    fn progress_delta_serializes_as_camel_case() {
        let delta = super::ProgressDeltaDto {
            job_id: 42,
            done: 1024,
            total: 2048,
        };
        let json = serde_json::to_string(&delta).unwrap();
        assert_eq!(json, r#"{"jobId":42,"done":1024,"total":2048}"#);
    }

    /// Sự kiện files changed phải serialize đúng camelCase (revision).
    #[test]
    fn files_changed_serializes_as_camel_case() {
        let event = super::FilesChangedDto { revision: 7 };
        let json = serde_json::to_string(&event).unwrap();
        assert_eq!(json, r#"{"revision":7}"#);
    }

    /// Công việc blocking phải rời executor để timer Tokio vẫn được đánh thức đúng hạn.
    #[tokio::test(flavor = "current_thread")]
    async fn blocking_task_keeps_tokio_executor_responsive() {
        let release = Arc::new(AtomicBool::new(false));
        let worker_release = release.clone();
        let watchdog_release = release.clone();
        let watchdog = std::thread::spawn(move || {
            for _ in 0..50 {
                if watchdog_release.load(Ordering::SeqCst) {
                    return;
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            watchdog_release.store(true, Ordering::SeqCst);
        });
        let started = Instant::now();
        let blocking = tokio::spawn(super::run_blocking(move || -> AppResult<()> {
            while !worker_release.load(Ordering::SeqCst) {
                std::thread::yield_now();
            }
            Ok(())
        }));

        tokio::task::yield_now().await;
        release.store(true, Ordering::SeqCst);
        blocking.await.unwrap().unwrap();
        watchdog.join().unwrap();

        assert!(
            started.elapsed() < Duration::from_millis(200),
            "blocking work starved the Tokio executor"
        );
    }

    /// Hai lượt đối soát được yêu cầu cùng lúc phải chạy tuần tự, không cùng quét đĩa.
    #[tokio::test]
    async fn blocking_reconciliation_tasks_are_serialized() {
        let gate = Arc::new(tokio::sync::Mutex::new(()));
        let (first_entered_tx, first_entered_rx) = tokio::sync::oneshot::channel();
        let (first_release_tx, first_release_rx) = std::sync::mpsc::channel();
        let first = tokio::spawn(super::run_serialized_blocking(
            gate.clone(),
            move || -> AppResult<()> {
                let _ = first_entered_tx.send(());
                first_release_rx.recv().unwrap();
                Ok(())
            },
        ));
        first_entered_rx.await.unwrap();

        let (second_entered_tx, mut second_entered_rx) = tokio::sync::oneshot::channel();
        let (second_release_tx, second_release_rx) = std::sync::mpsc::channel();
        let second = tokio::spawn(super::run_serialized_blocking(
            gate,
            move || -> AppResult<()> {
                let _ = second_entered_tx.send(());
                second_release_rx.recv().unwrap();
                Ok(())
            },
        ));

        assert!(
            tokio::time::timeout(Duration::from_millis(50), &mut second_entered_rx)
                .await
                .is_err(),
            "second reconciliation entered before the first one finished"
        );
        first_release_tx.send(()).unwrap();
        tokio::time::timeout(Duration::from_secs(1), &mut second_entered_rx)
            .await
            .unwrap()
            .unwrap();
        second_release_tx.send(()).unwrap();
        first.await.unwrap().unwrap();
        second.await.unwrap().unwrap();
    }

    /// Các phần đã tải lên rồi phải bị loại khỏi danh sách còn thiếu.
    #[test]
    fn resume_skips_already_uploaded_parts() {
        let done = HashSet::from([1_i64, 2]);
        assert_eq!(missing_part_numbers(4, &done), vec![3, 4]);
        assert!(missing_part_numbers(2, &done).is_empty());
    }

    /// Lô URL presigned hết hạn theo TTL ngắn nhất trừ biên an toàn; lô rỗng hoặc TTL nhỏ hơn
    /// biên thì phải xin lại ngay.
    #[test]
    fn presigned_urls_expire_by_shortest_ttl_minus_margin() {
        use super::{presigned_urls_lifetime, PRESIGN_EXPIRY_MARGIN};
        use crate::api::PresignPart;
        use std::time::Duration;
        let part = |part_number: i64, expires_in: i64| PresignPart {
            part_number,
            url: String::new(),
            expires_in,
        };
        assert_eq!(
            presigned_urls_lifetime(&[part(1, 900), part(2, 600)]),
            Duration::from_secs(600) - PRESIGN_EXPIRY_MARGIN
        );
        assert_eq!(presigned_urls_lifetime(&[]), Duration::ZERO);
        assert_eq!(presigned_urls_lifetime(&[part(1, 30)]), Duration::ZERO);
        assert_eq!(presigned_urls_lifetime(&[part(1, -5)]), Duration::ZERO);
    }

    /// Chỉ bỏ qua xếp hàng khi tệp đã `synced` với đúng hash đã lưu; trạng thái khác hoặc hash
    /// khác thì vẫn phải xếp hàng.
    #[test]
    fn skips_enqueue_only_when_synced_with_same_hash() {
        assert!(super::should_skip_enqueue(
            Some("aa"),
            "aa",
            Some("synced"),
            None
        ));
        assert!(!super::should_skip_enqueue(
            Some("aa"),
            "aa",
            Some("pending"),
            None
        ));
        assert!(!super::should_skip_enqueue(
            Some("aa"),
            "bb",
            Some("synced"),
            None
        ));
    }

    use super::{plan_remote_change, RemoteOutcome};
    use crate::api::FolderChangeDto;
    use crate::storage::{Db, FolderRow};
    use crate::sync::hash::sha256_file;
    use crate::sync::rules::SyncRule;

    /// Một tệp hiện có trên server (như `GET /folders/{id}/files` trả về), quy về dạng change.
    fn remote_file(file_id: i64, path: &str, hash: &str) -> FolderChangeDto {
        FolderChangeDto {
            id: 0,
            change_type: "CANONICAL_VERSION".into(),
            folder_id: 7,
            file_id,
            logical_path: path.into(),
            current_version_id: Some(file_id * 10),
            version_number: Some(1),
            content_hash: Some(hash.into()),
            size: 4,
            source: Some("UPLOAD".into()),
            changed_at: None,
            changed_by_device_id: None,
        }
    }

    /// Gắn remote id 7 vào một thư mục cục bộ và trả về dòng folder.
    fn bind(db: &Db, local: &std::path::Path, rules: &[SyncRule]) -> FolderRow {
        let id = db
            .upsert_folder(local.to_str().unwrap(), "R", Some(7), true, rules)
            .unwrap();
        db.list_folders()
            .unwrap()
            .into_iter()
            .find(|folder| folder.id == id)
            .unwrap()
    }

    /// Đường dẫn các job tải xuống đang chờ.
    fn queued(db: &Db) -> Vec<String> {
        let mut paths: Vec<String> = db
            .list_jobs()
            .unwrap()
            .into_iter()
            .filter(|job| job.operation == "download" && job.status == "pending")
            .map(|job| job.relative_path)
            .collect();
        paths.sort();
        paths
    }

    /// Gắn folder có sẵn 3 tệp (gồm đường dẫn lồng nhau) vào thư mục rỗng → 3 job tải xuống, giữ
    /// nguyên đường dẫn tương đối; chạy lại (idempotent) không nhân đôi job; không sinh job upload.
    #[tokio::test]
    async fn newly_bound_folder_queues_every_remote_file_with_nested_paths() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let local = dir.path().join("local");
        std::fs::create_dir_all(&local).unwrap();
        let folder = bind(&db, &local, &[]);
        let remote = [
            remote_file(1, "a.txt", "h1"),
            remote_file(2, "reports/report.xlsx", "h2"),
            remote_file(3, "raw/machine/result.csv", "h3"),
        ];
        for _ in 0..2 {
            for file in &remote {
                assert_eq!(
                    plan_remote_change(&db, &folder, file).await.unwrap(),
                    RemoteOutcome::DownloadQueued
                );
            }
        }
        assert_eq!(
            queued(&db),
            vec!["a.txt", "raw/machine/result.csv", "reports/report.xlsx"]
        );
        assert!(db
            .list_jobs()
            .unwrap()
            .iter()
            .all(|job| job.operation == "download"));
    }

    /// Thư mục cục bộ đã có tệp: trùng hash → chỉ cập nhật base, không truyền; chỉ có trên server
    /// → tải xuống; cục bộ khác server mà chưa có base → xung đột (không ghi đè lúc gắn).
    #[tokio::test]
    async fn non_empty_local_folder_uses_normal_conflict_safe_decisions() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let local = dir.path().join("local");
        std::fs::create_dir_all(&local).unwrap();
        std::fs::write(local.join("same.txt"), b"same").unwrap();
        std::fs::write(local.join("diverged.txt"), b"mine").unwrap();
        let same_hash = sha256_file(&local.join("same.txt")).unwrap();
        let folder = bind(&db, &local, &[]);

        let same = plan_remote_change(&db, &folder, &remote_file(1, "same.txt", &same_hash)).await;
        assert_eq!(same.unwrap(), RemoteOutcome::BaseAdvanced);
        let only_remote = plan_remote_change(&db, &folder, &remote_file(2, "new.txt", "h2")).await;
        assert_eq!(only_remote.unwrap(), RemoteOutcome::DownloadQueued);
        let diverged =
            plan_remote_change(&db, &folder, &remote_file(3, "diverged.txt", "theirs")).await;
        assert_eq!(diverged.unwrap(), RemoteOutcome::Conflict { base: None });
        assert_eq!(queued(&db), vec!["new.txt"]);
        assert_eq!(std::fs::read(local.join("diverged.txt")).unwrap(), b"mine");
    }

    /// Tệp đã đồng bộ (base = server) rồi bị xóa trên máy → lượt hydrate/đối soát tải xuống lại.
    #[tokio::test]
    async fn locally_deleted_synced_file_is_downloaded_again() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let local = dir.path().join("local");
        std::fs::create_dir_all(&local).unwrap();
        std::fs::write(local.join("a.txt"), b"data").unwrap();
        let hash = sha256_file(&local.join("a.txt")).unwrap();
        let folder = bind(&db, &local, &[]);
        let file = remote_file(1, "a.txt", &hash);
        assert_eq!(
            plan_remote_change(&db, &folder, &file).await.unwrap(),
            RemoteOutcome::BaseAdvanced
        );
        std::fs::remove_file(local.join("a.txt")).unwrap();
        assert_eq!(
            plan_remote_change(&db, &folder, &file).await.unwrap(),
            RemoteOutcome::DownloadQueued
        );
    }

    /// Gắn → "Ngừng đồng bộ" (xóa binding cục bộ) → gắn lại CÙNG remote id vào thư mục rỗng khác:
    /// mọi tệp hiện có lại được xếp hàng tải xuống (state tệp cũ đã đi theo binding cũ).
    #[tokio::test]
    async fn rebinding_same_remote_folder_hydrates_again() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let first = dir.path().join("first");
        let second = dir.path().join("second");
        std::fs::create_dir_all(&first).unwrap();
        std::fs::create_dir_all(&second).unwrap();
        let file = remote_file(1, "sub/a.txt", "h1");

        let folder = bind(&db, &first, &[]);
        plan_remote_change(&db, &folder, &file).await.unwrap();
        db.set_change_cursor(7, 999).unwrap();
        db.set_needs_hydration(folder.id, true).unwrap();
        db.delete_folder(folder.id).unwrap();
        assert!(!db.needs_hydration(folder.id).unwrap());
        assert!(queued(&db).is_empty());

        let rebound = bind(&db, &second, &[]);
        // Cursor change feed lưu theo remote id nên còn nguyên sau khi bỏ binding: feed sẽ không trả
        // lại gì — đây chính là lý do hydrate phải dùng danh sách tệp hiện tại chứ không phải feed.
        assert_eq!(db.change_cursor(7).unwrap(), 999);
        assert_eq!(
            plan_remote_change(&db, &rebound, &file).await.unwrap(),
            RemoteOutcome::DownloadQueued
        );
        assert_eq!(queued(&db), vec!["sub/a.txt"]);
    }

    /// Rule lọc của binding áp cho hydrate y như cho watcher; không có rule thì lấy mọi tệp.
    #[tokio::test]
    async fn hydration_follows_folder_rules() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let local = dir.path().join("local");
        std::fs::create_dir_all(&local).unwrap();
        let rules = [SyncRule {
            kind: "extension".into(),
            pattern: "xlsx".into(),
            recursive: true,
            enabled: true,
        }];
        let folder = bind(&db, &local, &rules);
        let skipped = plan_remote_change(&db, &folder, &remote_file(1, "notes.txt", "h1")).await;
        assert_eq!(skipped.unwrap(), RemoteOutcome::Skipped);
        let kept = plan_remote_change(&db, &folder, &remote_file(2, "r/report.xlsx", "h2")).await;
        assert_eq!(kept.unwrap(), RemoteOutcome::DownloadQueued);
        assert_eq!(queued(&db), vec!["r/report.xlsx"]);
    }

    /// TÍCH HỢP THẬT (bỏ qua mặc định): gắn một folder có sẵn tệp trên server dev vào thư mục rỗng
    /// bằng đúng các hàm production (`hydrate_folder` → `Db::next_job` → `run_download_job`), rồi
    /// bỏ binding và gắn lại sang thư mục rỗng khác. Chạy:
    /// `MEDILAB_E2E_URL=… MEDILAB_E2E_LOGIN=… MEDILAB_E2E_PASSWORD=… MEDILAB_E2E_FOLDER_ID=…
    ///  cargo test live_bind_hydrates -- --ignored --nocapture`
    #[tokio::test]
    #[ignore = "needs a running dev server and MEDILAB_E2E_* variables"]
    async fn live_bind_hydrates_existing_remote_folder_into_empty_directory() {
        use super::{hydrate_folder, run_download_job, should_skip_enqueue};
        use crate::api::ApiClient;

        let env = |name: &str| std::env::var(name).unwrap_or_else(|_| panic!("{name} not set"));
        let (url, remote_id) = (env("MEDILAB_E2E_URL"), env("MEDILAB_E2E_FOLDER_ID"));
        let remote_id: i64 = remote_id.parse().unwrap();
        let uid = format!("hydrate-e2e-{}", uuid::Uuid::new_v4());
        let session = ApiClient::login(
            &url,
            &env("MEDILAB_E2E_LOGIN"),
            &env("MEDILAB_E2E_PASSWORD"),
            "hydrate-e2e",
            "linux",
            "e2e",
            &uid,
        )
        .await
        .unwrap();
        let client = ApiClient::new(&url, &session.api_key, session.device_id).unwrap();
        let before = client.folder_files(remote_id, 50, 0).await.unwrap();
        let expected: Vec<(String, String, i64)> = before
            .items
            .iter()
            .filter_map(|item| {
                item.current_version.as_ref().map(|version| {
                    (
                        item.logical_path.clone(),
                        version.content_hash.clone(),
                        version.version_number,
                    )
                })
            })
            .collect();
        assert!(
            expected.len() >= 3,
            "seed the folder with nested files first"
        );

        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        for round in ["first", "second"] {
            let local = dir.path().join(round);
            std::fs::create_dir_all(&local).unwrap();
            let id = db
                .upsert_folder(local.to_str().unwrap(), "R", Some(remote_id), true, &[])
                .unwrap();
            let folder = db
                .list_folders()
                .unwrap()
                .into_iter()
                .find(|row| row.id == id)
                .unwrap();
            let summary = hydrate_folder(&client, &db, &folder).await.unwrap();
            println!("[{round}] hydration: {summary:?}");
            assert_eq!(summary.downloads_queued, expected.len());
            assert_eq!(summary.failed_items, 0);
            let pending = db.list_jobs().unwrap();
            assert_eq!(pending.len(), expected.len());
            assert!(pending.iter().all(|job| job.operation == "download"));
            while let Some(job) = db.next_job().unwrap() {
                run_download_job(&client, &db, &job, |_, _, _| {}, || false)
                    .await
                    .unwrap();
            }
            for (path, hash, _) in &expected {
                let file = local.join(path);
                assert!(file.is_file(), "{path} missing on disk");
                assert_eq!(&sha256_file(&file).unwrap(), hash, "{path} hash");
                println!("[{round}] on disk + sha256 ok: {path}");
            }
            // Tệp vừa tải xuống không được bị watcher/scan coi là thay đổi cần upload.
            for row in db.list_remote_files().unwrap() {
                let current = sha256_file(&local.join(&row.relative_path)).unwrap();
                assert!(should_skip_enqueue(
                    row.last_synced_hash.as_deref(),
                    &current,
                    Some(row.status.as_str()),
                    row.suppress_hash.as_deref(),
                ));
            }
            // Hydrate lần nữa là no-op: mọi thứ đã khớp.
            let again = hydrate_folder(&client, &db, &folder).await.unwrap();
            assert_eq!(again.downloads_queued, 0);
            // "Ngừng đồng bộ": chỉ bỏ binding cục bộ; tệp trên đĩa còn nguyên.
            db.delete_folder(id).unwrap();
            assert!(local.join(&expected[0].0).is_file());
        }
        let after = client.folder_files(remote_id, 50, 0).await.unwrap();
        let versions: Vec<i64> = after
            .items
            .iter()
            .filter_map(|item| item.current_version.as_ref().map(|v| v.version_number))
            .collect();
        let expected_versions: Vec<i64> = expected.iter().map(|(_, _, number)| *number).collect();
        assert_eq!(after.total, before.total, "no new server files");
        assert_eq!(versions, expected_versions, "no new server versions");
    }

    /// Hash khớp `suppress_hash` phải bị bỏ qua dù trạng thái tệp chưa phải `synced` (tự vọng
    /// lại của một lượt tải xuống).
    #[test]
    fn watcher_skips_hash_matching_download_suppress() {
        assert!(super::should_skip_enqueue(
            Some("old"),
            "new",
            Some("pending"),
            Some("new")
        ));
    }

    /// Chỉ tiếp tục phiên tải lên khi hash nội dung đã lưu khớp hash hiện tại; thiếu hash đã lưu
    /// hoặc khác hash thì không.
    #[test]
    fn resumes_session_only_when_content_hash_matches() {
        assert!(super::should_resume_session(Some("abc"), "abc"));
        assert!(!super::should_resume_session(Some("abc"), "def"));
        assert!(!super::should_resume_session(None, "abc"));
    }
}
