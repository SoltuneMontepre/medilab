mod api;
mod auth;
mod commands;
mod config;
mod error;
mod storage;
mod sync;
mod updater;

use crate::commands::AppState;
use crate::config::db_path;
use crate::storage::Db;
use crate::sync::engine::EngineHandle;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;

/// True nếu locale đã lưu là tiếng Anh (`"en"`, không phân biệt hoa thường).
fn locale_is_english(locale: &str) -> bool {
    locale.eq_ignore_ascii_case("en")
}

/// Tiêu đề cửa sổ chính theo locale hiện tại.
fn window_title(locale: &str) -> &'static str {
    if locale_is_english(locale) {
        "Lab file sync"
    } else {
        "Đồng bộ tệp phòng lab"
    }
}

/// Nhãn các mục trên menu tray, theo locale hiện tại.
struct TrayLabels {
    open: &'static str,
    pause: &'static str,
    resume: &'static str,
    errors: &'static str,
    quit: &'static str,
}

/// Dựng bộ nhãn tray theo locale hiện tại.
fn tray_labels(locale: &str) -> TrayLabels {
    if locale_is_english(locale) {
        TrayLabels {
            open: "Open app",
            pause: "Pause sync",
            resume: "Resume sync",
            errors: "View errors",
            quit: "Quit",
        }
    } else {
        TrayLabels {
            open: "Mở ứng dụng",
            pause: "Tạm dừng đồng bộ",
            resume: "Tiếp tục đồng bộ",
            errors: "Xem lỗi",
            quit: "Thoát",
        }
    }
}

/// Locale đã lưu trong cấu hình; mặc định "vi" nếu chưa có state hoặc chưa đọc được.
fn current_locale(app: &tauri::AppHandle) -> String {
    app.try_state::<AppState>()
        .and_then(|state| state.engine.db.load_settings().ok())
        .map(|settings| settings.locale)
        .unwrap_or_else(|| "vi".into())
}

/// Hiện cửa sổ chính đã có, hoặc tạo mới nếu chưa từng mở (ví dụ do tray/single-instance gọi).
fn show_main_window(app: &tauri::AppHandle) {
    let title = window_title(&current_locale(app));
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(title);
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
        return;
    }
    let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title(title)
        .inner_size(1100.0, 720.0);
    if let Some(icon) = app.default_window_icon() {
        let _ = builder
            .icon(icon.clone())
            .and_then(|builder| builder.build());
    } else {
        let _ = builder.build();
    }
}

/// Điểm khởi động ứng dụng Tauri: mở DB, khởi động engine đồng bộ, dựng menu tray, đăng ký mọi
/// Tauri command, và giữ app chạy nền khi đóng cửa sổ (chỉ thoát hẳn qua menu Quit).
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        // Span chi tiết ở mức debug; khi bật qua RUST_LOG, sự kiện đóng ghi thời gian busy/idle.
        .with_span_events(tracing_subscriber::fmt::format::FmtSpan::CLOSE)
        .init();

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let db = Db::open(&db_path())?;
            let settings = db.load_settings().unwrap_or_default();
            let engine = EngineHandle::new(db, settings.clone(), app.handle().clone());
            engine.start();
            app.manage(AppState {
                engine: engine.clone(),
            });

            let labels = tray_labels(&settings.locale);
            let open = MenuItem::with_id(app, "open", labels.open, true, None::<&str>)?;
            let pause = MenuItem::with_id(app, "pause", labels.pause, true, None::<&str>)?;
            let resume = MenuItem::with_id(app, "resume", labels.resume, true, None::<&str>)?;
            let errors = MenuItem::with_id(app, "errors", labels.errors, true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", labels.quit, true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &pause, &resume, &errors, &quit])?;
            // Windows hiện một ô tray rỗng nếu không đặt icon tường minh.
            let tray_icon = app.default_window_icon().cloned().ok_or_else(|| {
                std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    "missing default window icon for tray",
                )
            })?;
            TrayIconBuilder::new()
                .icon(tray_icon)
                .tooltip("MediLab File Sync")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" | "errors" => show_main_window(app),
                    "pause" => {
                        if let Some(state) = app.try_state::<AppState>() {
                            let engine = state.engine.clone();
                            tauri::async_runtime::spawn(async move {
                                engine.set_paused(true).await;
                            });
                        }
                    }
                    "resume" => {
                        if let Some(state) = app.try_state::<AppState>() {
                            let engine = state.engine.clone();
                            tauri::async_runtime::spawn(async move {
                                engine.set_paused(false).await;
                            });
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            let update_app = app.handle().clone();
            let update_odoo_url = settings.odoo_url.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                if !updater::is_update_dismissed() {
                    if let Some(info) =
                        updater::check_for_update(&update_app, &update_odoo_url).await
                    {
                        use tauri::Emitter;
                        let _ = update_app.emit("update-available", &info);
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::login,
            commands::logout,
            commands::choose_sync_folder,
            commands::resolve_dropped_sync_folder,
            commands::register_sync_folder,
            commands::unregister_sync_folder,
            commands::list_folder_members,
            commands::add_folder_member,
            commands::remove_folder_member,
            commands::search_member_candidates,
            commands::list_shared_folders,
            commands::bind_shared_folder,
            commands::start_sync,
            commands::pause_sync,
            commands::get_sync_status,
            commands::retry_sync_job,
            commands::list_sync_folders,
            commands::list_sync_jobs,
            commands::get_settings,
            commands::save_settings,
            commands::update_sync_rules,
            commands::restore_session,
            commands::list_remote_files,
            commands::get_sync_file,
            commands::get_file_versions,
            commands::get_file_version_detail,
            commands::restore_file_version,
            commands::accept_server_version,
            commands::keep_local_conflict,
            commands::open_office_editor,
            commands::check_update,
            commands::download_and_install_update,
            commands::dismiss_update_session,
        ]);

    let app = builder
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    app.run(|_app, event| {
        if let tauri::RunEvent::ExitRequested { code, api, .. } = event {
            // Một số compositor có thể hủy cửa sổ GDK mà không qua bước ẩn
            // CloseRequested. Giữ tray/engine sống trừ khi Quit đã yêu cầu exit code.
            if code.is_none() {
                api.prevent_exit();
            }
        }
    });
}
