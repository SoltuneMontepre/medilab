use crate::api::{
    folder_to_bind, unbound_folders, ApiClient, FileDetailDto, FileVersionDto, FileVersionListDto,
    FolderMembersDto, MemberUserDto, OfficeSessionDto, UnboundFoldersDto,
};
use crate::auth;
use crate::config::AppSettings;
use crate::error::{AppError, AppResult};
use crate::storage::{FolderRow, JobRow, RemoteFileRow};
use crate::sync::engine::{to_rule_dtos, EngineHandle, StatusDto};
use crate::sync::rules::SyncRule;
use serde::{Deserialize, Serialize};
#[cfg(target_os = "linux")]
use std::io::ErrorKind;
use std::path::PathBuf;
#[cfg(target_os = "linux")]
use std::process::Command;
use tauri::{AppHandle, State};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_dialog::DialogExt;

/// State Tauri dùng chung cho mọi command: tay cầm tới engine đồng bộ đang chạy nền.
pub struct AppState {
    pub engine: EngineHandle,
}

/// Tham số command `login`: URL Odoo, tài khoản, mật khẩu.
#[derive(Debug, Deserialize)]
pub struct LoginArgs {
    pub odoo_url: String,
    pub login: String,
    pub password: String,
}

/// Tham số command `register_sync_folder`: đường dẫn cục bộ, logical root phía server, có đệ quy
/// hay không, và danh sách rule đặt tên/lọc tệp.
#[derive(Debug, Deserialize)]
pub struct RegisterFolderArgs {
    pub local_path: String,
    pub logical_root: String,
    pub recursive: bool,
    pub rules: Vec<SyncRule>,
}

/// DTO trả về frontend: một folder cục bộ kèm rule đang áp dụng.
#[derive(Debug, Serialize)]
pub struct FolderView {
    #[serde(flatten)]
    pub folder: FolderRow,
    pub rules: Vec<SyncRule>,
}

/// Chuyển một đường dẫn được kéo-thả (kể cả dạng `file://`) thành `PathBuf` trên hệ điều hành.
fn dropped_path_to_fs(raw: &str) -> PathBuf {
    let trimmed = raw.trim();
    if trimmed.starts_with("file:") {
        if let Ok(url) = url::Url::parse(trimmed) {
            if let Ok(path) = url.to_file_path() {
                return path;
            }
        }
    }
    PathBuf::from(trimmed)
}

/// Kiểm `path` tồn tại và là một thư mục; trả về đường dẫn canonical hoặc lỗi.
fn ensure_dir(path: &str) -> AppResult<PathBuf> {
    let path = dropped_path_to_fs(path);
    let canonical = path.canonicalize().map_err(|_| AppError::FolderNotFound)?;
    if !canonical.is_dir() {
        return Err(AppError::Message("Đường dẫn không phải thư mục".into()));
    }
    Ok(canonical)
}

/// Nhận một lượt kéo-thả từ file manager của hệ điều hành. Chỉ chấp nhận đúng một thư mục đã
/// tồn tại.
fn resolve_dropped_sync_folder_path(paths: &[String]) -> AppResult<PathBuf> {
    if paths.is_empty() {
        return Err(AppError::Message("Không nhận được đường dẫn".into()));
    }
    let mut dirs = Vec::new();
    for raw in paths {
        let candidate = dropped_path_to_fs(raw);
        let canonical = match candidate.canonicalize() {
            Ok(path) => path,
            Err(_) => continue,
        };
        if canonical.is_dir() {
            dirs.push(canonical);
        }
    }
    match dirs.len() {
        0 => Err(AppError::Message(
            "Hãy thả một thư mục, không phải tệp".into(),
        )),
        1 => Ok(dirs.pop().expect("one directory")),
        _ => Err(AppError::Message("Chỉ thả một thư mục mỗi lần".into())),
    }
}

/// Tên máy trạm hiện tại, dùng làm nhãn thiết bị khi đăng nhập; `"desktop"` nếu không đọc được.
fn hostname() -> String {
    std::env::var("HOSTNAME")
        .or_else(|_| std::env::var("COMPUTERNAME"))
        .unwrap_or_else(|_| "desktop".into())
}

