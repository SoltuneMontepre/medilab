use std::time::Duration;
use tokio::sync::mpsc::{channel, Receiver, Sender};
use tokio::time::Instant;

/// Khoảng thời gian gộp (debounce/throttle) sự kiện trạng thái mặc định: 250ms (tương đương tối đa 4 Hz).
pub const DEFAULT_STATUS_COALESCE_INTERVAL: Duration = Duration::from_millis(250);

/// Bộ quản lý gửi tín hiệu làm mới trạng thái qua bounded channel một phần tử.
#[derive(Clone, Debug)]
pub struct StatusEventHub {
    tx: Sender<()>,
}

impl StatusEventHub {
    /// Khởi tạo một hub mới kèm đầu nhận của channel (đệm 1 phần tử).
    pub fn new() -> (Self, Receiver<()>) {
        let (tx, rx) = channel(1);
        (Self { tx }, rx)
    }

    /// Gửi tín hiệu thông báo trạng thái thay đổi không chặn luồng gọi.
    /// Nếu channel đã đầy (đang có một tín hiệu chờ xử lý), tín hiệu mới được bỏ qua an toàn
    /// vì snapshot sẽ luôn lấy dữ liệu mới nhất tại thời điểm gộp xong.
    pub fn notify(&self) {
        let _ = self.tx.try_send(());
    }
}

