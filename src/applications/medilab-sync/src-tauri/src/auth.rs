use crate::config::data_dir;
use crate::error::{AppError, AppResult};
use keyring::Entry;
use std::fs;
use std::path::PathBuf;

const SERVICE: &str = "com.medilab.filesync";
const ACCOUNT: &str = "api_key";

/// Đường dẫn tệp fallback lưu API key khi hệ điều hành không có keyring (chỉ dùng khi được
/// cho phép tường minh).
fn credential_file() -> PathBuf {
    data_dir().join("device.apikey")
}

/// True nếu kho bảo mật CÓ tồn tại nhưng đang bị khóa hoặc người dùng từ chối/hủy hộp thoại mở
/// khóa (keyring v3 + Secret Service: `Locked`/`Prompt`/`NoResult` → `NoStorageAccess`). Khác hẳn
/// "không có kho bảo mật": credential vẫn còn nguyên trong kho, chỉ là lúc này chưa đọc được.
fn is_keyring_locked(err: &keyring::Error) -> bool {
    matches!(err, keyring::Error::NoStorageAccess(_))
}

/// True nếu lỗi keyring cho thấy backend bảo mật (Secret Service/D-Bus/...) không khả dụng trên
/// máy này, chứ không phải một lỗi khác.
fn is_keyring_unavailable(err: &keyring::Error) -> bool {
    let text = err.to_string();
    text.contains("not activatable")
        || text.contains("org.freedesktop.secrets")
        || text.contains("Secret Service")
        || text.contains("DBus")
        || text.contains("D-Bus")
        || matches!(
            err,
            keyring::Error::NoStorageAccess(_) | keyring::Error::PlatformFailure(_)
        )
}

/// Ghi API key vào tệp fallback với quyền `0600` trên Unix (chỉ chủ sở hữu đọc/ghi được).
fn save_file_credential(path: &std::path::Path, value: &str) -> AppResult<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, value.as_bytes())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

/// Đọc API key từ tệp fallback; `None` nếu tệp không tồn tại hoặc rỗng.
fn load_file_credential(path: &std::path::Path) -> AppResult<Option<String>> {
    match fs::read_to_string(path) {
        Ok(value) if value.is_empty() => Ok(None),
        Ok(value) => Ok(Some(value)),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err.into()),
    }
}

/// Xóa tệp fallback lưu API key; không lỗi nếu tệp không tồn tại.
fn delete_file_credential(path: &std::path::Path) -> AppResult<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(err) => Err(err.into()),
    }
}

const FILE_KEYRING_ENV: &str = "MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING";
const KEYRING_REQUIRED_MSG: &str = "Không lưu được phiên đăng nhập: hệ thống không có khoá bảo mật (Linux Secret Service / Windows Credential Manager / macOS Keychain). Trên máy phát triển, đặt MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING=true để cho phép file 0600. Không dùng fallback này cho production.";

/// Parse giá trị biến môi trường bật fallback file (`"1"`/`"true"`/`"yes"`/`"on"`, không phân
/// biệt hoa thường); mặc định false khi thiếu hoặc không khớp.
pub fn parse_allow_insecure_file_keyring(value: Option<&str>) -> bool {
    matches!(
        value
            .map(|item| item.trim().to_ascii_lowercase())
            .as_deref(),
        Some("1" | "true" | "yes" | "on")
    )
}

/// Đọc biến môi trường `MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING` và parse thành bool.
fn allow_insecure_file_keyring() -> bool {
    parse_allow_insecure_file_keyring(std::env::var(FILE_KEYRING_ENV).ok().as_deref())
}

/// Khi keyring hệ điều hành không khả dụng: cho phép fallback file nếu biến môi trường bật, hoặc
/// trả lỗi yêu cầu bật nó (không bao giờ âm thầm dùng fallback không an toàn).
fn file_fallback_or_error() -> AppResult<()> {
    if allow_insecure_file_keyring() {
        tracing::warn!(
            "OS keyring unavailable; MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING is set, using a 0600 file under the app data directory"
        );
        Ok(())
    } else {
        Err(AppError::Message(KEYRING_REQUIRED_MSG.into()))
    }
}

/// Lưu API key của thiết bị vào keyring hệ điều hành; rơi về tệp `0600` cục bộ nếu keyring
/// không khả dụng và được phép.
pub fn save_api_key(value: &str) -> AppResult<()> {
    match Entry::new(SERVICE, ACCOUNT) {
        Ok(entry) => match entry.set_password(value) {
            Ok(()) => {
                let _ = delete_file_credential(&credential_file());
                return Ok(());
            }
            Err(err) if is_keyring_unavailable(&err) => file_fallback_or_error()?,
            Err(err) => {
                return Err(AppError::Message(format!(
                    "Không lưu được phiên đăng nhập an toàn: {err}"
                )));
            }
        },
        Err(err) if is_keyring_unavailable(&err) => file_fallback_or_error()?,
        Err(err) => {
            return Err(AppError::Message(format!(
                "Không lưu được phiên đăng nhập an toàn: {err}"
            )));
        }
    }
    save_file_credential(&credential_file(), value)
}