/// Id thiết bị bền vững của máy trạm này: đọc từ DB cục bộ nếu đã có, sinh mới và lưu lại nếu chưa.
fn client_uid(engine: &EngineHandle) -> AppResult<String> {
    if let Some(existing) = engine.db.meta_get("client_uid")? {
        return Ok(existing);
    }
    let uid = uuid::Uuid::new_v4().to_string();
    engine.db.meta_set("client_uid", &uid)?;
    Ok(uid)
}

/// Đăng nhập Odoo, lưu API key vào keyring, xóa state cục bộ nếu đổi tài khoản, rồi trả về
/// snapshot trạng thái đồng bộ mới nhất.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "login"))]
pub async fn login(state: State<'_, AppState>, args: LoginArgs) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    let uid = client_uid(&engine).map_err(String::from)?;
    let response = ApiClient::login(
        &args.odoo_url,
        &args.login,
        &args.password,
        &hostname(),
        std::env::consts::OS,
        env!("CARGO_PKG_VERSION"),
        &uid,
    )
    .await
    .map_err(String::from)?;
    let previous_login = engine.db.meta_get("user_login").map_err(String::from)?;
    if previous_login.as_deref() != Some(response.user_login.as_str()) {
        engine
            .db
            .clear_account_local_state()
            .map_err(String::from)?;
    }
    // Keyring là nơi lưu bền (bắt buộc ở production); key đang dùng được giữ trong bộ nhớ tiến
    // trình để đồng bộ không bao giờ phải hỏi lại keyring.
    auth::save_api_key(&response.api_key).map_err(String::from)?;
    engine
        .db
        .meta_set("device_id", &response.device_id.to_string())
        .map_err(String::from)?;
    engine
        .db
        .meta_set("user_name", &response.user_name)
        .map_err(String::from)?;
    engine
        .db
        .meta_set("user_login", &response.user_login)
        .map_err(String::from)?;
    engine
        .db
        .meta_set("user_id", &response.user_id.to_string())
        .map_err(String::from)?;
    tracing::info!(device_id = response.device_id, "login succeeded");
    engine.session.establish(response.api_key.clone(), "login");
    let mut settings = engine.settings.lock().await;
    settings.odoo_url = args.odoo_url;
    engine.db.save_settings(&settings).map_err(String::from)?;
    drop(settings);
    engine.emit_status();
    let _ = engine.poll_remote_changes().await;
    engine.status_snapshot().map_err(String::from)
}

/// Đăng xuất: báo server hủy phiên (nếu còn gọi được), xóa API key khỏi keyring cục bộ.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "logout"))]
pub async fn logout(state: State<'_, AppState>) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    if let Ok(client) = engine.client().await {
        let _ = client.logout().await;
    }
    engine.session.clear();
    // Key đã bị thu hồi phía server và đã rời bộ nhớ; nếu keyring đang khóa nên chưa xóa được thì
    // bản lưu còn lại là key chết (lần mở app sau sẽ nhận 401), không chặn việc đăng xuất.
    if let Err(err) = auth::delete_api_key() {
        tracing::warn!("stored credential could not be deleted on logout: {err}");
    }
    engine.emit_status();
    engine.status_snapshot().map_err(String::from)
}

/// Lấy dòng đầu (đã trim) của stdout một tiến trình con; `None` nếu rỗng.
#[cfg(target_os = "linux")]
fn stdout_path(output: &std::process::Output) -> Option<String> {
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        None
    } else {
        Some(path)
    }
}

