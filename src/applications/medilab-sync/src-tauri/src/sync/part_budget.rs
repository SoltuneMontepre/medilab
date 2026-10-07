//! Ngân sách bộ nhớ dùng chung cho buffer part đang đọc/đang PUT của MỌI upload trong tiến trình.
//! Tính theo byte (đơn vị 1 MiB), không theo số part, vì part size do server cấp và được lưu theo
//! từng job. Một part lấy đủ đơn vị TRƯỚC khi cấp phát/đọc buffer và giữ tới khi PUT của nó xong
//! hoặc bị hủy.
//!
//! Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#direct-minio-upload

use crate::error::{AppError, AppResult};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

/// Một đơn vị ngân sách: 1 MiB.
pub const BUDGET_UNIT_BYTES: usize = 1024 * 1024;
/// Ngân sách mặc định của app: 128 MiB buffer part cho mọi upload cộng lại.
pub const DEFAULT_PART_BUDGET_MIB: usize = 128;

/// Ngân sách buffer part dùng chung (một instance cho cả app, do `EngineHandle` sở hữu).
#[derive(Debug)]
pub struct PartBudget {
    permits: Arc<Semaphore>,
    total_mib: usize,
    peak_mib: AtomicUsize,
}

/// Phần ngân sách một part đang giữ; trả lại khi bị drop.
#[derive(Debug)]
pub struct PartPermit {
    _permit: OwnedSemaphorePermit,
}

impl PartBudget {
    /// Ngân sách `total_mib` MiB.
    pub fn new(total_mib: usize) -> Arc<Self> {
        Arc::new(Self {
            permits: Arc::new(Semaphore::new(total_mib)),
            total_mib,
            peak_mib: AtomicUsize::new(0),
        })
    }

    /// Số đơn vị (MiB, làm tròn lên, tối thiểu 1) mà một buffer `bytes` byte cần.
    pub fn units_for(bytes: usize) -> usize {
        bytes.div_ceil(BUDGET_UNIT_BYTES).max(1)
    }

    /// Tổng ngân sách (MiB).
    pub fn total_mib(&self) -> usize {
        self.total_mib
    }

    /// Mức đang dùng (MiB).
    #[cfg(test)]
    pub fn in_use_mib(&self) -> usize {
        self.total_mib - self.permits.available_permits()
    }

    /// Mức dùng cao nhất (MiB) đã quan sát được.
    pub fn peak_mib(&self) -> usize {
        self.peak_mib.load(Ordering::SeqCst)
    }

    /// Lỗi ngay nếu một part `bytes` byte cần nhiều hơn toàn bộ ngân sách — chờ semaphore khi đó
    /// sẽ không bao giờ xong. Lỗi cấu hình/protocol, không phải lỗi mạng.
    pub fn ensure_fits(&self, bytes: usize) -> AppResult<()> {
        let units = Self::units_for(bytes);
        if units > self.total_mib {
            return Err(AppError::Message(format!(
                "Kích thước part {units} MiB vượt ngân sách bộ nhớ upload {} MiB",
                self.total_mib
            )));
        }
        Ok(())
    }

    /// Chờ đủ ngân sách cho một buffer `bytes` byte (sau `ensure_fits`).
    pub async fn acquire(&self, bytes: usize) -> AppResult<PartPermit> {
        self.ensure_fits(bytes)?;
        let units = Self::units_for(bytes);
        let permit = self
            .permits
            .clone()
            .acquire_many_owned(units as u32)
            .await
            .map_err(|_| AppError::Message("Ngân sách bộ nhớ upload đã đóng".into()))?;
        let in_use = self.total_mib - self.permits.available_permits();
        self.peak_mib.fetch_max(in_use, Ordering::SeqCst);
        Ok(PartPermit { _permit: permit })
    }
}

#[cfg(test)]
mod tests {
    use super::{PartBudget, BUDGET_UNIT_BYTES};

    /// Làm tròn lên theo MiB, part rỗng vẫn tốn một đơn vị.
    #[test]
    fn units_round_up_to_whole_mebibytes() {
        assert_eq!(PartBudget::units_for(0), 1);
        assert_eq!(PartBudget::units_for(1), 1);
        assert_eq!(PartBudget::units_for(BUDGET_UNIT_BYTES), 1);
        assert_eq!(PartBudget::units_for(BUDGET_UNIT_BYTES + 1), 2);
        assert_eq!(PartBudget::units_for(16 * BUDGET_UNIT_BYTES), 16);
    }
}