/// Kết quả đọc credential đã lưu. `StoreLocked` KHÔNG phải "chưa đăng nhập" và càng không phải
/// "phiên hết hạn": key có thể vẫn hợp lệ, chỉ là kho bảo mật của OS lúc này chưa mở được.
pub enum CredentialLoad {
    Found(String),
    Missing,
    StoreLocked(String),
}

/// Đọc API key của thiết bị từ keyring hệ điều hành, hoặc từ tệp fallback nếu đã dùng fallback
/// đó lúc lưu. CHỈ gọi lúc khởi động/khôi phục phiên: với Secret Service, đọc một item đang khóa
/// sẽ bật hộp thoại mở khóa của OS và chặn luồng gọi cho tới khi người dùng trả lời. Trong lúc
/// chạy, engine dùng key giữ trong bộ nhớ (`Session`), không gọi hàm này.
pub fn load_api_key() -> CredentialLoad {
    let failure = match Entry::new(SERVICE, ACCOUNT) {
        Ok(entry) => match entry.get_password() {
            Ok(value) => return CredentialLoad::Found(value),
            Err(keyring::Error::NoEntry) => {
                if allow_insecure_file_keyring() {
                    return load_file_fallback();
                }
                return CredentialLoad::Missing;
            }
            Err(err) => err,
        },
        Err(err) => err,
    };
    // Khóa/hủy hộp thoại: key vẫn nằm trong keyring, nên tuyệt đối không rơi về tệp fallback
    // (tệp đó đã bị xóa lúc lưu vào keyring → sẽ bị hiểu nhầm là "chưa đăng nhập").
    if is_keyring_locked(&failure) {
        return CredentialLoad::StoreLocked(failure.to_string());
    }
    if is_keyring_unavailable(&failure) && allow_insecure_file_keyring() {
        return load_file_fallback();
    }
    CredentialLoad::StoreLocked(failure.to_string())
}

/// Đọc tệp fallback (chỉ khi được bật tường minh trên máy phát triển).
fn load_file_fallback() -> CredentialLoad {
    match load_file_credential(&credential_file()) {
        Ok(Some(value)) => CredentialLoad::Found(value),
        Ok(None) => CredentialLoad::Missing,
        Err(err) => CredentialLoad::StoreLocked(err.to_string()),
    }
}

/// Xóa API key của thiết bị khỏi keyring và khỏi tệp fallback (nếu có), dùng lúc đăng xuất.
pub fn delete_api_key() -> AppResult<()> {
    if let Ok(entry) = Entry::new(SERVICE, ACCOUNT) {
        match entry.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => {}
            Err(err) if is_keyring_unavailable(&err) => {}
            Err(err) => {
                return Err(AppError::Message(format!(
                    "Không xóa được phiên đăng nhập: {err}"
                )));
            }
        }
    }
    delete_file_credential(&credential_file())
}

/// Trạng thái xác thực của tiến trình, gửi cho frontend. Bốn trạng thái tách bạch để "kho bảo mật
/// đang khóa" hay "mất mạng" không bao giờ bị trình bày thành "phiên hết hạn".
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthState {
    /// Có API key trong bộ nhớ và server chưa từ chối nó.
    Authenticated,
    /// Máy này không có credential nào: cần đăng nhập.
    MissingCredentials,
    /// Odoo trả 401 cho key này (hết hạn, bị thu hồi, hoặc thiết bị bị thu hồi): cần đăng nhập lại.
    SessionExpired,
    /// Kho bảo mật của OS đang khóa/không đọc được; key có thể vẫn hợp lệ. Cần mở khóa rồi thử lại.
    CredentialStoreLocked,
}

/// Phiên đăng nhập của tiến trình. Keyring của OS là nơi LƯU BỀN; API key đang dùng nằm trong bộ
/// nhớ ở đây. Mọi request và mọi lần dựng status đọc từ đây — không bao giờ hỏi keyring — nên
/// keyring bị khóa giữa chừng không làm gián đoạn đồng bộ hay bật hộp thoại mở khóa.
///
/// Cố ý KHÔNG derive `Debug`/`Serialize`/`Clone`: key không được lọt ra log hay IPC.
#[derive(Default)]
pub struct Session {
    api_key: parking_lot::Mutex<Option<String>>,
    expired: std::sync::atomic::AtomicBool,
    store_locked: std::sync::atomic::AtomicBool,
}

