use thiserror::Error;

/// Xóa phần query (`?...`) khỏi URL trong một chuỗi lỗi, để không lộ presigned URL/credential ra log.
pub fn redact_url_queries(text: &str) -> String {
    let mut out = String::new();
    for (index, chunk) in text.split('?').enumerate() {
        if index == 0 {
            out.push_str(chunk);
            continue;
        }
        if let Some(end) = chunk.find(|ch: char| ch.is_whitespace() || ch == ')') {
            out.push_str(&chunk[end..]);
        }
    }
    out
}

/// Chỉ true khi CHÍNH ODOO trả HTTP 401 cho API key của thiết bị (`ApiClient::map_response` là
/// nơi duy nhất sinh `Unauthenticated`). Có kiểu, không so chuỗi: 401 của MinIO/presigned URL,
/// ONLYOFFICE hay updater, lỗi mạng, 403/404/5xx, hoặc keyring không đọc được đều KHÔNG làm cả
/// phiên Odoo hết hạn.
pub fn is_odoo_auth_failure(err: &AppError) -> bool {
    matches!(err, AppError::Unauthenticated)
}

/// Loại lỗi dùng chung toàn app: bọc lỗi IO/SQLite/HTTP/keyring/serde thành một kiểu trả về
/// duy nhất cho Tauri command.
#[derive(Debug, Error)]
pub enum AppError {
    #[error("{0}")]
    Message(String),
    /// Odoo trả 401: API key hết hạn/bị thu hồi hoặc thiết bị bị thu hồi. Cần đăng nhập lại.
    #[error("Phiên đăng nhập đã hết hạn hoặc thiết bị đã bị thu hồi")]
    Unauthenticated,
    /// Tiến trình này chưa có API key (chưa đăng nhập, hoặc chưa khôi phục được phiên). Lỗi CỤC
    /// BỘ, không phải server từ chối — không bao giờ làm phiên "hết hạn".
    #[error("Chưa đăng nhập")]
    NotLoggedIn,
    /// Server trả 403/404: mất quyền hoặc tài nguyên không tồn tại (server cố ý không phân biệt).
    /// Kiểu riêng để engine nhận ra mất quyền thư mục mà không phải so chuỗi thông báo.
    #[error("Không có quyền hoặc không tìm thấy tài nguyên ({0})")]
    Forbidden(u16),
    #[error("Không tìm thấy thư mục đồng bộ")]
    FolderNotFound,
    /// Người dùng tạm dừng đồng bộ giữa lúc job đang truyền: job dừng ở ranh giới part/chunk kế
    /// tiếp và quay về hàng đợi. Không phải lỗi, không tính vào số lần thử.
    #[error("Đồng bộ đang tạm dừng")]
    Paused,
    /// Task không còn sở hữu job đang chạy: thư mục bị gỡ, rowid job/tệp/folder đã được tái dùng
    /// cho binding khác, hoặc job đã bị chuyển khỏi `running`. Không phải lỗi của job: task dừng
    /// và không ghi gì thêm vào DB.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    #[error("Job không còn thuộc lượt chạy này")]
    Superseded,
    /// MinIO/S3 từ chối presigned URL (403), thường vì URL đã hết hạn trước khi request tới nơi.
    /// Đáng thử lại với URL mới; không phải mất quyền phía Odoo (quyền được kiểm lúc presign).
    #[error("URL tải trực tiếp bị storage từ chối hoặc đã hết hạn ({0})")]
    PresignedUrlRejected(u16),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
    #[error("{0}")]
    Http(String),
    /// Lỗi truyền dẫn mạng (timeout, không kết nối được, gửi request/đọc body thất bại) — tách
    /// khỏi `Http` theo loại lỗi của reqwest để chính sách retry không phải so chuỗi.
    #[error("{0}")]
    Connectivity(String),
    #[error("Không lưu được phiên đăng nhập an toàn")]
    Keyring(#[from] keyring::Error),
    #[error(transparent)]
    Serde(#[from] serde_json::Error),
}

impl From<reqwest::Error> for AppError {
    /// Chuyển lỗi reqwest thành `AppError::Connectivity` nếu là lỗi truyền dẫn (timeout, kết nối,
    /// gửi request, đọc/ghi body), ngược lại `AppError::Http`; message đã xóa query khỏi URL.
    fn from(err: reqwest::Error) -> Self {
        let message = redact_url_queries(&err.to_string());
        if err.is_timeout() || err.is_connect() || err.is_request() || err.is_body() {
            AppError::Connectivity(message)
        } else {
            AppError::Http(message)
        }
    }
}

impl From<AppError> for String {
    /// Chuyển `AppError` thành chuỗi message, dùng khi trả lỗi qua Tauri command (`Result<T, String>`).
    fn from(value: AppError) -> Self {
        value.to_string()
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[cfg(test)]
mod tests {
    use super::{is_odoo_auth_failure, redact_url_queries, AppError};

    /// Query chứa `X-Amz-Signature` phải bị xóa khỏi message lỗi kiểu reqwest.
    #[test]
    fn redacts_presigned_query_from_reqwest_style_message() {
        let raw = "error sending request for url (http://localhost:29000/medilab/sync/1/abc?X-Amz-Signature=secret)";
        let redacted = redact_url_queries(raw);
        assert_eq!(
            redacted,
            "error sending request for url (http://localhost:29000/medilab/sync/1/abc)"
        );
        assert!(!redacted.contains("Signature"));
        assert!(!redacted.contains('?'));
    }

    /// Khóa object dạng hex chứa chuỗi "401" không được coi nhầm là lỗi xác thực Odoo.
    #[test]
    fn hex_object_key_is_not_odoo_auth_failure() {
        let minio = AppError::Message(
            "Tải phần thất bại (403 Forbidden) http://localhost:29000/medilab/sync/20/ea914caef50e4014a6f332d664b7db0c"
                .into(),
        );
        assert!(!is_odoo_auth_failure(&minio));
        assert!(is_odoo_auth_failure(&AppError::Unauthenticated));
    }

    /// Chỉ 401 có kiểu từ Odoo mới làm hết phiên: 401 dạng chuỗi từ dịch vụ khác (MinIO presigned,
    /// ONLYOFFICE, updater), chưa có key cục bộ, 403/404, 5xx, timeout/mất mạng đều không.
    #[test]
    fn only_typed_odoo_401_expires_the_session() {
        for err in [
            AppError::Message("Tải phần thất bại (401 Unauthorized)".into()),
            AppError::Message("Tải xuống thất bại (401 Unauthorized) http://minio/x".into()),
            AppError::Http(
                "HTTP status client error (401 Unauthorized) for url (http://minio/x)".into(),
            ),
            AppError::Http("error sending request: connection refused".into()),
            AppError::Http("operation timed out".into()),
            AppError::Message("500: Internal Server Error".into()),
            AppError::Message("503: Service Unavailable".into()),
            AppError::Forbidden(403),
            AppError::Forbidden(404),
            AppError::NotLoggedIn,
        ] {
            assert!(!is_odoo_auth_failure(&err), "{err}");
        }
    }
}