/// `blocking_pick_folder` của GTK trong một Tauri command làm WebKit deadlock trên Hyprland
/// (`GDK_BACKEND=x11`). Ưu tiên dùng CLI/portal picker trước, rồi mới tới callback rfd bất đồng bộ.
///
/// Thiếu binary hoặc helper bị crash không được coi là "người dùng đã hủy", nếu không sẽ bỏ qua
/// hẳn dialog native/portal.
#[cfg(target_os = "linux")]
fn pick_folder_via_cli() -> Result<Option<String>, std::io::Error> {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let tools: &[(&str, Vec<String>)] = &[
        (
            "zenity",
            vec![
                "--file-selection".into(),
                "--directory".into(),
                "--title=Chọn thư mục đồng bộ".into(),
            ],
        ),
        (
            "qarma",
            vec!["--file-selection".into(), "--directory".into()],
        ),
        ("kdialog", vec!["--getexistingdirectory".into(), home]),
    ];
    for (bin, args) in tools {
        match Command::new(bin)
            .args(args)
            .env_remove("GDK_BACKEND")
            .env("GTK_USE_PORTAL", "1")
            .output()
        {
            Ok(output) => {
                if output.status.success() {
                    if let Some(path) = stdout_path(&output) {
                        return Ok(Some(path));
                    }
                }
                return Ok(None);
            }
            Err(err) if err.kind() == ErrorKind::NotFound => continue,
            Err(err) => return Err(err),
        }
    }
    match Command::new("python3")
        .args([
            "-c",
            "import tkinter as tk\nfrom tkinter import filedialog\nroot=tk.Tk(); root.withdraw(); root.attributes('-topmost', True)\nprint(filedialog.askdirectory(title='Chọn thư mục đồng bộ') or '')",
        ])
        .env_remove("GDK_BACKEND")
        .output()
    {
        Ok(output) if output.status.success() => return Ok(stdout_path(&output)),
        Ok(_) => {}
        Err(err) if err.kind() == ErrorKind::NotFound => {}
        Err(err) => return Err(err),
    }
    Err(std::io::Error::new(ErrorKind::NotFound, "no folder picker"))
}

/// Command: chuẩn hóa đường dẫn của một lượt kéo-thả folder từ frontend.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "resolve_dropped_sync_folder")
)]
pub fn resolve_dropped_sync_folder(paths: Vec<String>) -> Result<String, String> {
    resolve_dropped_sync_folder_path(&paths)
        .map(|path| path.to_string_lossy().into_owned())
        .map_err(String::from)
}

/// Command: mở dialog chọn thư mục (CLI/portal picker trên Linux, dialog native ở nơi khác).
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "choose_sync_folder"))]
pub async fn choose_sync_folder(app: AppHandle) -> Result<Option<String>, String> {
    #[cfg(target_os = "linux")]
    {
        match tokio::task::spawn_blocking(pick_folder_via_cli)
            .await
            .map_err(|err| err.to_string())?
        {
            Ok(Some(path)) => return Ok(Some(path)),
            Ok(None) => return Ok(None),
            Err(err) if err.kind() == ErrorKind::NotFound => {}
            Err(err) => {
                return Err(format!("Không mở được hộp thoại chọn thư mục: {err}"));
            }
        }
    }

    let previous_gdk = std::env::var("GDK_BACKEND").ok();
    std::env::remove_var("GDK_BACKEND");
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |folder| {
        let _ = tx.send(folder);
    });
    let picked = rx.await.unwrap_or(None);
    if let Some(value) = previous_gdk {
        std::env::set_var("GDK_BACKEND", value);
    }
    Ok(picked
        .and_then(|path| path.into_path().ok())
        .map(|path| path.to_string_lossy().into_owned()))
}

/// Command: đăng ký một thư mục cục bộ để đồng bộ — tạo/upsert folder phía server, lưu binding
/// cục bộ, rồi đối soát lại toàn bộ.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "register_sync_folder"))]
pub async fn register_sync_folder(
    state: State<'_, AppState>,
    args: RegisterFolderArgs,
) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    let path = ensure_dir(&args.local_path).map_err(String::from)?;
    let client = engine.client().await.map_err(String::from)?;
    // Luôn POST: server tự upsert folder của chủ sở hữu theo (user, logical_root). App không bao
    // giờ bật/tắt folder trên server — đó là thao tác quản trị của Sync Manager trong Odoo.
    let remote = client
        .create_folder(
            &args.logical_root,
            &args.logical_root,
            &to_rule_dtos(&args.rules),
        )
        .await
        .map_err(String::from)?;
    let folder_id = engine
        .db
        .upsert_folder(
            path.to_string_lossy().as_ref(),
            &args.logical_root,
            Some(remote.id),
            args.recursive,
            &args.rules,
        )
        .map_err(String::from)?;
    let _ = engine.db.apply_folder_lab_context(folder_id, &remote);
    let _ = engine.db.retry_failed_jobs_for_folder(folder_id);
    // Folder trên server có thể đã có tệp (đăng ký cùng tên từ máy khác): hydrate ngay như khi gắn.
    let _ = engine.db.set_needs_hydration(folder_id, true);
    let _ = engine.reconcile_all().await;
    engine.hydrate_pending_folders().await;
    engine.emit_files_changed();
    engine.emit_status();
    engine.status_snapshot().map_err(String::from)
}