impl Session {
    /// API key đang dùng (nếu có). Không IO.
    pub fn api_key(&self) -> Option<String> {
        self.api_key.lock().clone()
    }

    /// Trạng thái xác thực hiện tại. Không IO.
    pub fn state(&self) -> AuthState {
        use std::sync::atomic::Ordering::SeqCst;
        if self.expired.load(SeqCst) {
            AuthState::SessionExpired
        } else if self.api_key.lock().is_some() {
            AuthState::Authenticated
        } else if self.store_locked.load(SeqCst) {
            AuthState::CredentialStoreLocked
        } else {
            AuthState::MissingCredentials
        }
    }

    /// True khi worker/poller được phép gọi Odoo.
    pub fn is_authenticated(&self) -> bool {
        self.state() == AuthState::Authenticated
    }

    /// True khi Odoo đã từ chối key hiện tại.
    pub fn is_expired(&self) -> bool {
        self.expired.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Đăng nhập thành công (hoặc server xác nhận key): giữ key trong bộ nhớ, xóa mọi cờ lỗi.
    pub fn establish(&self, api_key: String, source: &str) {
        use std::sync::atomic::Ordering::SeqCst;
        *self.api_key.lock() = Some(api_key);
        self.expired.store(false, SeqCst);
        self.store_locked.store(false, SeqCst);
        tracing::info!(
            auth_source = source,
            auth_state = "authenticated",
            "session established"
        );
    }

    /// Nạp key từ nơi lưu bền vào bộ nhớ nếu chưa có. `loader` chỉ chạy khi bộ nhớ trống, nên
    /// phiên đang chạy không bao giờ chạm keyring. Kho khóa → `CredentialStoreLocked`, KHÔNG phải
    /// hết hạn; không xóa hay thu hồi gì.
    pub fn restore_with(&self, loader: impl FnOnce() -> CredentialLoad) -> AuthState {
        use std::sync::atomic::Ordering::SeqCst;
        if self.api_key.lock().is_some() {
            return self.state();
        }
        match loader() {
            CredentialLoad::Found(key) => self.establish(key, "keyring"),
            CredentialLoad::Missing => {
                self.store_locked.store(false, SeqCst);
                tracing::info!(
                    auth_source = "keyring",
                    auth_state = "missing",
                    "no stored credential"
                );
            }
            CredentialLoad::StoreLocked(reason) => {
                self.store_locked.store(true, SeqCst);
                tracing::warn!(
                    auth_source = "keyring",
                    auth_state = "credential_store_locked",
                    reason = %reason,
                    "credential store locked or unavailable; stored credential left untouched"
                );
            }
        }
        self.state()
    }

    /// Odoo trả 401 cho key này: đánh dấu hết hạn và bỏ key khỏi bộ nhớ để không gọi lại bằng key
    /// đã chết. Trả `true` đúng một lần (lúc chuyển false → true) để nơi gọi log/emit một lần.
    pub fn mark_expired(&self, reason: &str) -> bool {
        use std::sync::atomic::Ordering::SeqCst;
        let flipped = !self.expired.swap(true, SeqCst);
        *self.api_key.lock() = None;
        if flipped {
            tracing::warn!(
                auth_state = "expired",
                http_status = 401,
                reason,
                "odoo rejected the device key; session expired, workers paused"
            );
        }
        flipped
    }

    /// Đăng xuất: bỏ key khỏi bộ nhớ và xóa mọi cờ.
    pub fn clear(&self) {
        use std::sync::atomic::Ordering::SeqCst;
        *self.api_key.lock() = None;
        self.expired.store(false, SeqCst);
        self.store_locked.store(false, SeqCst);
        tracing::info!(auth_state = "missing", "session cleared");
    }
}

#[cfg(test)]
mod tests {
    use super::{delete_file_credential, load_file_credential, save_file_credential};
    use std::fs;

    use super::{AuthState, CredentialLoad, Session};
    use std::cell::Cell;

    /// Test thiết kế: engine (worker, poller, `client()`, `status_snapshot()`) không được đọc kho
    /// credential của OS — chỉ `restore_session` đọc, đúng một chỗ. Đọc keyring đang khóa sẽ bật
    /// hộp thoại mở khóa của OS và từng khiến app rơi về màn hình đăng nhập giữa lúc đồng bộ.
    #[test]
    fn credential_store_is_only_read_by_restore_session() {
        let engine = include_str!("sync/engine.rs");
        assert!(!engine.contains("load_api_key"));
        assert!(!engine.contains("keyring::"));
        let commands = include_str!("commands.rs");
        assert_eq!(commands.matches("auth::load_api_key").count(), 1);
    }

