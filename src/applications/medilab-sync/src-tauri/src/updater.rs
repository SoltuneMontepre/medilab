//! Kiểm tra cập nhật nền.
//!
//! Lấy manifest cập nhật từ endpoint backend Odoo
//! `{odoo_url}/medilab/api/v1/updates/{target}/{arch}/{version}` lúc khởi động
//! và mỗi khi frontend gọi `check_update`. Lượt kiểm chỉ best-effort: mọi thất
//! bại được log và âm thầm bỏ qua để một update server hỏng không bao giờ
//! ảnh hưởng tới sync.
//!
//! Signing keys are managed by the release owner; the desktop never replaces them.

use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::AppHandle;
use tauri_plugin_updater::UpdaterExt;
use tracing::{info, warn};

/// Cờ ở mức phiên chạy, đặt khi người dùng bấm "Nhắc lại sau".
/// Ngăn dialog nhắc nhở lặp lại trong cùng vòng đời tiến trình.
static UPDATE_DISMISSED: AtomicBool = AtomicBool::new(false);

/// Thông tin bản cập nhật đang chờ, trả về cho frontend.
#[derive(Debug, Clone, Serialize)]
pub struct UpdateAvailable {
    pub current_version: String,
    pub new_version: String,
    pub notes: Option<String>,
    pub pub_date: Option<String>,
}

/// Đánh dấu bản cập nhật đang chờ là đã bỏ qua cho phiên chạy này.
pub fn dismiss_update() {
    UPDATE_DISMISSED.store(true, Ordering::Relaxed);
}

/// Trả về `true` nếu người dùng đã bỏ qua nhắc cập nhật trong phiên chạy này.
pub fn is_update_dismissed() -> bool {
    UPDATE_DISMISSED.load(Ordering::Relaxed)
}

/// Ghi đè channel lúc build. Mặc định "stable".
/// Với bản build test, đặt MEDILAB_SYNC_UPDATE_CHANNEL=test lúc compile.
const UPDATE_CHANNEL: &str = match option_env!("MEDILAB_SYNC_UPDATE_CHANNEL") {
    Some(channel) => channel,
    None => "stable",
};

/// Dựng URL endpoint kiểm tra cập nhật theo target/arch/version hiện tại, kèm channel nếu khác
/// "stable".
fn build_endpoint_url(
    odoo_url: &str,
    target: &str,
    arch: &str,
    current: &str,
) -> crate::error::AppResult<String> {
    if [target, arch, current].iter().any(|part| {
        part.is_empty()
            || !part
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_'))
    }) {
        return Err(crate::error::AppError::Message(
            "Thông tin bản cập nhật không hợp lệ".into(),
        ));
    }
    let mut url = crate::server_url::endpoint(
        odoo_url,
        &format!("medilab/api/v1/updates/{target}/{arch}/{current}"),
    )?;
    if UPDATE_CHANNEL != "stable" {
        url.query_pairs_mut().append_pair("channel", UPDATE_CHANNEL);
    }
    Ok(url.into())
}

/// Ánh xạ `std::env::consts::OS` sang chuỗi target mà update server mong đợi.
///
/// Bản thân Tauri dùng "darwin" cho macOS ở bên trong, khớp quy ước của biến template
/// `{{target}}` riêng của `tauri-plugin-updater`.
fn os_to_target(os: &str) -> &'static str {
    match os {
        "windows" => "windows",
        "macos" => "darwin",
        _ => "linux",
    }
}

/// Kiểm tra bản mới hơn trên endpoint cập nhật của Odoo.
///
/// Trả về `Some(UpdateAvailable)` khi có bản mới hơn, `None` nếu không (kể cả khi lỗi mạng hoặc
/// lỗi parse).
///
/// # Lỗi
/// Mọi lỗi được log ở mức `warn` rồi chuyển thành `None` để một lượt kiểm thất bại không bao giờ
/// lan tới caller.
pub async fn check_for_update(app: &AppHandle, odoo_url: &str) -> Option<UpdateAvailable> {
    if odoo_url.is_empty() {
        return None;
    }

    let target = os_to_target(std::env::consts::OS);
    let arch = std::env::consts::ARCH;
    let current = app.package_info().version.to_string();

    let endpoint = build_endpoint_url(odoo_url, target, arch, &current)
        .map_err(|err| warn!("Invalid updater endpoint: {err}"))
        .ok()?;

    let updater = match app
        .updater_builder()
        .header(
            "User-Agent",
            concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")),
        )
        .map_err(|err| warn!("Invalid updater header: {err}"))
        .ok()?
        .endpoints(vec![endpoint
            .parse()
            .map_err(|err| warn!("Invalid updater endpoint '{endpoint}': {err}"))
            .ok()?])
        .map_err(|err| warn!("Failed to configure updater endpoints: {err}"))
        .ok()?
        .build()
    {
        Ok(u) => u,
        Err(err) => {
            warn!("Failed to build updater: {err}");
            return None;
        }
    };

    match updater.check().await {
        Ok(Some(update)) => {
            info!("Update available: {} → {}", current, update.version);
            Some(UpdateAvailable {
                current_version: current,
                new_version: update.version.clone(),
                notes: update.body.clone(),
                pub_date: update.date.map(|d| d.to_string()),
            })
        }
        Ok(None) => {
            info!("No update available (current: {current})");
            None
        }
        Err(err) => {
            warn!("Update check failed: {err}");
            None
        }
    }
}