/// Command "Ngừng đồng bộ": CHỈ bỏ binding của thư mục này trên máy này. Không gọi server: folder
/// trên server vẫn bật, rule/tệp/thành viên phía server giữ nguyên, user và máy khác không bị ảnh
/// hưởng, và tệp trên đĩa không bị xóa. Tắt folder trên server là thao tác quản trị riêng trong
/// Odoo, không thuộc nút này. Watcher/đối soát đọc binding từ DB nên dừng theo ngay; folder vẫn
/// gắn lại được sau đó theo remote id.
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "unregister_sync_folder", folder_id = folder_id)
)]
pub async fn unregister_sync_folder(
    state: State<'_, AppState>,
    folder_id: i64,
) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    engine.db.delete_folder(folder_id).map_err(String::from)?;
    let _ = engine.reconcile_all().await;
    engine.emit_files_changed();
    engine.emit_status();
    engine.status_snapshot().map_err(String::from)
}

/// Command: thông tin chia sẻ của một folder trên server (chủ sở hữu, tư cách của mình, thành
/// viên). Server quyết định ai thấy được gì; app chỉ hiển thị.
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-manage-members
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "list_folder_members", remote_id = remote_id)
)]
pub async fn list_folder_members(
    state: State<'_, AppState>,
    remote_id: i64,
) -> Result<FolderMembersDto, String> {
    let client = require_client(&state.engine).await?;
    client.list_members(remote_id).await.map_err(String::from)
}

/// Command: thêm một thành viên rồi trả lại danh sách mới. Chỉ gửi user id — vai trò do server
/// gán, và server từ chối nếu người gọi không phải chủ sở hữu/Sync Manager.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "add_folder_member", remote_id = remote_id, user_id = user_id)
)]
pub async fn add_folder_member(
    state: State<'_, AppState>,
    remote_id: i64,
    user_id: i64,
) -> Result<FolderMembersDto, String> {
    let client = require_client(&state.engine).await?;
    client
        .add_member(remote_id, user_id)
        .await
        .map_err(String::from)?;
    client.list_members(remote_id).await.map_err(String::from)
}

/// Command: gỡ một thành viên rồi trả lại danh sách mới. Không đụng tới tệp trên máy của ai.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "remove_folder_member", remote_id = remote_id, member_id = member_id)
)]
pub async fn remove_folder_member(
    state: State<'_, AppState>,
    remote_id: i64,
    member_id: i64,
) -> Result<FolderMembersDto, String> {
    let client = require_client(&state.engine).await?;
    client
        .remove_member(remote_id, member_id)
        .await
        .map_err(String::from)?;
    client.list_members(remote_id).await.map_err(String::from)
}

/// Command: tìm user có thể thêm vào folder này (server giới hạn phạm vi và số kết quả).
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "search_member_candidates", remote_id = remote_id)
)]
pub async fn search_member_candidates(
    state: State<'_, AppState>,
    remote_id: i64,
    query: String,
) -> Result<Vec<MemberUserDto>, String> {
    let client = require_client(&state.engine).await?;
    client
        .search_member_candidates(remote_id, query.trim())
        .await
        .map_err(String::from)
}

/// Tham số gắn một folder được chia sẻ vào một thư mục cục bộ: id folder trên server, đường dẫn
/// cục bộ, có quét đệ quy hay không.
#[derive(Debug, Deserialize)]
pub struct BindSharedFolderArgs {
    pub remote_id: i64,
    pub local_path: String,
    pub recursive: bool,
}

/// Remote id của các folder máy này đã gắn.
fn bound_remote_ids(engine: &EngineHandle) -> Result<Vec<i64>, String> {
    Ok(engine
        .db
        .list_folders()
        .map_err(String::from)?
        .into_iter()
        .filter_map(|folder| folder.remote_id)
        .collect())
}

/// Command: các folder trên server mà máy này chưa gắn — được chia sẻ cho mình ("Được chia sẻ
/// với bạn") và của chính mình (ví dụ sau khi "Ngừng đồng bộ" trên máy này).
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "list_shared_folders"))]
pub async fn list_shared_folders(state: State<'_, AppState>) -> Result<UnboundFoldersDto, String> {
    let engine = state.engine.clone();
    let client = require_client(&engine).await?;
    let remotes = client.list_folders().await.map_err(String::from)?;
    Ok(unbound_folders(remotes, &bound_remote_ids(&engine)?))
}