/// Vòng lặp nền điều phối việc phát sự kiện trạng thái:
/// - Tín hiệu đầu tiên phát ngay lập tức (không chờ).
/// - Các tín hiệu kế tiếp trong cửa sổ `interval` được gộp lại.
/// - Hoạt động liên tục sẽ phát snapshot với tần số tối đa 1 lần mỗi `interval` (4 Hz).
/// - Dữ liệu snapshot chỉ được truy vấn và dựng thông qua `emit_fn` sau khi gộp xong.
pub async fn run_status_coalescer<F, Fut>(mut rx: Receiver<()>, interval: Duration, mut emit_fn: F)
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = ()>,
{
    let mut last_emitted: Option<Instant> = None;

    while rx.recv().await.is_some() {
        // Xả sạch các tín hiệu đang tồn đọng trong channel
        while rx.try_recv().is_ok() {}

        if let Some(last) = last_emitted {
            let elapsed = last.elapsed();
            if elapsed < interval {
                let remaining = interval - elapsed;
                tokio::time::sleep(remaining).await;
                // Xả tiếp các tín hiệu dồn dập tới trong thời gian chờ
                while rx.try_recv().is_ok() {}
            }
        }

        emit_fn().await;
        last_emitted = Some(Instant::now());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    /// Tín hiệu đầu tiên khi hệ thống rảnh rỗi phải được phát ngay lập tức mà không phải chờ.
    #[tokio::test(start_paused = true)]
    async fn first_signal_emits_promptly() {
        let (hub, rx) = StatusEventHub::new();
        let emit_count = Arc::new(AtomicUsize::new(0));
        let emit_count_clone = emit_count.clone();

        let handle = tokio::spawn(run_status_coalescer(
            rx,
            DEFAULT_STATUS_COALESCE_INTERVAL,
            move || {
                let count = emit_count_clone.clone();
                async move {
                    count.fetch_add(1, Ordering::SeqCst);
                }
            },
        ));

        hub.notify();
        tokio::task::yield_now().await;

        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            1,
            "tín hiệu đầu tiên phải phát ngay lập tức"
        );

        handle.abort();
    }

    /// Hai mươi tín hiệu gửi dồn dập trong cửa sổ 250ms chỉ tạo đúng một snapshot gộp bổ sung.
    #[tokio::test(start_paused = true)]
    async fn burst_signals_coalesced_within_250ms() {
        let (hub, rx) = StatusEventHub::new();
        let emit_count = Arc::new(AtomicUsize::new(0));
        let emit_count_clone = emit_count.clone();

        let handle = tokio::spawn(run_status_coalescer(
            rx,
            DEFAULT_STATUS_COALESCE_INTERVAL,
            move || {
                let count = emit_count_clone.clone();
                async move {
                    count.fetch_add(1, Ordering::SeqCst);
                }
            },
        ));

        // Tín hiệu 1 phát ngay lập tức
        hub.notify();
        tokio::task::yield_now().await;
        assert_eq!(emit_count.load(Ordering::SeqCst), 1);

        // 20 tín hiệu dồn dập trong lúc chưa hết 250ms
        for _ in 0..20 {
            hub.notify();
            tokio::task::yield_now().await;
        }

        // Chờ 100ms: vẫn nằm trong cửa sổ debounce, chưa được phát thêm
        tokio::time::advance(Duration::from_millis(100)).await;
        tokio::task::yield_now().await;
        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            1,
            "không được phát thêm trước khi hết 250ms"
        );

        // Chờ tiếp 150ms (đủ 250ms kể từ lần phát 1)
        tokio::time::advance(Duration::from_millis(150)).await;
        tokio::task::yield_now().await;
        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            2,
            "phải phát đúng một snapshot gộp tại mốc 250ms"
        );

        // Tiến thêm 500ms nữa mà không có tín hiệu mới: số lần phát giữ nguyên 2
        tokio::time::advance(Duration::from_millis(500)).await;
        tokio::task::yield_now().await;
        assert_eq!(emit_count.load(Ordering::SeqCst), 2);

        handle.abort();
    }

    /// Hoạt động liên tục được giới hạn tối đa 4 lần phát mỗi giây (4 Hz).
    #[tokio::test(start_paused = true)]
    async fn continuous_signals_capped_at_4hz() {
        let (hub, rx) = StatusEventHub::new();
        let emit_count = Arc::new(AtomicUsize::new(0));
        let emit_count_clone = emit_count.clone();

        let handle = tokio::spawn(run_status_coalescer(
            rx,
            DEFAULT_STATUS_COALESCE_INTERVAL,
            move || {
                let count = emit_count_clone.clone();
                async move {
                    count.fetch_add(1, Ordering::SeqCst);
                }
            },
        ));

        // Tín hiệu đầu tiên phát ngay lập tức tại t=0
        hub.notify();
        tokio::task::yield_now().await;
        assert_eq!(emit_count.load(Ordering::SeqCst), 1);

        // Gửi liên tục mỗi 10ms trong 1000ms tiếp theo (100 * 10ms = 1 giây)
        for _ in 0..100 {
            tokio::time::advance(Duration::from_millis(10)).await;
            hub.notify();
            tokio::task::yield_now().await;
        }

        // Trong 1 giây hoạt động dồn dập sau lần phát đầu, số lần phát thêm là 4 (mỗi 250ms), tổng cộng 5 lần (4 Hz)
        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            5,
            "hoạt động liên tục trong 1s chỉ được phát tối đa 5 lần (4 Hz)"
        );

        handle.abort();
    }

    /// Tín hiệu đơn lẻ đến sau một khoảng thời gian im lặng phải được phát ngay lập tức.
    #[tokio::test(start_paused = true)]
    async fn isolated_signal_after_quiet_period_emits_promptly() {
        let (hub, rx) = StatusEventHub::new();
        let emit_count = Arc::new(AtomicUsize::new(0));
        let emit_count_clone = emit_count.clone();

        let handle = tokio::spawn(run_status_coalescer(
            rx,
            DEFAULT_STATUS_COALESCE_INTERVAL,
            move || {
                let count = emit_count_clone.clone();
                async move {
                    count.fetch_add(1, Ordering::SeqCst);
                }
            },
        ));

        hub.notify();
        tokio::task::yield_now().await;
        assert_eq!(emit_count.load(Ordering::SeqCst), 1);

        // Im lặng 10 giây
        tokio::time::advance(Duration::from_secs(10)).await;
        tokio::task::yield_now().await;
        assert_eq!(emit_count.load(Ordering::SeqCst), 1);

        // Tín hiệu độc lập mới phát ngay
        hub.notify();
        tokio::task::yield_now().await;
        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            2,
            "tín hiệu sau khoảng im lặng phải phát ngay"
        );

        handle.abort();
    }

    /// Channel đầy không bao giờ làm nghẽn hoặc lỗi bên gửi.
    #[test]
    fn full_channel_never_blocks_producer() {
        let (hub, _rx) = StatusEventHub::new();
        // Gửi 1000 lần vào channel có buffer 1
        for _ in 0..1000 {
            hub.notify();
        }
    }

    /// Snapshot phát ra phản ánh giá trị mới nhất tại thời điểm gộp, không bị kẹt ở giá trị cũ.
    #[tokio::test(start_paused = true)]
    async fn latest_state_emitted_after_coalescing() {
        let (hub, rx) = StatusEventHub::new();
        let state = Arc::new(AtomicUsize::new(1));
        let state_clone = state.clone();
        let emitted_val = Arc::new(AtomicUsize::new(0));
        let emitted_val_clone = emitted_val.clone();

        let handle = tokio::spawn(run_status_coalescer(
            rx,
            DEFAULT_STATUS_COALESCE_INTERVAL,
            move || {
                let s = state_clone.clone();
                let out = emitted_val_clone.clone();
                async move {
                    out.store(s.load(Ordering::SeqCst), Ordering::SeqCst);
                }
            },
        ));

        // Lần 1: state = 1 phát ngay
        hub.notify();
        tokio::task::yield_now().await;
        assert_eq!(emitted_val.load(Ordering::SeqCst), 1);

        // Trong lúc đang trong cửa sổ 250ms, state liên tục tăng lên 2, 3, 4, 99
        for val in [2, 3, 4, 99] {
            state.store(val, Ordering::SeqCst);
            hub.notify();
            tokio::time::advance(Duration::from_millis(20)).await;
            tokio::task::yield_now().await;
        }

        // Chờ đến hết cửa sổ 250ms
        tokio::time::advance(Duration::from_millis(200)).await;
        tokio::task::yield_now().await;

        // Snapshot thứ 2 phải mang giá trị mới nhất là 99
        assert_eq!(
            emitted_val.load(Ordering::SeqCst),
            99,
            "snapshot gộp phải đọc trạng thái mới nhất"
        );

        handle.abort();
    }
}
