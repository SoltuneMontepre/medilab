//! Dispatcher transfer có giới hạn: claim job từ SQLite theo từng loại (upload/download) và chạy
//! song song trong `JoinSet`, tối đa số slot cấu hình. Mỗi tệp chỉ có tối đa một transfer nhờ
//! claim ở tầng DB (`Db::claim_next_job`); multipart của MỘT tệp vẫn tuần tự.
//!
//! Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#concurrent-transfers

use crate::error::{AppError, AppResult};
use crate::storage::{Db, JobRow, RunningJob};
use std::future::Future;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio::task::JoinSet;

/// Số upload chạy song song mặc định (gồm cả slot dành cho tệp nhỏ).
pub const UPLOAD_CONCURRENCY: usize = 3;
/// Số download chạy song song mặc định (gồm cả slot dành cho tệp nhỏ).
pub const DOWNLOAD_CONCURRENCY: usize = 3;
/// Job có `bytes_total` không vượt ngưỡng này (một part) được coi là nhỏ; slot 0 của mỗi loại
/// chỉ nhận job nhỏ để tệp nhỏ không phải xếp sau các tệp lớn.
pub const SMALL_TRANSFER_BYTES: i64 = 16 * 1024 * 1024;
/// Chu kỳ kiểm lại quyền truy cập folder của một transfer đang chạy.
pub const ACCESS_CHECK_INTERVAL: Duration = Duration::from_secs(1);

/// Giới hạn slot của dispatcher.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TransferLimits {
    pub uploads: usize,
    pub downloads: usize,
    /// Slot 0 của mỗi loại chỉ nhận job ≤ `SMALL_TRANSFER_BYTES` (chỉ khi loại đó có ≥ 2 slot).
    pub small_lane: bool,
}

/// Giới hạn trên/dưới cho các setting concurrency ẩn.
pub const MIN_CONCURRENCY: i64 = 1;
pub const MAX_CONCURRENCY: i64 = 4;

/// Kẹp một giá trị concurrency đọc từ settings vào `MIN_CONCURRENCY..=MAX_CONCURRENCY`.
pub fn clamp_concurrency(value: i64) -> usize {
    value.clamp(MIN_CONCURRENCY, MAX_CONCURRENCY) as usize
}

impl TransferLimits {
    /// Giới hạn slot từ settings ẩn (đã kẹp); slot tệp nhỏ bật khi loại đó có ≥ 2 slot.
    pub fn from_settings(settings: &crate::config::AppSettings) -> Self {
        Self {
            uploads: clamp_concurrency(settings.upload_concurrency),
            downloads: clamp_concurrency(settings.download_concurrency),
            small_lane: true,
        }
    }
}

impl Default for TransferLimits {
    /// Giới hạn mặc định của app: 3 upload + 3 download, có slot riêng cho tệp nhỏ.
    fn default() -> Self {
        Self {
            uploads: UPLOAD_CONCURRENCY,
            downloads: DOWNLOAD_CONCURRENCY,
            small_lane: true,
        }
    }
}

/// Slot một transfer đang giữ; trả chỉ số slot và permit về pool khi bị drop.
pub struct TransferSlot {
    pub index: usize,
    free: Arc<Mutex<Vec<usize>>>,
    _permit: OwnedSemaphorePermit,
}

impl Drop for TransferSlot {
    /// Trả chỉ số slot về danh sách trống.
    fn drop(&mut self) {
        if let Ok(mut free) = self.free.lock() {
            free.push(self.index);
        }
    }
}

/// Pool slot của một loại transfer: semaphore giới hạn số lượng, danh sách chỉ số để log.
struct SlotPool {
    operation: &'static str,
    permits: Arc<Semaphore>,
    free: Arc<Mutex<Vec<usize>>>,
    small_lane: bool,
}