/// Command: gắn một folder đã có trên server (được chia sẻ, hoặc của chính mình) vào thư mục cục
/// bộ do người dùng chọn. Dùng ĐÚNG remote
/// id lấy từ `GET /folders` và KHÔNG gọi `POST /folders`: không tạo folder trùng lặp, không rơi
/// vào nhánh ưu tiên folder trùng tên của chính mình. Rule lấy theo folder trên server. Mỗi
/// user/máy tự chọn đường dẫn cục bộ riêng cho cùng một folder trên server.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "bind_shared_folder"))]
pub async fn bind_shared_folder(
    state: State<'_, AppState>,
    args: BindSharedFolderArgs,
) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    let path = ensure_dir(&args.local_path).map_err(String::from)?;
    let local_path = path.to_string_lossy().into_owned();
    // upsert theo local_path sẽ ghi đè binding cũ, nên chặn đường dẫn đã dùng.
    let folders = engine.db.list_folders().map_err(String::from)?;
    if folders.iter().any(|folder| folder.local_path == local_path) {
        return Err("Thư mục trên máy này đã được dùng cho một thư mục đồng bộ khác".into());
    }
    let client = require_client(&engine).await?;
    let remotes = client.list_folders().await.map_err(String::from)?;
    let remote = folder_to_bind(remotes, args.remote_id, &bound_remote_ids(&engine)?)
        .map_err(String::from)?;
    let rules: Vec<SyncRule> = remote
        .rules
        .iter()
        .map(|rule| SyncRule {
            kind: rule.r#type.clone(),
            pattern: rule.pattern.clone(),
            recursive: rule.recursive,
            enabled: rule.enabled,
        })
        .collect();
    let folder_id = engine
        .db
        .upsert_folder(
            &local_path,
            &remote.logical_root,
            Some(remote.id),
            args.recursive,
            &rules,
        )
        .map_err(String::from)?;
    let _ = engine.db.apply_folder_lab_context(folder_id, &remote);
    // Binding đã lưu xong. Hydrate ngay từ trạng thái hiện tại của folder trên server để hàng đợi
    // tải xuống có việc tức thì; hydrate lỗi (mất mạng...) không gỡ binding — cờ bền để poll thử lại.
    let _ = engine.db.set_needs_hydration(folder_id, true);
    let _ = engine.reconcile_all().await;
    engine.hydrate_pending_folders().await;
    engine.emit_files_changed();
    engine.emit_status();
    engine.status_snapshot().map_err(String::from)
}

/// Command: bỏ tạm dừng và đối soát lại toàn bộ ngay.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "start_sync"))]
pub async fn start_sync(state: State<'_, AppState>) -> Result<StatusDto, String> {
    state.engine.set_paused(false).await;
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: tạm dừng vòng lặp đồng bộ.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "pause_sync"))]
pub async fn pause_sync(state: State<'_, AppState>) -> Result<StatusDto, String> {
    state.engine.set_paused(true).await;
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: snapshot trạng thái đồng bộ hiện tại (folder, job, tiến độ).
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "get_sync_status"))]
pub fn get_sync_status(state: State<'_, AppState>) -> Result<StatusDto, String> {
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: đặt lại một job lỗi để thử lại.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "retry_sync_job", job_id = job_id)
)]
pub fn retry_sync_job(state: State<'_, AppState>, job_id: i64) -> Result<StatusDto, String> {
    state.engine.db.retry_job(job_id).map_err(String::from)?;
    state.engine.emit_status();
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: liệt kê mọi folder đã đăng ký kèm rule của từng folder.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "list_sync_folders"))]
pub fn list_sync_folders(state: State<'_, AppState>) -> Result<Vec<FolderView>, String> {
    let folders = state.engine.db.list_folders().map_err(String::from)?;
    let mut out = Vec::new();
    for folder in folders {
        let rules = state
            .engine
            .db
            .folder_rules(folder.id)
            .map_err(String::from)?;
        out.push(FolderView { folder, rules });
    }
    Ok(out)
}

/// Command: liệt kê mọi job đồng bộ (đang chạy, chờ, lỗi, đã xong).
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "list_sync_jobs"))]
pub fn list_sync_jobs(state: State<'_, AppState>) -> Result<Vec<JobRow>, String> {
    state.engine.db.list_jobs().map_err(String::from)
}

