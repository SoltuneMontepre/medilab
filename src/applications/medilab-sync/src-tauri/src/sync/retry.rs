use crate::error::AppError;

/// Thời gian chờ (giây) trước lần thử lại thứ `attempt`, tăng dần rồi chặn ở 60s, cộng jitter
/// ngẫu nhiên tới 1/4 mức nền để nhiều job song song lỗi cùng lúc không thử lại cùng một giây.
pub fn backoff_secs(attempt: i64) -> i64 {
    let caps = [1_i64, 2, 4, 8, 15, 30, 60];
    let idx = attempt.clamp(1, caps.len() as i64) as usize - 1;
    let base = caps[idx];
    base + random_jitter(base / 4)
}

/// Số nguyên ngẫu nhiên trong `0..=max` (0 nếu `max <= 0`).
fn random_jitter(max: i64) -> i64 {
    if max <= 0 {
        return 0;
    }
    (uuid::Uuid::new_v4().as_u128() % (max as u128 + 1)) as i64
}

/// Số lần thử tối đa cho lỗi server/storage/ứng dụng đáng thử lại (5xx, presigned bị từ chối, tệp
/// đổi trong lúc upload…). Lỗi kết nối mạng không bị giới hạn: máy PTN có thể mất mạng lâu.
pub const MAX_SERVER_ERROR_ATTEMPTS: i64 = 20;

/// True nếu lỗi là lỗi kết nối mạng thật sự (timeout, không kết nối được, mất kết nối giữa
/// chừng), theo loại lỗi chứ không theo chuỗi. Response HTTP của server/storage (5xx, 403, 409),
/// lỗi toàn vẹn và lỗi IO cục bộ (quyền, đĩa đầy) không phải lỗi kết nối.
pub fn is_connectivity_error(err: &AppError) -> bool {
    match err {
        AppError::Connectivity(_) => true,
        AppError::Io(io) => matches!(
            io.kind(),
            std::io::ErrorKind::TimedOut
                | std::io::ErrorKind::ConnectionReset
                | std::io::ErrorKind::ConnectionAborted
                | std::io::ErrorKind::ConnectionRefused
                | std::io::ErrorKind::NotConnected
                | std::io::ErrorKind::BrokenPipe
                | std::io::ErrorKind::UnexpectedEof
        ),
        _ => false,
    }
}

/// Trạng thái kế tiếp của một job vừa lỗi.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RetryDecision {
    /// `retry_wait` hoặc `failed`.
    pub status: &'static str,
    pub retry_at: Option<i64>,
    /// Thông báo lỗi lưu vào job (đã xóa query của URL).
    pub message: String,
}

/// Quyết định trạng thái sau lần thử thứ `attempt` (đếm cả lần vừa lỗi) cho một lỗi `err` mà
/// caller đã phân loại là `retryable` hay không:
///
/// - không retry được → `failed`;
/// - lỗi kết nối → `retry_wait` vô hạn;
/// - lỗi server/storage → `retry_wait` tới lần thứ `MAX_SERVER_ERROR_ATTEMPTS`, rồi `failed` với
///   "Đã thử {n} lần: {lỗi}".
pub fn next_status(err: &AppError, attempt: i64, retryable: bool, now: i64) -> RetryDecision {
    let message = crate::error::redact_url_queries(&err.to_string());
    if !retryable {
        return RetryDecision {
            status: "failed",
            retry_at: None,
            message,
        };
    }
    if !is_connectivity_error(err) && attempt >= MAX_SERVER_ERROR_ATTEMPTS {
        return RetryDecision {
            status: "failed",
            retry_at: None,
            message: format!("Đã thử {attempt} lần: {message}"),
        };
    }
    RetryDecision {
        status: "retry_wait",
        retry_at: Some(now + backoff_secs(attempt)),
        message,
    }
}

