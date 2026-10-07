// Ngăn cửa sổ console phụ hiện lên trên Windows ở bản release, ĐỪNG XÓA!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// Điểm vào tiến trình: chuyển thẳng cho `run()` của thư viện app.
fn main() {
    laboratory_file_sync_application_lib::run()
}