/// Tải và cài đặt bản cập nhật đang chờ.
///
/// Việc tạm dừng engine đồng bộ trước khi gọi hàm này là trách nhiệm của caller. Tiến trình sẽ bị
/// thay thế bởi installer khi thành công. Khi lỗi, hàm trả về `Err` để frontend hiện thông báo.
pub async fn download_and_install(app: &AppHandle, odoo_url: &str) -> Result<(), String> {
    if odoo_url.is_empty() {
        return Err("Chưa cấu hình URL máy chủ".into());
    }

    let target = os_to_target(std::env::consts::OS);
    let arch = std::env::consts::ARCH;
    let current = app.package_info().version.to_string();

    let endpoint = build_endpoint_url(odoo_url, target, arch, &current).map_err(String::from)?;

    let updater = app
        .updater_builder()
        .header(
            "User-Agent",
            concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")),
        )
        .map_err(|err| format!("Không thể cấu hình cập nhật: {err}"))?
        .endpoints(vec![endpoint
            .parse()
            .map_err(|err| format!("URL cập nhật không hợp lệ: {err}"))?])
        .map_err(|err| format!("Không thể cấu hình trình cập nhật: {err}"))?
        .build()
        .map_err(|err| format!("Không thể khởi tạo trình cập nhật: {err}"))?;

    let update = updater
        .check()
        .await
        .map_err(|err| format!("Không thể kiểm tra cập nhật: {err}"))?
        .ok_or_else(|| "Không tìm thấy bản cập nhật mới".to_string())?;

    update
        .download_and_install(|_chunk_len, _total| {}, || {})
        .await
        .map_err(|err| format!("Cài đặt cập nhật thất bại: {err}"))?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{dismiss_update, is_update_dismissed, os_to_target, UPDATE_DISMISSED};
    use std::sync::atomic::Ordering;

    /// Đặt lại cờ đã-bỏ-qua về false trước mỗi test liên quan.
    fn reset_dismissed() {
        UPDATE_DISMISSED.store(false, Ordering::Relaxed);
    }

    /// Bỏ qua nhắc cập nhật phải đặt cờ true; đọc lại đúng giá trị vừa đặt.
    #[test]
    fn dismiss_sets_flag_and_is_dismissed_reads_it() {
        reset_dismissed();
        assert!(!is_update_dismissed(), "flag should start false");
        dismiss_update();
        assert!(is_update_dismissed(), "flag should be true after dismiss");
        reset_dismissed();
    }

    /// "windows" ánh xạ thẳng thành "windows".
    #[test]
    fn os_target_windows() {
        assert_eq!(os_to_target("windows"), "windows");
    }

    /// "macos" ánh xạ thành "darwin", đúng quy ước của tauri-plugin-updater.
    #[test]
    fn os_target_macos() {
        assert_eq!(os_to_target("macos"), "darwin");
    }

    /// "linux" ánh xạ thẳng thành "linux".
    #[test]
    fn os_target_linux() {
        assert_eq!(os_to_target("linux"), "linux");
    }

    /// OS lạ không nhận diện được thì rơi về "linux".
    #[test]
    fn os_target_unknown_falls_back_to_linux() {
        assert_eq!(os_to_target("freebsd"), "linux");
    }

    /// URL endpoint dựng ra phải đúng định dạng `{odoo_url}/medilab/api/v1/updates/{target}/{arch}/{version}`.
    #[test]
    fn endpoint_url_format() {
        let url =
            super::build_endpoint_url("https://odoo.example.com", "windows", "x86_64", "0.1.0")
                .unwrap();
        assert!(
            url.starts_with("https://odoo.example.com/medilab/api/v1/updates/windows/x86_64/0.1.0")
        );
    }
}