impl SlotPool {
    /// Dựng pool `size` slot cho `operation`.
    fn new(operation: &'static str, size: usize, small_lane: bool) -> Self {
        Self {
            operation,
            permits: Arc::new(Semaphore::new(size)),
            free: Arc::new(Mutex::new((0..size).rev().collect())),
            small_lane: small_lane && size >= 2,
        }
    }

    /// Lấy một slot trống (chỉ số nhỏ nhất) nếu còn; không chờ.
    fn try_acquire(&self) -> Option<TransferSlot> {
        let permit = self.permits.clone().try_acquire_owned().ok()?;
        let index = {
            let mut free = self.free.lock().ok()?;
            free.sort_unstable_by(|a, b| b.cmp(a));
            free.pop()?
        };
        Some(TransferSlot {
            index,
            free: self.free.clone(),
            _permit: permit,
        })
    }

    /// Ngưỡng kích thước job mà slot này được nhận (`None` = không giới hạn).
    fn max_bytes(&self, slot: &TransferSlot) -> Option<i64> {
        (self.small_lane && slot.index == 0).then_some(SMALL_TRANSFER_BYTES)
    }
}

/// Dispatcher transfer: claim job cho slot trống và chạy `run(job)` trong `JoinSet`.
pub struct Dispatcher<R> {
    db: Db,
    pools: [SlotPool; 2],
    running: JoinSet<()>,
    run: R,
}

impl<R, F> Dispatcher<R>
where
    R: FnMut(JobRow) -> F,
    F: Future<Output = ()> + Send + 'static,
{
    /// Dựng dispatcher với giới hạn slot và hàm chạy một job đã claim.
    pub fn new(db: Db, limits: TransferLimits, run: R) -> Self {
        Self {
            db,
            pools: [
                SlotPool::new("download", limits.downloads, limits.small_lane),
                SlotPool::new("upload", limits.uploads, limits.small_lane),
            ],
            running: JoinSet::new(),
            run,
        }
    }

    /// Số transfer đang chạy.
    #[cfg(test)]
    pub fn running(&self) -> usize {
        self.running.len()
    }

    /// Claim job cho mọi slot trống (download trước, rồi upload; FIFO trong từng loại) và khởi
    /// chạy chúng. Trả số job vừa khởi chạy.
    pub async fn fill_slots(&mut self) -> AppResult<usize> {
        let mut started = 0;
        for pool in &self.pools {
            // Giữ mọi slot trống trước, rồi claim cho từng slot theo bộ lọc của nó: slot tệp nhỏ
            // không có job hợp lệ thì các slot chung vẫn được thử. Slot không dùng tự trả về pool.
            let mut slots = Vec::new();
            while let Some(slot) = pool.try_acquire() {
                slots.push(slot);
            }
            for slot in slots {
                let db = self.db.clone();
                let (operation, max_bytes) = (pool.operation, pool.max_bytes(&slot));
                let claimed = tokio::task::spawn_blocking(move || {
                    db.claim_next_job(Some(operation), max_bytes)
                })
                .await
                .map_err(|err| AppError::Message(format!("Tác vụ blocking thất bại: {err}")))??;
                let Some(job) = claimed else {
                    continue;
                };
                tracing::info!(
                    job_id = job.id,
                    file_id = job.file_id,
                    operation,
                    slot = slot.index,
                    bytes_total = job.bytes_total,
                    "transfer started"
                );
                let (job_id, file_id) = (job.id, job.file_id);
                let transfer = (self.run)(job);
                self.running.spawn(async move {
                    let started_at = Instant::now();
                    transfer.await;
                    tracing::info!(
                        job_id,
                        file_id,
                        operation,
                        slot = slot.index,
                        duration_ms = started_at.elapsed().as_millis() as u64,
                        "transfer finished"
                    );
                    drop(slot);
                });
                started += 1;
            }
        }
        Ok(started)
    }

    /// Thu các transfer đã xong; task panic (lỗi lập trình) chỉ được log, job của nó còn
    /// `running` và được `recover_jobs` đưa về `pending` ở lần khởi động sau.
    pub fn reap(&mut self) {
        while let Some(result) = self.running.try_join_next() {
            if let Err(err) = result {
                tracing::error!("transfer task ended abnormally: {err}");
            }
        }
    }

    /// Chờ tới khi một transfer xong hoặc hết `idle`.
    pub async fn wait(&mut self, idle: Duration) {
        if self.running.is_empty() {
            tokio::time::sleep(idle).await;
            return;
        }
        tokio::select! {
            result = self.running.join_next() => {
                if let Some(Err(err)) = result {
                    tracing::error!("transfer task ended abnormally: {err}");
                }
            }
            _ = tokio::time::sleep(idle) => {}
        }
    }

    /// Chạy tới khi không còn job claim được và không còn transfer nào đang chạy (test/benchmark).
    #[cfg(test)]
    pub async fn run_until_idle(&mut self) -> AppResult<()> {
        loop {
            self.reap();
            let started = self.fill_slots().await?;
            if started == 0 && self.running.is_empty() {
                return Ok(());
            }
            self.wait(Duration::from_millis(50)).await;
        }
    }
}