/// Command: đọc cấu hình ứng dụng đã lưu.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "get_settings"))]
pub fn get_settings(state: State<'_, AppState>) -> Result<AppSettings, String> {
    state.engine.db.load_settings().map_err(String::from)
}

/// Command: lưu cấu hình mới, đồng bộ cờ tạm dừng vào engine, và bật/tắt autostart theo cài đặt.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "save_settings"))]
pub async fn save_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    settings: AppSettings,
) -> Result<StatusDto, String> {
    state
        .engine
        .db
        .save_settings(&settings)
        .map_err(String::from)?;
    {
        let mut current = state.engine.settings.lock().await;
        *current = settings.clone();
        state
            .engine
            .paused
            .store(settings.paused, std::sync::atomic::Ordering::SeqCst);
    }
    if settings.autostart {
        let _ = app.autolaunch().enable();
    } else {
        let _ = app.autolaunch().disable();
    }
    state.engine.emit_status();
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: đổi rule đặt tên/lọc tệp của một folder rồi đối soát lại toàn bộ.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "update_sync_rules", folder_id = folder_id)
)]
pub async fn update_sync_rules(
    state: State<'_, AppState>,
    folder_id: i64,
    rules: Vec<SyncRule>,
) -> Result<StatusDto, String> {
    let folders = state.engine.db.list_folders().map_err(String::from)?;
    let folder = folders
        .into_iter()
        .find(|folder| folder.id == folder_id)
        .ok_or_else(|| AppError::FolderNotFound.to_string())?;
    state
        .engine
        .db
        .upsert_folder(
            &folder.local_path,
            &folder.logical_root,
            folder.remote_id,
            folder.recursive,
            &rules,
        )
        .map_err(String::from)?;
    let _ = state.engine.reconcile_all().await;
    state.engine.emit_status();
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: khôi phục phiên lúc khởi động app (và khi người dùng bấm "Thử lại" sau khi mở khóa
/// kho mật khẩu). Đây là nơi DUY NHẤT đọc keyring: một lần, ngoài async runtime vì hộp thoại mở
/// khóa của OS chặn luồng gọi tới khi người dùng trả lời. Sau đó key nằm trong bộ nhớ.
/// - Kho khóa/hủy hộp thoại → `credential_store_locked`; không xóa, không thu hồi, không "hết hạn".
/// - Odoo trả 401 cho `/me` → `session_expired`.
/// - Mất mạng/5xx → vẫn `authenticated`, app chạy bình thường và tự thử lại.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "restore_session"))]
pub async fn restore_session(state: State<'_, AppState>) -> Result<StatusDto, String> {
    let engine = state.engine.clone();
    if engine.session.api_key().is_none() && !engine.session.is_expired() {
        let session = engine.session.clone();
        let _ = tokio::task::spawn_blocking(move || session.restore_with(auth::load_api_key)).await;
    }
    if let Ok(client) = engine.client().await {
        match client.me().await {
            Ok(me) => {
                engine
                    .db
                    .meta_set("user_name", &me.name)
                    .map_err(String::from)?;
            }
            Err(AppError::Unauthenticated) => {
                engine.session.mark_expired("restore_session");
            }
            Err(err) => {
                tracing::warn!(
                    auth_state = "authenticated",
                    "could not reach server to validate session; staying logged in: {err}"
                );
            }
        }
    }
    if engine.session.is_authenticated() {
        let _ = engine.poll_remote_changes().await;
    }
    engine.emit_status();
    engine.status_snapshot().map_err(String::from)
}

/// Command: liệt kê tệp trên server đã biết cục bộ (dùng cho các view không phụ thuộc folder).
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "list_remote_files"))]
pub fn list_remote_files(state: State<'_, AppState>) -> Result<Vec<RemoteFileRow>, String> {
    state.engine.db.list_remote_files().map_err(String::from)
}

/// Lấy client API đã xác thực từ engine, hoặc lỗi chuỗi cho Tauri command.
async fn require_client(engine: &EngineHandle) -> Result<ApiClient, String> {
    engine.client().await.map_err(String::from)
}