/// True nếu lỗi có khả năng tạm thời và đáng thử lại job (xem `api::is_retryable`); lỗi hết
/// phiên/xác thực không khớp bất kỳ nhánh nào nên mặc định không đáng thử lại — đây là chính
/// sách retry kỹ thuật chung, không phải một luật nghiệp vụ cụ thể.
pub fn is_retryable(err: &AppError) -> bool {
    crate::api::is_retryable(err)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Thời gian chờ phải tăng dần theo số lần thử và bị chặn ở mức trần.
    #[test]
    fn backoff_grows_and_caps() {
        assert_eq!(backoff_secs(1), 1);
        assert!(backoff_secs(2) >= 2);
        for _ in 0..200 {
            let capped = backoff_secs(20);
            assert!((60..=75).contains(&capped), "{capped}");
            assert!((15..=18).contains(&backoff_secs(5)));
        }
    }

    /// Jitter phải thực sự ngẫu nhiên để các job lỗi cùng lúc không thử lại cùng một giây.
    #[test]
    fn backoff_jitter_spreads_retries() {
        let values: std::collections::HashSet<i64> = (0..200).map(|_| backoff_secs(20)).collect();
        assert!(values.len() > 1, "no jitter: {values:?}");
    }

    /// Lỗi kết nối được nhận theo loại (variant/`ErrorKind`), không phải response của server hay
    /// lỗi cục bộ.
    #[test]
    fn classifies_connectivity_by_error_kind() {
        use std::io::{Error, ErrorKind};
        assert!(is_connectivity_error(&AppError::Connectivity("x".into())));
        for kind in [
            ErrorKind::TimedOut,
            ErrorKind::ConnectionReset,
            ErrorKind::UnexpectedEof,
        ] {
            assert!(
                is_connectivity_error(&AppError::Io(Error::from(kind))),
                "{kind:?}"
            );
        }
        for err in [
            AppError::Io(Error::from(ErrorKind::PermissionDenied)),
            AppError::Message("503 Service Unavailable".into()),
            AppError::Message("Tải phần thất bại (500 Internal Server Error)".into()),
            AppError::PresignedUrlRejected(403),
            AppError::Message("Tệp đã thay đổi trong lúc tải lên, sẽ thử lại".into()),
            AppError::Message("409: session expired".into()),
            AppError::Http("builder error".into()),
            AppError::Forbidden(403),
        ] {
            assert!(!is_connectivity_error(&err), "{err:?}");
        }
    }

    /// Biên trần retry: lỗi server lần 19 còn chờ, lần 20 thành `failed` kèm số lần thử; lỗi
    /// kết nối lần 50 vẫn chờ; lỗi không retry được thành `failed` ngay.
    #[test]
    fn server_errors_stop_at_the_ceiling_but_connectivity_retries_forever() {
        let server = AppError::Message("503 Service Unavailable".into());
        let decision = next_status(&server, MAX_SERVER_ERROR_ATTEMPTS - 1, true, 1000);
        assert_eq!(decision.status, "retry_wait");
        assert!(decision.retry_at.unwrap() > 1000);
        let decision = next_status(&server, MAX_SERVER_ERROR_ATTEMPTS, true, 1000);
        assert_eq!(decision.status, "failed");
        assert_eq!(decision.retry_at, None);
        assert_eq!(decision.message, "Đã thử 20 lần: 503 Service Unavailable");
        let offline = AppError::Connectivity("operation timed out".into());
        assert_eq!(next_status(&offline, 50, true, 1000).status, "retry_wait");
        let semantic = AppError::Forbidden(403);
        let decision = next_status(&semantic, 1, false, 1000);
        assert_eq!((decision.status, decision.retry_at), ("failed", None));
    }

    /// Lỗi truyền dẫn thật của reqwest (cổng không có ai nghe) thành `Connectivity`, không `Http`.
    #[tokio::test]
    async fn reqwest_transport_errors_map_to_connectivity() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let err: AppError = reqwest::Client::new()
            .get(format!("http://127.0.0.1:{port}/"))
            .send()
            .await
            .unwrap_err()
            .into();
        assert!(matches!(err, AppError::Connectivity(_)), "{err:?}");
        assert!(is_connectivity_error(&err));
        assert!(is_retryable(&err));
    }

    /// Lỗi mạng/tạm thời đáng thử lại; lỗi xác thực/quyền/toàn vẹn dữ liệu thì không.
    #[test]
    fn classifies_retryable_errors() {
        assert!(is_retryable(&AppError::Message("timeout from 503".into())));
        assert!(is_retryable(&AppError::Message("502 Bad Gateway".into())));
        assert!(!is_retryable(&AppError::Unauthenticated));
        assert!(!is_retryable(&AppError::Message("403 Forbidden".into())));
        assert!(!is_retryable(&AppError::Message("401 Unauthorized".into())));
        assert!(!is_retryable(&AppError::Message(
            "Toàn vẹn tải xuống thất bại: SHA-256 không khớp".into()
        )));
        assert!(is_retryable(&AppError::Message(
            "Tệp đang được chương trình khác sử dụng, sẽ thử thay thế lại".into()
        )));
        assert!(is_retryable(&AppError::Message("connection reset".into())));
    }
}