/// Điểm dừng an toàn của một transfer đang chạy: người dùng tạm dừng, hoặc folder của job vừa
/// bị đánh dấu `denied`. Quyền folder được đọc lại từ DB tối đa mỗi `interval`, vì hàm này được
/// hỏi sau mỗi chunk download.
pub struct StopProbe {
    db: Db,
    paused: Arc<AtomicBool>,
    folder_id: i64,
    interval: Duration,
    cached: Mutex<Option<(Instant, bool)>>,
}

impl StopProbe {
    /// Dựng probe cho folder của một job.
    pub fn new(db: Db, paused: Arc<AtomicBool>, folder_id: i64, interval: Duration) -> Self {
        Self {
            db,
            paused,
            folder_id,
            interval,
            cached: Mutex::new(None),
        }
    }

    /// True nếu transfer phải dừng ở điểm an toàn hiện tại.
    pub fn should_stop(&self) -> bool {
        if self.paused.load(Ordering::SeqCst) {
            return true;
        }
        let Ok(mut cached) = self.cached.lock() else {
            return false;
        };
        if let Some((checked_at, denied)) = *cached {
            if checked_at.elapsed() < self.interval {
                return denied;
            }
        }
        let denied = self
            .db
            .folder_access_denied(self.folder_id)
            .unwrap_or(false);
        *cached = Some((Instant::now(), denied));
        denied
    }
}

/// Kết quả xử lý một job bị dừng ở điểm an toàn.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StoppedAs {
    /// Người dùng tạm dừng: job về `pending`, không lỗi.
    Paused,
    /// Folder mất quyền: job về `pending` với thông báo mất quyền; không được claim tới khi có
    /// quyền lại.
    AccessDenied,
    /// Job đã bị tác nhân khác chuyển khỏi `running` (vd. xung đột); giữ nguyên.
    Superseded,
}

/// Đưa job dừng ở điểm an toàn về `pending` mà không tăng `attempt_count` (compare-and-set), chỉ
/// khi task vẫn sở hữu job `owned` đã chụp lúc bắt đầu: job của binding khác trùng rowid không bị
/// đụng tới (`StoppedAs::Superseded`).
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-work-with-a-mapped-folder
pub fn settle_stopped_job(
    db: &Db,
    job: &JobRow,
    owned: &RunningJob,
    access_message: &str,
) -> AppResult<StoppedAs> {
    let denied = db.folder_access_denied(owned.binding.id)?;
    let message = denied.then_some(access_message);
    let changed = db.transition_owned_job(
        owned,
        "pending",
        message,
        job.attempt_count,
        None,
        None,
        None,
    )?;
    Ok(match (changed, denied) {
        (false, _) => StoppedAs::Superseded,
        (true, true) => StoppedAs::AccessDenied,
        (true, false) => StoppedAs::Paused,
    })
}