/// Command: trang lịch sử version của một tệp trên server.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "get_file_versions", file_id = file_id, limit = ?limit, offset = ?offset)
)]
pub async fn get_file_versions(
    state: State<'_, AppState>,
    file_id: i64,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<FileVersionListDto, String> {
    if file_id <= 0 {
        return Err("Thiếu mã tệp trên máy chủ".into());
    }
    let client = require_client(&state.engine).await?;
    client
        .get_file_versions(file_id, limit.unwrap_or(20), offset.unwrap_or(0))
        .await
        .map_err(String::from)
}

/// Command: chi tiết một tệp trên server theo id.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "get_sync_file", file_id = file_id)
)]
pub async fn get_sync_file(
    state: State<'_, AppState>,
    file_id: i64,
) -> Result<FileDetailDto, String> {
    if file_id <= 0 {
        return Err("Thiếu mã tệp trên máy chủ".into());
    }
    let client = require_client(&state.engine).await?;
    client.get_file(file_id).await.map_err(String::from)
}

/// Command: chi tiết một version cụ thể của một tệp.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "get_file_version_detail", file_id = file_id, version_id = version_id)
)]
pub async fn get_file_version_detail(
    state: State<'_, AppState>,
    file_id: i64,
    version_id: i64,
) -> Result<FileVersionDto, String> {
    if file_id <= 0 || version_id <= 0 {
        return Err("Thiếu mã tệp hoặc phiên bản".into());
    }
    let client = require_client(&state.engine).await?;
    client
        .get_file_version(file_id, version_id)
        .await
        .map_err(String::from)
}

/// Command: yêu cầu server phục hồi một version cũ thành version hiện hành mới.
///
/// Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "restore_file_version", file_id = file_id, version_id = version_id)
)]
pub async fn restore_file_version(
    state: State<'_, AppState>,
    file_id: i64,
    version_id: i64,
) -> Result<FileVersionDto, String> {
    if file_id <= 0 || version_id <= 0 {
        return Err("Thiếu mã tệp hoặc phiên bản".into());
    }
    let client = require_client(&state.engine).await?;
    let restored = client
        .restore_file_version(file_id, version_id)
        .await
        .map_err(String::from)?;
    // Kích hoạt đối soát thay đổi máy chủ ngay lập tức để tải phiên bản chuẩn mới về thư mục
    // cục bộ qua quy trình tải xuống an toàn của sync engine mà không cần chờ chu kỳ thăm dò.
    let _ = state.engine.poll_remote_changes().await;
    state.engine.emit_status();
    Ok(restored)
}

/// Command: xung đột nội dung — người dùng chọn giữ bản trên server.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "accept_server_version", file_id = file_id)
)]
pub async fn accept_server_version(
    state: State<'_, AppState>,
    file_id: i64,
) -> Result<StatusDto, String> {
    state
        .engine
        .accept_server_version(file_id)
        .map_err(String::from)?;
    let _ = state.engine.poll_remote_changes().await;
    state.engine.emit_status();
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: xung đột nội dung — người dùng chọn giữ bản cục bộ (bản conflict vẫn được lưu song song).
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "keep_local_conflict", file_id = file_id)
)]
pub fn keep_local_conflict(state: State<'_, AppState>, file_id: i64) -> Result<StatusDto, String> {
    state
        .engine
        .keep_local_conflict(file_id)
        .map_err(String::from)?;
    state.engine.emit_status();
    state.engine.status_snapshot().map_err(String::from)
}

/// Command: mở phiên chỉnh sửa ONLYOFFICE cho một tệp trên server.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "open_office_editor", file_id = file_id)
)]
pub async fn open_office_editor(
    state: State<'_, AppState>,
    file_id: i64,
) -> Result<OfficeSessionDto, String> {
    if file_id <= 0 {
        return Err("Thiếu mã tệp trên máy chủ".into());
    }
    let client = require_client(&state.engine).await?;
    client
        .open_office_session(file_id)
        .await
        .map_err(String::from)
}

