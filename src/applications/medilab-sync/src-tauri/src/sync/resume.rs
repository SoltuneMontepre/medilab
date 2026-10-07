//! Bỏ tạm dừng transfer mà không bắt lệnh chờ một lượt đối soát đầy đủ: cờ tạm dừng tắt ngay,
//! poll change feed + đối soát chạy nền. Các lần Tiếp tục dồn dập trong lúc một lượt nền đang chạy
//! được gộp thành đúng một lượt chạy tiếp, nên không sinh scan trùng không kiểm soát.
//!
//! Luật vận hành: applications/laboratory-file-sync-application/docs/contract.md#concurrent-transfers

use std::future::Future;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Trigger chạy một việc nền theo yêu cầu, gộp các yêu cầu tới trong lúc việc đó đang chạy.
#[derive(Debug, Clone, Default)]
pub struct RefreshTrigger {
    requested: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
}

impl RefreshTrigger {
    /// Yêu cầu chạy `work` ở nền và trả về ngay. Không có lượt nào đang chạy thì spawn một task;
    /// đang chạy thì chỉ đánh dấu, task hiện tại chạy thêm đúng một lượt sau khi xong.
    pub fn request<F, Fut>(&self, work: F)
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static,
    {
        self.requested.store(true, Ordering::SeqCst);
        if self.running.swap(true, Ordering::SeqCst) {
            return;
        }
        let (requested, running) = (self.requested.clone(), self.running.clone());
        tokio::spawn(async move {
            loop {
                while requested.swap(false, Ordering::SeqCst) {
                    work().await;
                }
                running.store(false, Ordering::SeqCst);
                // Yêu cầu tới đúng lúc vừa thoát vòng: nhận lại quyền chạy nếu chưa ai nhận.
                if !requested.load(Ordering::SeqCst) || running.swap(true, Ordering::SeqCst) {
                    break;
                }
            }
        });
    }

    /// True nếu có lượt nền đang chạy hoặc đang chờ chạy.
    #[cfg(test)]
    pub fn is_active(&self) -> bool {
        self.running.load(Ordering::SeqCst) || self.requested.load(Ordering::SeqCst)
    }
}

/// Tắt cờ tạm dừng để dispatcher claim lại job ngay, rồi xếp `refresh` (poll + đối soát) chạy
/// nền qua `trigger` và trả về ngay — không chờ lượt đối soát đó.
pub async fn resume_transfers<F, Fut>(paused: &AtomicBool, trigger: &RefreshTrigger, refresh: F)
where
    F: Fn() -> Fut + Send + Sync + 'static,
    Fut: Future<Output = ()> + Send + 'static,
{
    paused.store(false, Ordering::SeqCst);
    trigger.request(refresh);
}

#[cfg(test)]
mod tests {
    use super::{resume_transfers, RefreshTrigger};
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::sync::Arc;
    use std::time::Duration;
    use tokio::sync::Notify;

    /// Tiếp tục khi lượt đối soát nền bị giữ lại: lệnh trả về ngay (không chờ đối soát), cờ tạm
    /// dừng đã tắt, lượt nền chạy khi được thả; hai lần Tiếp tục thêm trong lúc đó gộp thành đúng
    /// một lượt chạy tiếp.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn resume_returns_before_a_slow_refresh_and_coalesces_repeats() {
        let paused = AtomicBool::new(true);
        let trigger = RefreshTrigger::default();
        let (started, release) = (Arc::new(Notify::new()), Arc::new(Notify::new()));
        let runs = Arc::new(AtomicUsize::new(0));
        let refresh = {
            let (started, release, runs) = (started.clone(), release.clone(), runs.clone());
            move || {
                let (started, release, runs) = (started.clone(), release.clone(), runs.clone());
                async move {
                    runs.fetch_add(1, Ordering::SeqCst);
                    started.notify_one();
                    release.notified().await;
                }
            }
        };
        tokio::time::timeout(
            Duration::from_millis(500),
            resume_transfers(&paused, &trigger, refresh.clone()),
        )
        .await
        .expect("resume must not wait for the reconcile to finish");
        assert!(
            !paused.load(Ordering::SeqCst),
            "transfers resumed immediately"
        );
        tokio::time::timeout(Duration::from_secs(2), started.notified())
            .await
            .expect("background refresh scheduled");
        resume_transfers(&paused, &trigger, refresh.clone()).await;
        resume_transfers(&paused, &trigger, refresh.clone()).await;
        release.notify_one();
        tokio::time::timeout(Duration::from_secs(2), started.notified())
            .await
            .expect("requests made while running coalesce into one more run");
        release.notify_one();
        for _ in 0..400 {
            if !trigger.is_active() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        assert!(!trigger.is_active());
        assert_eq!(runs.load(Ordering::SeqCst), 2);
    }
}
