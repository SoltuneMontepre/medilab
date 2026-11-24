use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Cấu hình ứng dụng đã lưu (URL Odoo, autostart, debounce/reconcile, ngôn ngữ, trạng thái
/// tạm dừng).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub odoo_url: String,
    pub autostart: bool,
    pub debounce_ms: u64,
    pub reconcile_secs: u64,
    #[serde(default = "default_change_poll_secs")]
    pub change_poll_secs: u64,
    pub paused: bool,
    #[serde(default = "default_locale")]
    pub locale: String,
    /// Số upload chạy song song. Setting ẩn (không có trên UI), áp dụng khi app khởi động; kẹp
    /// `1..=4` lúc dùng (`TransferLimits::from_settings`). `i64` để giá trị gõ tay sai (vd. `-1`)
    /// vẫn đọc được và bị kẹp, thay vì làm hỏng cả JSON settings.
    #[serde(default = "default_transfer_concurrency")]
    pub upload_concurrency: i64,
    /// Số download chạy song song (setting ẩn, như `upload_concurrency`).
    #[serde(default = "default_transfer_concurrency")]
    pub download_concurrency: i64,
    /// Số part của MỘT tệp được PUT cùng lúc (setting ẩn, như `upload_concurrency`).
    #[serde(default = "default_transfer_concurrency")]
    pub part_concurrency: i64,
    /// Thư mục chính trên máy này: folder của các mẫu đang thử được tự gắn vào bên trong. Chưa chọn
    /// thì không tự gắn gì.
    #[serde(default)]
    pub home_folder: Option<String>,
}

/// Mức song song mặc định của các setting concurrency ẩn.
fn default_transfer_concurrency() -> i64 {
    3
}

/// Chu kỳ mặc định (giây) để hỏi server có thay đổi mới hay không.
fn default_change_poll_secs() -> u64 {
    15
}

/// Ngôn ngữ mặc định của giao diện khi chưa có cấu hình lưu sẵn.
fn default_locale() -> String {
    "vi".into()
}

/// URL Odoo mặc định: lấy từ biến môi trường lúc build, localhost cho dev, rỗng cho bản release
/// dùng chung (người dùng mở app từ nút trong MediLab để điền URL).
pub fn default_odoo_url() -> String {
    let fallback = if cfg!(debug_assertions) {
        "http://localhost:8069"
    } else {
        ""
    };
    option_env!("MEDILAB_SYNC_ODOO_URL")
        .unwrap_or(fallback)
        .into()
}

/// Thư mục chính mặc định: `MediLab` trong Documents, hoặc trong thư mục người dùng nếu máy không
/// có Documents.
pub fn default_home_folder() -> Option<String> {
    let dirs = directories::UserDirs::new()?;
    let parent = dirs.document_dir().unwrap_or(dirs.home_dir());
    Some(parent.join("MediLab").to_string_lossy().into_owned())
}

impl Default for AppSettings {
    /// Giá trị mặc định khi chưa từng lưu cấu hình.
    fn default() -> Self {
        Self {
            odoo_url: default_odoo_url(),
            autostart: false,
            debounce_ms: 1000,
            reconcile_secs: 600,
            change_poll_secs: default_change_poll_secs(),
            paused: false,
            locale: default_locale(),
            upload_concurrency: default_transfer_concurrency(),
            download_concurrency: default_transfer_concurrency(),
            part_concurrency: default_transfer_concurrency(),
            home_folder: None,
        }
    }
}

/// Thư mục dữ liệu riêng của app trên hệ điều hành hiện tại; tạo sẵn nếu chưa có.
pub fn data_dir() -> PathBuf {
    let dirs = directories::ProjectDirs::from("com", "medilab", "filesync").expect("project dirs");
    let path = dirs.data_dir().to_path_buf();
    std::fs::create_dir_all(&path).ok();
    path
}

/// Đường dẫn tệp SQLite cục bộ trong thư mục dữ liệu của app.
pub fn db_path() -> PathBuf {
    data_dir().join("sync.sqlite")
}

#[cfg(test)]
mod tests {
    use super::AppSettings;

    /// JSON settings của bản cũ (chưa có field concurrency) vẫn đọc được, nhận giá trị mặc định.
    #[test]
    fn legacy_settings_json_gets_concurrency_defaults() {
        let legacy = r#"{"odoo_url":"http://odoo","autostart":false,"debounce_ms":1000,
            "reconcile_secs":600,"change_poll_secs":15,"paused":false,"locale":"vi"}"#;
        let settings: AppSettings = serde_json::from_str(legacy).unwrap();
        assert_eq!(settings.upload_concurrency, 3);
        assert_eq!(settings.download_concurrency, 3);
        assert_eq!(settings.part_concurrency, 3);
        assert_eq!(settings.home_folder, None);
        assert_eq!(settings.odoo_url, "http://odoo");
    }

    #[test]
    fn default_home_folder_is_medilab_in_the_user_folders() {
        let home = super::default_home_folder().expect("user folders");
        let user = directories::UserDirs::new().unwrap();
        let parent = user.document_dir().unwrap_or(user.home_dir());
        assert_eq!(std::path::Path::new(&home), parent.join("MediLab"));
    }
}