/// Kiểm tra bản cập nhật mới trên endpoint Odoo đã cấu hình.
///
/// Trả về `None` khi đã là bản mới nhất hoặc khi lượt kiểm thất bại vì bất kỳ lý do gì (lỗi mạng,
/// endpoint không hợp lệ, ...). Lỗi chỉ được log, không bao giờ hiện thành error cho người dùng để
/// tránh gây hoang mang vì một lượt kiểm nền định kỳ.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "check_update"))]
pub async fn check_update(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<crate::updater::UpdateAvailable>, String> {
    let odoo_url = {
        let settings = state.engine.settings.lock().await;
        settings.odoo_url.clone()
    };
    Ok(crate::updater::check_for_update(&app, &odoo_url).await)
}

/// Tải và cài đặt bản cập nhật đang chờ.
///
/// Tạm dừng engine đồng bộ trong hai giây để job đang chạy dở kịp tới một điểm dừng an toàn trước
/// khi tiến trình bị thay thế bởi installer. Trên Windows, updater NSIS chạy installer im lặng rồi
/// thoát tiến trình hiện tại; ở nền tảng khác, launcher/AppImage được thay thế tại chỗ.
#[tauri::command]
#[tracing::instrument(
    level = "debug",
    skip_all,
    fields(command = "download_and_install_update")
)]
pub async fn download_and_install_update(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    // Tạm dừng sync để job đang chạy dở tới một điểm dừng sạch trước khi tiến trình
    // bị thay thế. Hai giây là khá rộng rãi nhưng không chặn lâu.
    state.engine.set_paused(true).await;
    tokio::time::sleep(std::time::Duration::from_secs(2)).await;

    let odoo_url = {
        let settings = state.engine.settings.lock().await;
        settings.odoo_url.clone()
    };
    crate::updater::download_and_install(&app, &odoo_url).await
}

/// Bỏ qua nhắc cập nhật cho phiên chạy hiện tại.
///
/// Cờ đã bỏ qua reset khi tiến trình khởi động lại, nên người dùng sẽ được nhắc lại ở lần mở
/// app tiếp theo.
#[tauri::command]
#[tracing::instrument(level = "debug", skip_all, fields(command = "dismiss_update_session"))]
pub fn dismiss_update_session() {
    crate::updater::dismiss_update();
}

#[cfg(test)]
mod tests {
    use super::{resolve_dropped_sync_folder_path, AppError};
    use std::fs;

    /// Tạo một thư mục tạm riêng cho test, đặt tên theo `label` + uuid để không đụng nhau.
    fn temp_dir(label: &str) -> std::path::PathBuf {
        let dir =
            std::env::temp_dir().join(format!("medilab-drop-{label}-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// Thả một thư mục thật phải trả về đường dẫn canonical của chính nó.
    #[test]
    fn dropped_directory_is_canonicalized() {
        let dir = temp_dir("dir");
        let resolved =
            resolve_dropped_sync_folder_path(&[dir.to_string_lossy().into_owned()]).unwrap();
        assert_eq!(resolved, dir.canonicalize().unwrap());
        fs::remove_dir_all(&dir).ok();
    }

    /// Thả một thư mục dạng URL `file://` cũng được chấp nhận như đường dẫn thường.
    #[test]
    fn dropped_file_url_directory_is_accepted() {
        let dir = temp_dir("url");
        let url = url::Url::from_file_path(dir.canonicalize().unwrap()).unwrap();
        let resolved = resolve_dropped_sync_folder_path(&[url.to_string()]).unwrap();
        assert_eq!(resolved, dir.canonicalize().unwrap());
        fs::remove_dir_all(&dir).ok();
    }

    /// Thả một tệp (không phải thư mục) phải bị từ chối.
    #[test]
    fn dropped_file_is_rejected() {
        let dir = temp_dir("file");
        let file = dir.join("note.txt");
        fs::write(&file, b"x").unwrap();
        let err =
            resolve_dropped_sync_folder_path(&[file.to_string_lossy().into_owned()]).unwrap_err();
        assert!(matches!(err, AppError::Message(message) if message.contains("thư mục")));
        fs::remove_dir_all(&dir).ok();
    }

    /// Thả nhiều hơn một thư mục cùng lúc phải bị từ chối.
    #[test]
    fn multiple_directories_are_rejected() {
        let a = temp_dir("a");
        let b = temp_dir("b");
        let err = resolve_dropped_sync_folder_path(&[
            a.to_string_lossy().into_owned(),
            b.to_string_lossy().into_owned(),
        ])
        .unwrap_err();
        assert!(matches!(err, AppError::Message(message) if message.contains("một thư mục")));
        fs::remove_dir_all(&a).ok();
        fs::remove_dir_all(&b).ok();
    }
}