    /// Đăng nhập giữ key trong bộ nhớ; sau đó lấy key/trạng thái bao nhiêu lần cũng KHÔNG đọc lại
    /// kho lưu bền — kể cả khi kho đó vừa bị khóa (kịch bản keyring khóa giữa lúc đang đồng bộ).
    #[test]
    fn active_session_never_touches_credential_store() {
        let session = Session::default();
        session.establish("key-1".into(), "login");
        let reads = Cell::new(0);
        for _ in 0..50 {
            assert_eq!(session.api_key().as_deref(), Some("key-1"));
            assert_eq!(session.state(), AuthState::Authenticated);
            let state = session.restore_with(|| {
                reads.set(reads.get() + 1);
                CredentialLoad::StoreLocked("locked".into())
            });
            assert_eq!(state, AuthState::Authenticated);
        }
        assert_eq!(reads.get(), 0);
        assert!(!session.is_expired());
    }

    /// Khởi động: đọc kho đúng một lần rồi giữ trong bộ nhớ.
    #[test]
    fn startup_reads_store_once_then_caches() {
        let session = Session::default();
        let reads = Cell::new(0);
        let load = || {
            reads.set(reads.get() + 1);
            CredentialLoad::Found("stored".into())
        };
        assert_eq!(session.restore_with(load), AuthState::Authenticated);
        assert_eq!(session.restore_with(load), AuthState::Authenticated);
        assert_eq!(reads.get(), 1);
        assert_eq!(session.api_key().as_deref(), Some("stored"));
    }

    /// Kho khóa/hủy hộp thoại lúc khởi động: trạng thái riêng, KHÔNG phải hết hạn, không có key;
    /// thử lại sau khi mở khóa thì vào thẳng phiên.
    #[test]
    fn locked_store_at_startup_is_not_session_expired_and_retry_recovers() {
        let session = Session::default();
        let state = session.restore_with(|| CredentialLoad::StoreLocked("prompt dismissed".into()));
        assert_eq!(state, AuthState::CredentialStoreLocked);
        assert!(!session.is_expired());
        assert!(!session.is_authenticated());
        let state = session.restore_with(|| CredentialLoad::Found("stored".into()));
        assert_eq!(state, AuthState::Authenticated);
    }

    /// Không có credential → trạng thái chưa đăng nhập (không phải hết hạn, không phải kho khóa).
    #[test]
    fn missing_credential_is_logged_out() {
        let session = Session::default();
        assert_eq!(
            session.restore_with(|| CredentialLoad::Missing),
            AuthState::MissingCredentials
        );
    }

    /// 401 thật của Odoo: hết hạn, bỏ key khỏi bộ nhớ, báo chuyển trạng thái đúng một lần; đăng
    /// nhập lại khôi phục phiên.
    #[test]
    fn real_401_expires_once_and_relogin_restores() {
        let session = Session::default();
        session.establish("key-1".into(), "login");
        assert!(session.mark_expired("test"));
        assert!(!session.mark_expired("test"));
        assert_eq!(session.state(), AuthState::SessionExpired);
        assert!(session.api_key().is_none());
        session.establish("key-2".into(), "login");
        assert_eq!(session.state(), AuthState::Authenticated);
        session.clear();
        assert_eq!(session.state(), AuthState::MissingCredentials);
    }

    /// Fallback file phải là opt-in: chỉ bật khi biến môi trường có giá trị true-như, không phải
    /// khi thiếu, rỗng, hay "false".
    #[test]
    fn insecure_file_keyring_is_opt_in() {
        assert!(!super::parse_allow_insecure_file_keyring(None));
        assert!(!super::parse_allow_insecure_file_keyring(Some("")));
        assert!(!super::parse_allow_insecure_file_keyring(Some("false")));
        assert!(super::parse_allow_insecure_file_keyring(Some("true")));
        assert!(super::parse_allow_insecure_file_keyring(Some("1")));
        assert!(super::parse_allow_insecure_file_keyring(Some("YES")));
    }

    /// Lưu rồi đọc lại tệp fallback phải cho đúng giá trị; trên Unix quyền tệp phải là 0600;
    /// xóa xong thì đọc lại phải ra None.
    #[test]
    fn file_fallback_round_trip() {
        let path =
            std::env::temp_dir().join(format!("medilab-sync-key-test-{}", std::process::id()));
        let _ = fs::remove_file(&path);
        save_file_credential(&path, "test-key").unwrap();
        assert_eq!(
            load_file_credential(&path).unwrap().as_deref(),
            Some("test-key")
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o600);
        }
        delete_file_credential(&path).unwrap();
        assert!(load_file_credential(&path).unwrap().is_none());
    }
}
