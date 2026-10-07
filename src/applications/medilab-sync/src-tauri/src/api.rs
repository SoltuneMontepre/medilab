use crate::error::{AppError, AppResult};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;
use std::time::Duration;

/// Thời gian chờ tối đa cho một request API Odoo (chỉ metadata, không mang byte tệp).
const ODOO_REQUEST_TIMEOUT: Duration = Duration::from_secs(60);
/// Thời gian chờ đăng nhập, ngắn hơn request thường để người dùng sớm biết server không phản hồi.
const LOGIN_TIMEOUT: Duration = Duration::from_secs(30);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(15);
/// Khoảng tối đa không nhận được byte nào từ MinIO/S3 trước khi coi kết nối là treo.
const STORAGE_READ_TIMEOUT: Duration = Duration::from_secs(60);
const PART_UPLOAD_MIN_TIMEOUT: Duration = Duration::from_secs(120);
/// Tốc độ thấp nhất còn chấp nhận khi tải lên một part; chậm hơn thì part bị coi là treo.
const PART_UPLOAD_MIN_BYTES_PER_SEC: u64 = 16 * 1024;

static ODOO_HTTP: OnceLock<reqwest::Client> = OnceLock::new();
static STORAGE_UPLOAD_HTTP: OnceLock<reqwest::Client> = OnceLock::new();
static STORAGE_DOWNLOAD_HTTP: OnceLock<reqwest::Client> = OnceLock::new();

/// Lấy client dùng chung trong `cell`, dựng bằng `build` ở lần đầu; lỗi dựng không được cache
/// để lần gọi sau thử lại.
fn shared_client(
    cell: &'static OnceLock<reqwest::Client>,
    build: impl FnOnce() -> reqwest::Result<reqwest::Client>,
) -> AppResult<reqwest::Client> {
    if let Some(client) = cell.get() {
        return Ok(client.clone());
    }
    let client = build()?;
    Ok(cell.get_or_init(|| client).clone())
}

/// Client HTTP dùng chung cho API Odoo: giữ pool kết nối/TLS giữa các job và lượt poll thay vì
/// dựng mới cho mỗi lần gọi.
fn odoo_http() -> AppResult<reqwest::Client> {
    shared_client(&ODOO_HTTP, || {
        reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .timeout(ODOO_REQUEST_TIMEOUT)
            .build()
    })
}

/// Client HTTP dùng chung để PUT part lên presigned URL (MinIO/S3). Không đặt read timeout: với
/// reqwest, read timeout đếm cả lúc gửi body chờ response header nên sẽ cắt part upload lâu hơn
/// ngưỡng. Mỗi PUT tự đặt timeout theo kích thước (`part_upload_timeout`).
fn storage_upload_http() -> AppResult<reqwest::Client> {
    shared_client(&STORAGE_UPLOAD_HTTP, || {
        reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .build()
    })
}

/// Client HTTP dùng chung để GET tệp qua presigned URL (MinIO/S3). Không có timeout tổng: tệp
/// lớn trên mạng chậm là hợp lệ; kết nối treo (không nhận được byte nào) bị cắt bằng read timeout.
pub(crate) fn storage_download_http() -> AppResult<reqwest::Client> {
    shared_client(&STORAGE_DOWNLOAD_HTTP, || {
        reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .read_timeout(STORAGE_READ_TIMEOUT)
            .build()
    })
}

/// Timeout cho PUT một part `len` byte: đủ thời gian ở tốc độ tối thiểu
/// `PART_UPLOAD_MIN_BYTES_PER_SEC`, không dưới `PART_UPLOAD_MIN_TIMEOUT`.
pub(crate) fn part_upload_timeout(len: usize) -> Duration {
    Duration::from_secs(len as u64 / PART_UPLOAD_MIN_BYTES_PER_SEC).max(PART_UPLOAD_MIN_TIMEOUT)
}

/// Client HTTP đã xác thực gọi API sync của Odoo; mang theo API key và device id để gắn vào
/// mọi request.
#[derive(Clone)]
pub struct ApiClient {
    http: reqwest::Client,
    base: String,
    api_key: String,
    device_id: i64,
}

/// Kết quả đăng nhập: API key mới cấp cho thiết bị, cùng thông tin user/thiết bị.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct LoginResponse {
    pub api_key: String,
    pub user_id: i64,
    pub user_name: String,
    pub user_login: String,
    pub device_id: i64,
    pub device_name: String,
}

/// Thông tin phiên hiện tại: user, thiết bị, và nhóm quyền — dùng để xác nhận phiên còn hợp lệ.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct MeResponse {
    pub user_id: i64,
    pub name: String,
    pub login: String,
    pub device_id: i64,
    pub device_name: String,
    pub groups: Vec<String>,
}

/// Một folder đồng bộ trên server, kèm rule đặt tên/lọc và ngữ cảnh mẫu LIMS (nếu đã map).
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FolderDto {
    pub id: i64,
    pub name: String,
    pub logical_root: String,
    pub sync_mode: String,
    pub enabled: bool,
    #[serde(default)]
    pub device_id: i64,
    #[serde(default)]
    pub user_id: i64,
    pub rules: Vec<RuleDto>,
    #[serde(default)]
    pub sample_name: Option<String>,
    #[serde(default)]
    pub sample_code: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub workflow_status: Option<String>,
    #[serde(default)]
    pub nguon_thiet_bi: Option<String>,
    /// Tên chủ sở hữu folder. Server cũ không gửi → `None`.
    #[serde(default)]
    pub owner_name: Option<String>,
    /// Tư cách của người gọi: `owner`, `upload` (thành viên đọc + ghi) hoặc `manager`.
    #[serde(default)]
    pub my_role: Option<String>,
    /// Gợi ý hiển thị nút quản lý; quyền thật do server quyết định ở từng lần gọi.
    #[serde(default)]
    pub can_manage_members: bool,
}

/// Danh tính tối thiểu của một user do server trả về: chỉ id, tên và login.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct MemberUserDto {
    pub id: i64,
    pub name: String,
    #[serde(default)]
    pub login: Option<String>,
}

/// Một thành viên của folder. `effective_access=false` nghĩa là đã là thành viên nhưng chưa thấy
/// mẫu đã map trong LIMS nên chưa truy cập được.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct MemberDto {
    pub id: i64,
    pub user: MemberUserDto,
    pub role: String,
    #[serde(default = "default_true")]
    pub effective_access: bool,
}

/// Thông tin chia sẻ của một folder: chủ sở hữu, tư cách của người gọi và danh sách thành viên
/// (đủ với chủ sở hữu/Sync Manager; thành viên thường chỉ nhận dòng của chính mình).
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FolderMembersDto {
    pub folder_id: i64,
    pub owner: MemberUserDto,
    pub my_role: String,
    #[serde(default)]
    pub can_manage_members: bool,
    #[serde(default)]
    pub mapped: bool,
    #[serde(default)]
    pub members: Vec<MemberDto>,
}

/// Mặc định `true` cho field bool vắng mặt trong response.
fn default_true() -> bool {
    true
}

/// Một rule đặt tên/lọc tệp áp cho một folder (khớp phần mở rộng, tiền tố, hoặc glob).
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct RuleDto {
    pub id: Option<i64>,
    pub r#type: String,
    pub pattern: String,
    pub recursive: bool,
    pub enabled: bool,
}

/// Kết quả server chuẩn bị một lượt tải lên: kích thước phần, storage key, và có bị trùng nội
/// dung hay không.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct PrepareResponse {
    #[serde(alias = "session_id")]
    pub session_id: Option<i64>,
    pub file_id: i64,
    #[serde(alias = "deduplicated")]
    pub deduplicated: bool,
    pub version_id: Option<i64>,
    pub version_number: Option<i64>,
    #[serde(alias = "part_size")]
    pub part_size: i64,
    #[serde(alias = "storage_key")]
    pub storage_key: String,
    pub s3_upload_id: Option<String>,
    pub expires_at: Option<String>,
    #[serde(default)]
    pub object_reused: bool,
}

/// URL presigned để tải lên trực tiếp một phần (part) của một object lên storage.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct PresignPart {
    pub part_number: i64,
    pub url: String,
    pub expires_in: i64,
}

/// Kết quả hoàn tất một lượt tải lên: version mới tạo, hoặc thông tin xung đột nếu có.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FinalizeResponse {
    pub status: String,
    pub file_id: i64,
    pub version_id: Option<i64>,
    pub version_number: Option<i64>,
    pub conflict_id: Option<i64>,
    pub server_version_id: Option<i64>,
}

/// Người hoặc thiết bị đứng sau một hành động (tạo version, ...), dùng để hiện tên trên UI.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct VersionActorDto {
    pub id: i64,
    pub name: String,
}

/// Một version cụ thể của một tệp: hash nội dung, người/thiết bị tạo, có phải bản chuẩn
/// (canonical) hay không, và có phục hồi được không.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FileVersionDto {
    pub id: i64,
    pub file_id: i64,
    pub version_number: i64,
    pub size: i64,
    pub content_hash: String,
    pub checksum_algorithm: String,
    pub source: String,
    pub created_at: Option<String>,
    pub created_by: Option<VersionActorDto>,
    pub device: Option<VersionActorDto>,
    pub is_canonical: bool,
    pub parent_version_id: Option<i64>,
    #[serde(default)]
    pub parent_version_number: Option<i64>,
    pub restored_from_version_id: Option<i64>,
    #[serde(default)]
    pub restored_from_version_number: Option<i64>,
    pub object_available: Option<bool>,
    #[serde(default)]
    pub can_restore: bool,
    #[serde(default)]
    pub current_version_id: Option<i64>,
}

/// Một thay đổi trong change feed của folder (version mới, đổi tên, ...), dùng để đồng bộ tăng
/// dần thay vì quét lại toàn bộ.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FolderChangeDto {
    pub id: i64,
    pub change_type: String,
    pub folder_id: i64,
    pub file_id: i64,
    pub logical_path: String,
    pub current_version_id: Option<i64>,
    pub version_number: Option<i64>,
    pub content_hash: Option<String>,
    pub size: i64,
    pub source: Option<String>,
    pub changed_at: Option<String>,
    pub changed_by_device_id: Option<i64>,
}

/// Một trang của change feed: danh sách thay đổi, kèm cursor để lấy trang kế tiếp.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FolderChangesDto {
    pub folder_id: i64,
    pub changes: Vec<FolderChangeDto>,
    pub next_cursor: i64,
    pub has_more: bool,
    pub limit: i64,
}

/// Một trang danh sách tệp thuộc một folder, dùng cho reconciliation toàn bộ.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FolderFileListDto {
    pub folder_id: i64,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
    pub items: Vec<FileDetailDto>,
}

/// URL presigned và metadata toàn vẹn (hash, kích thước) để tải một version cụ thể xuống.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct DownloadAuthDto {
    pub file_id: i64,
    pub version_id: i64,
    pub version_number: i64,
    pub size: i64,
    pub content_hash: String,
    pub checksum_algorithm: String,
    pub url: String,
    pub expires_in: i64,
}

/// Chi tiết một tệp trên server: version hiện hành, số lượng version, và lần cập nhật gần nhất.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FileDetailDto {
    pub id: i64,
    pub folder_id: i64,
    pub name: String,
    pub logical_path: String,
    pub current_version_id: Option<i64>,
    pub version_count: i64,
    pub updated_at: Option<String>,
    pub current_version: Option<FileVersionDto>,
}

/// Một trang lịch sử version của một tệp.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct FileVersionListDto {
    pub file_id: i64,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
    pub items: Vec<FileVersionDto>,
}

/// Danh tính người dùng hiện cho ONLYOFFICE Document Server.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeUserDto {
    pub id: String,
    pub name: String,
}

/// Quyền hạn của người dùng trên phiên chỉnh sửa ONLYOFFICE hiện tại.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficePermissionsDto {
    pub edit: bool,
    pub download: bool,
    pub print: bool,
    #[serde(default)]
    pub comment: bool,
}

/// Mô tả tài liệu gửi cho ONLYOFFICE: loại tệp, khóa phiên bản, URL tải nội dung, quyền hạn.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeDocumentDto {
    #[serde(rename = "fileType")]
    pub file_type: String,
    pub key: String,
    pub title: String,
    pub url: String,
    pub permissions: OfficePermissionsDto,
}

/// Tùy chỉnh editor ONLYOFFICE do server quyết định. Struct có kiểu nên field nào không khai báo ở
/// đây sẽ bị serde BỎ khi config đi qua lớp Rust — `uiTheme` từng bị rơi đúng như vậy, khiến editor
/// trong app vẫn theo theme tối của hệ điều hành dù server đã đặt theme sáng. `extra` giữ nguyên
/// mọi tùy chỉnh khác server thêm về sau để chúng tới được `DocsAPI.DocEditor`.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeCustomizationDto {
    #[serde(default)]
    pub autosave: bool,
    #[serde(default)]
    pub forcesave: bool,
    #[serde(rename = "uiTheme", default, skip_serializing_if = "Option::is_none")]
    pub ui_theme: Option<String>,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

/// Phần `editorConfig` của cấu hình ONLYOFFICE: chế độ, ngôn ngữ, callback lưu, người dùng.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeEditorInnerDto {
    pub mode: String,
    pub lang: String,
    #[serde(rename = "type", default)]
    pub editor_type: Option<String>,
    #[serde(rename = "callbackUrl")]
    pub callback_url: String,
    pub user: OfficeUserDto,
    #[serde(default)]
    pub customization: Option<OfficeCustomizationDto>,
}

/// Toàn bộ cấu hình JS cần truyền cho ONLYOFFICE API để mở editor.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeEditorConfigDto {
    #[serde(rename = "documentType")]
    pub document_type: String,
    #[serde(default)]
    pub width: Option<String>,
    #[serde(default)]
    pub height: Option<String>,
    pub document: OfficeDocumentDto,
    #[serde(rename = "editorConfig")]
    pub editor_config: OfficeEditorInnerDto,
    pub token: String,
}

/// Phiên chỉnh sửa ONLYOFFICE cho một tệp: id phiên, version gốc, và cấu hình để nhúng editor.
#[derive(Deserialize, Serialize, Clone)]
pub struct OfficeSessionDto {
    pub session_id: i64,
    pub file_id: i64,
    pub base_version_id: i64,
    pub document_key: String,
    pub created: bool,
    pub state: String,
    pub document_server_url: String,
    pub document_type: String,
    pub file_type: String,
    pub config: OfficeEditorConfigDto,
}

impl ApiClient {
    /// Dựng client với API key và device id đã có sẵn (đăng nhập trước đó).
    pub fn new(base: &str, api_key: &str, device_id: i64) -> AppResult<Self> {
        Ok(Self {
            http: odoo_http()?,
            base: base.trim_end_matches('/').to_string(),
            api_key: api_key.to_string(),
            device_id,
        })
    }

    /// Device id của phiên này (chỉ cho test phân biệt hai thiết bị).
    #[cfg(test)]
    pub fn device_id(&self) -> i64 {
        self.device_id
    }

    /// Dựng header `Authorization: Bearer` + `X-Sync-Device-Id` cho mọi request đã xác thực.
    fn headers(&self) -> AppResult<HeaderMap> {
        let mut headers = HeaderMap::new();
        let value = HeaderValue::from_str(&format!("Bearer {}", self.api_key))
            .map_err(|err| AppError::Message(err.to_string()))?;
        headers.insert(AUTHORIZATION, value);
        headers.insert(
            "X-Sync-Device-Id",
            HeaderValue::from_str(&self.device_id.to_string())
                .map_err(|err| AppError::Message(err.to_string()))?,
        );
        Ok(headers)
    }

    /// Chuyển response lỗi thành `AppError`: 401 thành `Unauthenticated`, còn lại qua
    /// `map_http_error`; response thành công trả nguyên vẹn.
    async fn map_response(response: reqwest::Response) -> AppResult<reqwest::Response> {
        let status = response.status();
        if status.as_u16() == 401 {
            return Err(AppError::Unauthenticated);
        }
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(map_http_error(status.as_u16(), &body));
        }
        Ok(response)
    }

    /// Xóa phần query khỏi một URL, để log an toàn (không lộ presigned signature).
    pub fn sanitize_url(url: &str) -> String {
        url.split('?').next().unwrap_or("[invalid-url]").to_string()
    }

    /// Đăng nhập bằng tài khoản/mật khẩu Odoo, đăng ký thiết bị này, và nhận về API key mới.
    pub async fn login(
        base: &str,
        login: &str,
        password: &str,
        device_name: &str,
        os: &str,
        app_version: &str,
        client_uid: &str,
    ) -> AppResult<LoginResponse> {
        let url = format!("{}/api/sync/v1/auth/login", base.trim_end_matches('/'));
        let response = odoo_http()?
            .post(url)
            .timeout(LOGIN_TIMEOUT)
            .json(&serde_json::json!({
                "login": login,
                "password": password,
                "device": {
                    "name": device_name,
                    "os": os,
                    "app_version": app_version,
                    "client_uid": client_uid,
                }
            }))
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            return Err(AppError::Message(format!(
                "Đăng nhập thất bại ({status}): {text}"
            )));
        }
        Ok(response.json().await?)
    }

    /// Xác nhận phiên hiện tại còn hợp lệ và đọc lại thông tin user/thiết bị.
    pub async fn me(&self) -> AppResult<MeResponse> {
        let response = self
            .http
            .get(format!("{}/api/sync/v1/me", self.base))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Báo server hủy phiên hiện tại (best-effort, lỗi bị bỏ qua).
    pub async fn logout(&self) -> AppResult<()> {
        let _ = self
            .http
            .post(format!("{}/api/sync/v1/auth/logout", self.base))
            .headers(self.headers()?)
            .send()
            .await?;
        Ok(())
    }

    /// Liệt kê mọi folder trên server mà thiết bị/người dùng hiện tại được phép thấy.
    pub async fn list_folders(&self) -> AppResult<Vec<FolderDto>> {
        let response = self
            .http
            .get(format!("{}/api/sync/v1/folders", self.base))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Thông tin chia sẻ của một folder (chủ sở hữu, tư cách của mình, thành viên).
    pub async fn list_members(&self, folder_id: i64) -> AppResult<FolderMembersDto> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/folders/{folder_id}/members",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Thêm một thành viên; chỉ gửi user id, vai trò do server gán.
    pub async fn add_member(&self, folder_id: i64, user_id: i64) -> AppResult<MemberDto> {
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/folders/{folder_id}/members",
                self.base
            ))
            .headers(self.headers()?)
            .json(&serde_json::json!({ "userId": user_id }))
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Gỡ một thành viên khỏi folder.
    pub async fn remove_member(&self, folder_id: i64, member_id: i64) -> AppResult<()> {
        let response = self
            .http
            .delete(format!(
                "{}/api/sync/v1/folders/{folder_id}/members/{member_id}",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let _ = Self::map_response(response).await?;
        Ok(())
    }

    /// Tìm user có thể thêm làm thành viên của folder này (server giới hạn ≥2 ký tự, ≤10 kết quả).
    pub async fn search_member_candidates(
        &self,
        folder_id: i64,
        query: &str,
    ) -> AppResult<Vec<MemberUserDto>> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/folders/{folder_id}/member-candidates",
                self.base
            ))
            .query(&[("q", query)])
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Tạo hoặc upsert folder của chủ sở hữu hiện tại trên server.
    pub async fn create_folder(
        &self,
        name: &str,
        logical_root: &str,
        rules: &[RuleDto],
    ) -> AppResult<FolderDto> {
        let response = self
            .http
            .post(format!("{}/api/sync/v1/folders", self.base))
            .headers(self.headers()?)
            .json(&serde_json::json!({
                "name": name,
                "logical_root": logical_root,
                "enabled": true,
                "rules": rules,
            }))
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Xin server chuẩn bị một lượt tải lên: nhận storage key, kích thước phần, và có bị trùng
    /// nội dung hay không.
    pub async fn prepare(
        &self,
        folder_id: i64,
        logical_path: &str,
        size: i64,
        content_hash: &str,
        base_version_id: i64,
    ) -> AppResult<PrepareResponse> {
        let response = self
            .http
            .post(format!("{}/api/sync/v1/uploads/prepare", self.base))
            .headers(self.headers()?)
            .json(&serde_json::json!({
                "folder_id": folder_id,
                "logical_path": logical_path,
                "size": size,
                "content_hash": content_hash,
                "checksum_algorithm": "sha256",
                "base_version_id": base_version_id,
            }))
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Xin URL presigned để tải lên trực tiếp các phần đã liệt kê.
    pub async fn presign(
        &self,
        session_id: i64,
        part_numbers: &[i64],
    ) -> AppResult<Vec<PresignPart>> {
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/uploads/{session_id}/parts/presign",
                self.base
            ))
            .headers(self.headers()?)
            .json(&serde_json::json!({ "part_numbers": part_numbers }))
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        let body: serde_json::Value = response.json().await?;
        Ok(serde_json::from_value(body["parts"].clone())?)
    }

    /// Hoàn tất lượt tải lên với etag của từng phần; server ghép part và tạo version mới (hoặc
    /// báo xung đột).
    pub async fn finalize(
        &self,
        session_id: i64,
        parts: &[(i64, String)],
    ) -> AppResult<FinalizeResponse> {
        let payload: Vec<_> = parts
            .iter()
            .map(|(n, etag)| serde_json::json!({"part_number": n, "etag": etag}))
            .collect();
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/uploads/{session_id}/finalize",
                self.base
            ))
            .headers(self.headers()?)
            .json(&serde_json::json!({ "parts": payload }))
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// PUT trực tiếp bytes của một phần lên URL presigned; trả về etag để dùng lúc finalize.
    ///
    /// Nhận `Bytes` để lần thử lại gửi đúng buffer đã hash (clone chỉ tăng refcount), không đọc
    /// lại tệp. 403 từ storage trả `PresignedUrlRejected` để caller xin URL mới.
    pub async fn put_part(url: &str, bytes: bytes::Bytes) -> AppResult<String> {
        tracing::info!(target = %Self::sanitize_url(url), "uploading part");
        let timeout = part_upload_timeout(bytes.len());
        let response = storage_upload_http()?
            .put(url)
            .timeout(timeout)
            .body(bytes)
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            if status.as_u16() == 403 {
                return Err(AppError::PresignedUrlRejected(403));
            }
            return Err(AppError::Message(format!("Tải phần thất bại ({status})")));
        }
        let etag = response
            .headers()
            .get("etag")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .trim_matches('"')
            .to_string();
        Ok(etag)
    }

    /// Đọc chi tiết một tệp trên server theo id.
    pub async fn get_file(&self, file_id: i64) -> AppResult<FileDetailDto> {
        let response = self
            .http
            .get(format!("{}/api/sync/v1/files/{file_id}", self.base))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Đọc một trang lịch sử version của một tệp.
    pub async fn get_file_versions(
        &self,
        file_id: i64,
        limit: i64,
        offset: i64,
    ) -> AppResult<FileVersionListDto> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/files/{file_id}/versions",
                self.base
            ))
            .query(&[("limit", limit), ("offset", offset)])
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Đọc chi tiết một version cụ thể.
    pub async fn get_file_version(
        &self,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<FileVersionDto> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/files/{file_id}/versions/{version_id}",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Yêu cầu server phục hồi một version cũ thành version hiện hành mới.
    pub async fn restore_file_version(
        &self,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<FileVersionDto> {
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/files/{file_id}/versions/{version_id}/restore",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Đọc một trang change feed của folder, bắt đầu sau cursor `after`.
    pub async fn folder_changes(
        &self,
        folder_id: i64,
        after: i64,
        limit: i64,
    ) -> AppResult<FolderChangesDto> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/folders/{folder_id}/changes",
                self.base
            ))
            .query(&[("after", after), ("limit", limit)])
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Đọc một trang danh sách tệp của folder, dùng cho reconciliation toàn bộ.
    pub async fn folder_files(
        &self,
        folder_id: i64,
        limit: i64,
        offset: i64,
    ) -> AppResult<FolderFileListDto> {
        let response = self
            .http
            .get(format!(
                "{}/api/sync/v1/folders/{folder_id}/files",
                self.base
            ))
            .query(&[("limit", limit), ("offset", offset)])
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Xin server cấp URL presigned để tải một version cụ thể xuống.
    pub async fn authorize_download(
        &self,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<DownloadAuthDto> {
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/files/{file_id}/versions/{version_id}/download",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }

    /// Mở (hoặc tham gia) một phiên chỉnh sửa ONLYOFFICE cho một tệp.
    pub async fn open_office_session(&self, file_id: i64) -> AppResult<OfficeSessionDto> {
        let response = self
            .http
            .post(format!(
                "{}/api/sync/v1/files/{file_id}/office/session",
                self.base
            ))
            .headers(self.headers()?)
            .send()
            .await?;
        let response = Self::map_response(response).await?;
        Ok(response.json().await?)
    }
}

/// Dịch lỗi HTTP của server thành thông báo tiếng Việt dễ hiểu cho người dùng — bao gồm các lý
/// do từ chối theo tình trạng mẫu (đã lưu trữ, đã kết thúc) mà server enforce, ở đây chỉ diễn
/// giải lại, không tự quyết định.
pub fn map_http_error(status: u16, body: &str) -> AppError {
    let lower = body.to_ascii_lowercase();
    if status == 403 && lower.contains("folder is disabled") {
        return AppError::Message(
            "Thư mục đang bị quản trị viên tạm tắt trên máy chủ. Tệp sẽ tự tải lên khi thư mục được bật lại."
                .into(),
        );
    }
    if status == 403 || status == 404 {
        return AppError::Forbidden(status);
    }
    if status == 409 && lower.contains("already a member") {
        return AppError::Message("Người này đã là thành viên của thư mục".into());
    }
    if status == 409 && lower.contains("owner cannot be removed") {
        return AppError::Message("Không gỡ được chủ sở hữu khỏi thư mục".into());
    }
    if status == 400 && lower.contains("user cannot be added") {
        return AppError::Message("Không thêm được người dùng này vào thư mục".into());
    }
    if status == 409 && lower.contains("checked out") {
        return AppError::Message("Tệp đang được khóa chỉnh sửa trên thiết bị khác".into());
    }
    if status == 409 && lower.contains("archived") {
        return AppError::Message("Thư mục đã lưu trữ, không nhận tải lên mới".into());
    }
    if status == 409 && lower.contains("sample is closed") {
        return AppError::Message("Mẫu đã kết thúc, không nhận chỉnh sửa mới".into());
    }
    if status == 409 && lower.contains("not available") {
        return AppError::Message(
            "Đối tượng lưu trữ của phiên bản này không còn trên máy chủ".into(),
        );
    }
    if status == 400 && lower.contains("unsupported office") {
        return AppError::Message("Định dạng tệp không hỗ trợ chỉnh sửa trực tuyến".into());
    }
    if status == 503 && lower.contains("onlyoffice") {
        return AppError::Message(
            "Máy chủ ONLYOFFICE chưa được cấu hình hoặc không khả dụng".into(),
        );
    }
    AppError::Message(format!("{status}: {body}"))
}

/// True nếu lỗi có khả năng là tạm thời (mạng, 502/503/504, timeout, ...) và đáng thử lại.
pub fn is_retryable(err: &AppError) -> bool {
    match err {
        AppError::Http(msg) => {
            let lower = msg.to_ascii_lowercase();
            lower.contains("timeout")
                || lower.contains("connect")
                || lower.contains("sending request")
                || lower.contains("connection reset")
        }
        AppError::Message(msg) => {
            let lower = msg.to_ascii_lowercase();
            lower.contains("502")
                || lower.contains("503")
                || lower.contains("504")
                || lower.contains("timeout")
                || lower.contains("connection reset")
                || lower.contains("temporarily unavailable")
                || lower.contains("đã thay đổi trong lúc tải lên")
                || lower.contains("tải xuống cần bắt đầu lại")
                || lower.contains("đang được chương trình khác")
                || lower.contains("tạm tắt")
        }
        AppError::Io(_) => true,
        AppError::Connectivity(_) => true,
        AppError::PresignedUrlRejected(_) => true,
        _ => false,
    }
}

/// Các folder trên server mà máy này chưa gắn với thư mục cục bộ nào, tách theo tư cách:
/// `shared` = mình là thành viên ("Được chia sẻ với bạn"), `owned` = mình sở hữu (ví dụ vừa bấm
/// "Ngừng đồng bộ" trên máy này, hoặc tạo từ máy khác). Folder Sync Manager chỉ thấy nhờ quyền
/// quản trị, và folder của server cũ không gửi `my_role`, không nằm ở đây.
#[derive(Debug, Serialize, Default)]
pub struct UnboundFoldersDto {
    pub shared: Vec<FolderDto>,
    pub owned: Vec<FolderDto>,
}

/// Tách danh sách `GET /folders` thành các folder chưa gắn cục bộ, theo tư cách của người dùng.
pub fn unbound_folders(remotes: Vec<FolderDto>, bound_remote_ids: &[i64]) -> UnboundFoldersDto {
    let mut unbound = UnboundFoldersDto::default();
    for remote in remotes {
        if bound_remote_ids.contains(&remote.id) {
            continue;
        }
        match remote.my_role.as_deref() {
            Some("upload") => unbound.shared.push(remote),
            Some("owner") => unbound.owned.push(remote),
            _ => {}
        }
    }
    unbound
}

/// Chọn đúng folder để gắn, theo ID trên server — không bao giờ theo tên, nên không thể gắn nhầm
/// folder trùng `logical_root` hay tạo folder trùng lặp. Lỗi nếu server không (còn) cho thấy
/// folder đó với tư cách chủ sở hữu/thành viên, hoặc máy này đã gắn nó rồi.
pub fn folder_to_bind(
    remotes: Vec<FolderDto>,
    remote_id: i64,
    bound_remote_ids: &[i64],
) -> AppResult<FolderDto> {
    let unbound = unbound_folders(remotes, bound_remote_ids);
    unbound
        .shared
        .into_iter()
        .chain(unbound.owned)
        .find(|remote| remote.id == remote_id)
        .ok_or_else(|| AppError::Message("Thư mục không còn khả dụng hoặc đã được gắn".into()))
}

/// Trong nhiều folder cùng `logical_root`, ưu tiên folder do `user_id` sở hữu, rồi mới tới
/// folder đầu tiên khớp tên. Chỉ dùng trong test hiện tại (chưa được gọi từ code chạy thật).
#[cfg(test)]
pub fn select_remote_folder(
    folders: &[FolderDto],
    logical_root: &str,
    user_id: Option<i64>,
) -> Option<FolderDto> {
    let matches: Vec<FolderDto> = folders
        .iter()
        .filter(|folder| folder.logical_root == logical_root)
        .cloned()
        .collect();
    if let Some(user_id) = user_id {
        if let Some(own) = matches.iter().find(|folder| folder.user_id == user_id) {
            return Some(own.clone());
        }
    }
    matches.into_iter().next()
}

#[cfg(test)]
mod tests {
    use super::{
        folder_to_bind, is_retryable, map_http_error, select_remote_folder, unbound_folders,
        ApiClient, FileVersionDto, FileVersionListDto, FinalizeResponse, FolderDto,
        FolderMembersDto, PrepareResponse,
    };
    use crate::error::AppError;

    /// Timeout PUT part tăng theo kích thước ở tốc độ tối thiểu, không bao giờ dưới mức sàn.
    #[test]
    fn part_upload_timeout_scales_with_part_size() {
        use super::{part_upload_timeout, PART_UPLOAD_MIN_BYTES_PER_SEC, PART_UPLOAD_MIN_TIMEOUT};
        assert_eq!(part_upload_timeout(0), PART_UPLOAD_MIN_TIMEOUT);
        assert_eq!(part_upload_timeout(1024), PART_UPLOAD_MIN_TIMEOUT);
        let part = 16 * 1024 * 1024;
        assert_eq!(
            part_upload_timeout(part).as_secs(),
            part as u64 / PART_UPLOAD_MIN_BYTES_PER_SEC
        );
        assert!(part_upload_timeout(part) > PART_UPLOAD_MIN_TIMEOUT);
    }

    /// Payload finalize dạng "conflict" phải giữ đúng conflict_id và server_version_id khác
    /// version_id đã tạo.
    #[test]
    fn maps_conflict_finalize_payload() {
        let parsed: FinalizeResponse = serde_json::from_str(
            r#"{"status":"conflict","file_id":1,"version_id":2,"version_number":2,"conflict_id":9,"server_version_id":1}"#,
        )
        .unwrap();
        assert_eq!(parsed.status, "conflict");
        assert_eq!(parsed.conflict_id, Some(9));
        assert_eq!(parsed.server_version_id, Some(1));
        assert_ne!(parsed.version_id, parsed.server_version_id);
    }

    /// Query chứa chữ ký presigned phải bị xóa khỏi URL đã sanitize.
    #[test]
    fn sanitizes_presigned_query_string() {
        let raw = "http://localhost:29000/medilab/sync/1/abc?X-Amz-Signature=secret";
        assert_eq!(
            ApiClient::sanitize_url(raw),
            "http://localhost:29000/medilab/sync/1/abc"
        );
        assert!(!ApiClient::sanitize_url(raw).contains("Signature"));
    }

    /// Lỗi hết phiên đăng nhập (401) không được coi là đáng thử lại.
    #[test]
    fn expired_auth_is_not_retryable() {
        assert!(!is_retryable(&AppError::Unauthenticated));
        assert!(!is_retryable(&AppError::Message("401: expired".into())));
    }

    /// Tệp đổi giữa lúc tải lên, hoặc folder tạm tắt, đáng thử lại; tệp không còn trên đĩa
    /// thì không.
    #[test]
    fn changed_file_during_upload_is_retryable() {
        assert!(is_retryable(&AppError::Message(
            "Tệp đã thay đổi trong lúc tải lên, sẽ thử lại".into()
        )));
        assert!(is_retryable(&map_http_error(
            403,
            r#"{"detail":"Folder is disabled"}"#
        )));
        assert!(!is_retryable(&AppError::Message(
            "Tệp không còn trên đĩa: ABC.xlsx".into()
        )));
    }

    /// Khi nhiều folder cùng tên, chọn folder của chính người dùng trước; nếu không phải chủ,
    /// rơi về folder chia sẻ khớp tên đầu tiên; tên không khớp thì không chọn gì.
    #[test]
    fn select_remote_folder_prefers_own_then_membership() {
        let own = FolderDto {
            id: 8,
            name: "LabResults".into(),
            logical_root: "LabResults".into(),
            sync_mode: "upload_only".into(),
            enabled: true,
            device_id: 1,
            user_id: 10,
            rules: vec![],
            sample_name: None,
            sample_code: None,
            category: None,
            workflow_status: None,
            nguon_thiet_bi: None,
            owner_name: None,
            my_role: None,
            can_manage_members: false,
        };
        let shared = FolderDto {
            id: 3,
            name: "LabResults".into(),
            logical_root: "LabResults".into(),
            sync_mode: "upload_only".into(),
            enabled: true,
            device_id: 2,
            user_id: 1,
            rules: vec![],
            sample_name: None,
            sample_code: None,
            category: None,
            workflow_status: None,
            nguon_thiet_bi: None,
            owner_name: None,
            my_role: None,
            can_manage_members: false,
        };
        let folders = vec![shared.clone(), own.clone()];
        assert_eq!(
            select_remote_folder(&folders, "LabResults", Some(10))
                .unwrap()
                .id,
            8
        );
        assert_eq!(
            select_remote_folder(&folders, "LabResults", Some(99))
                .unwrap()
                .id,
            3
        );
        assert!(select_remote_folder(&folders, "Other", Some(10)).is_none());
    }

    /// Parse payload lịch sử version phải giữ đúng thứ tự mới-nhất-trước và cờ `is_canonical`.
    #[test]
    fn decodes_version_history_newest_first() {
        let parsed: FileVersionListDto = serde_json::from_str(
            r#"{
                "file_id": 10,
                "total": 3,
                "limit": 20,
                "offset": 0,
                "items": [
                    {
                        "id": 30,
                        "file_id": 10,
                        "version_number": 3,
                        "size": 12,
                        "content_hash": "aaa",
                        "checksum_algorithm": "sha256",
                        "source": "DESKTOP_SYNC",
                        "created_at": "2026-08-27 10:00:00",
                        "created_by": {"id": 1, "name": "A"},
                        "device": {"id": 2, "name": "LAB-01"},
                        "is_canonical": true,
                        "parent_version_id": 20,
                        "restored_from_version_id": null,
                        "object_available": null,
                        "can_restore": true
                    },
                    {
                        "id": 20,
                        "file_id": 10,
                        "version_number": 2,
                        "size": 11,
                        "content_hash": "bbb",
                        "checksum_algorithm": "sha256",
                        "source": "CONFLICT",
                        "created_at": "2026-08-27 09:00:00",
                        "created_by": {"id": 1, "name": "A"},
                        "device": {"id": 3, "name": "LAB-02"},
                        "is_canonical": false,
                        "parent_version_id": 10,
                        "restored_from_version_id": null,
                        "object_available": null,
                        "can_restore": true
                    }
                ]
            }"#,
        )
        .unwrap();
        assert_eq!(parsed.total, 3);
        assert_eq!(parsed.limit, 20);
        assert_eq!(parsed.items[0].version_number, 3);
        assert!(parsed.items[0].is_canonical);
        assert_eq!(parsed.items[1].source, "CONFLICT");
        assert!(!parsed.items[1].is_canonical);
        assert!(parsed.items[0].version_number > parsed.items[1].version_number);
    }

    /// Parse payload phục hồi version phải giữ đúng `restored_from_version_id` và
    /// `current_version_id` mới.
    #[test]
    fn decodes_restore_response() {
        let parsed: FileVersionDto = serde_json::from_str(
            r#"{
                "id": 40,
                "file_id": 10,
                "version_number": 4,
                "size": 12,
                "content_hash": "aaa",
                "checksum_algorithm": "sha256",
                "source": "RESTORE",
                "created_at": "2026-08-27 11:00:00",
                "created_by": {"id": 1, "name": "A"},
                "device": {"id": 2, "name": "LAB-01"},
                "is_canonical": true,
                "parent_version_id": 30,
                "restored_from_version_id": 10,
                "object_available": true,
                "can_restore": true,
                "current_version_id": 40
            }"#,
        )
        .unwrap();
        assert_eq!(parsed.source, "RESTORE");
        assert_eq!(parsed.restored_from_version_id, Some(10));
        assert_eq!(parsed.parent_version_id, Some(30));
        assert_eq!(parsed.current_version_id, Some(40));
        assert!(parsed.is_canonical);
    }

    /// Parse chi tiết phiên bản lịch sử với các ràng buộc khôi phục và đối tượng lưu trữ.
    #[test]
    fn decodes_historical_version_with_restore_constraints() {
        let parsed: FileVersionDto = serde_json::from_str(
            r#"{
                "id": 20,
                "file_id": 10,
                "version_number": 2,
                "size": 1024,
                "content_hash": "hash2",
                "checksum_algorithm": "sha256",
                "source": "ONLYOFFICE",
                "created_at": "2026-09-19 05:47:00",
                "created_by": {"id": 1, "name": "Tech A"},
                "device": {"id": 2, "name": "LAB-01"},
                "is_canonical": false,
                "parent_version_id": 10,
                "restored_from_version_id": null,
                "object_available": false,
                "can_restore": true
            }"#,
        )
        .unwrap();
        assert!(!parsed.is_canonical);
        assert_eq!(parsed.version_number, 2);
        assert_eq!(parsed.object_available, Some(false));
        assert!(parsed.can_restore);
    }

    /// Dựng một FolderDto tối thiểu cho test danh sách chia sẻ.
    fn shared_fixture(id: i64, logical_root: &str, my_role: Option<&str>) -> FolderDto {
        serde_json::from_value(serde_json::json!({
            "id": id,
            "name": logical_root,
            "logical_root": logical_root,
            "sync_mode": "upload_only",
            "enabled": true,
            "rules": [],
            "owner_name": "Dr. A",
            "my_role": my_role,
        }))
        .unwrap()
    }

    /// Id của một nhóm folder, để so trong test.
    fn ids(folders: &[FolderDto]) -> Vec<i64> {
        folders.iter().map(|folder| folder.id).collect()
    }

    /// "Được chia sẻ với bạn" chỉ gồm folder mình là thành viên và máy này chưa gắn; folder mình
    /// sở hữu chưa gắn nằm ở nhóm riêng; folder chỉ thấy nhờ quyền manager và folder server cũ
    /// không gửi vai trò thì không hiện ở đâu cả.
    #[test]
    fn unbound_folders_split_by_role_and_exclude_locally_bound() {
        let remotes = vec![
            shared_fixture(1, "MineBound", Some("owner")),
            shared_fixture(2, "SharedBound", Some("upload")),
            shared_fixture(3, "SharedFree", Some("upload")),
            shared_fixture(4, "Managed", Some("manager")),
            shared_fixture(5, "Legacy", None),
            shared_fixture(6, "MineFree", Some("owner")),
        ];
        let unbound = unbound_folders(remotes, &[1, 2]);
        assert_eq!(ids(&unbound.shared), vec![3]);
        assert_eq!(ids(&unbound.owned), vec![6]);
    }

    /// Server cho thấy A, B, C (đều được chia sẻ); máy đã gắn A, C → chỉ B hiện. Gắn B → danh
    /// sách rỗng. Ngừng đồng bộ B trên máy này (bỏ binding) → B hiện lại, gắn lại được theo id.
    #[test]
    fn shared_list_follows_local_bind_and_unbind() {
        let remotes = || {
            vec![
                shared_fixture(1, "A", Some("upload")),
                shared_fixture(2, "B", Some("upload")),
                shared_fixture(3, "C", Some("upload")),
            ]
        };
        assert_eq!(ids(&unbound_folders(remotes(), &[1, 3]).shared), vec![2]);
        assert_eq!(folder_to_bind(remotes(), 2, &[1, 3]).unwrap().id, 2);
        assert!(unbound_folders(remotes(), &[1, 3, 2]).shared.is_empty());
        assert!(folder_to_bind(remotes(), 2, &[1, 3, 2]).is_err());
        assert_eq!(ids(&unbound_folders(remotes(), &[1, 3]).shared), vec![2]);
        assert_eq!(folder_to_bind(remotes(), 2, &[1, 3]).unwrap().id, 2);
    }

    /// Gắn folder chọn theo remote id, kể cả khi mình có folder riêng trùng tên; chủ sở hữu gắn
    /// lại được folder của mình sau khi bỏ binding; id không thấy được, chỉ thấy nhờ quyền
    /// manager, hoặc đã gắn thì từ chối.
    #[test]
    fn bind_selects_folder_by_remote_id_not_name() {
        let remotes = || {
            vec![
                shared_fixture(10, "LabResults", Some("owner")),
                shared_fixture(11, "LabResults", Some("upload")),
                shared_fixture(12, "LabResults", Some("manager")),
            ]
        };
        assert_eq!(folder_to_bind(remotes(), 11, &[10]).unwrap().id, 11);
        assert_eq!(folder_to_bind(remotes(), 10, &[11]).unwrap().id, 10);
        assert!(folder_to_bind(remotes(), 12, &[]).is_err());
        assert!(folder_to_bind(remotes(), 11, &[11]).is_err());
        assert!(folder_to_bind(remotes(), 99, &[]).is_err());
    }

    /// Response folder của server cũ (không có owner_name/my_role/can_manage_members) vẫn đọc
    /// được với mặc định an toàn; response mới đọc đủ các field chia sẻ.
    #[test]
    fn folder_dto_sharing_fields_are_backward_compatible() {
        let legacy: FolderDto = serde_json::from_str(
            r#"{"id":1,"name":"A","logical_root":"A","sync_mode":"upload_only","enabled":true,"rules":[]}"#,
        )
        .unwrap();
        assert!(legacy.owner_name.is_none());
        assert!(legacy.my_role.is_none());
        assert!(!legacy.can_manage_members);

        let current: FolderDto = serde_json::from_str(
            r#"{"id":1,"name":"A","logical_root":"A","sync_mode":"upload_only","enabled":true,"rules":[],
                "owner_name":"Dr. A","my_role":"upload","can_manage_members":false,"future_field":1}"#,
        )
        .unwrap();
        assert_eq!(current.owner_name.as_deref(), Some("Dr. A"));
        assert_eq!(current.my_role.as_deref(), Some("upload"));

        let members: FolderMembersDto = serde_json::from_str(
            r#"{"folder_id":1,"owner":{"id":2,"name":"Dr. A"},"my_role":"upload",
                "members":[{"id":9,"user":{"id":3,"name":"B","login":"b"},"role":"upload","effective_access":false}]}"#,
        )
        .unwrap();
        assert!(!members.can_manage_members);
        assert!(!members.members[0].effective_access);
    }

    /// Lỗi 403/thư mục tắt/409-object-không-còn phải dịch ra đúng thông báo, và lỗi thiếu
    /// object thì không đáng thử lại.
    #[test]
    fn maps_permission_and_missing_object_errors() {
        let forbidden = map_http_error(403, r#"{"detail":"File not found"}"#);
        assert!(forbidden.to_string().contains("Không có quyền"));
        // 403/404 mang kiểu riêng để engine nhận ra mất quyền mà không so chuỗi; không thử lại,
        // và không bị coi là hết phiên (401 mới là chuyện phiên/thiết bị).
        assert!(matches!(forbidden, AppError::Forbidden(403)));
        assert!(matches!(
            map_http_error(404, r#"{"detail":"Folder not found"}"#),
            AppError::Forbidden(404)
        ));
        assert!(!is_retryable(&forbidden));
        assert!(!crate::error::is_odoo_auth_failure(&forbidden));
        let disabled = map_http_error(403, r#"{"detail":"Folder is disabled"}"#);
        // Folder bị quản trị tắt: không phải mất quyền, và job chờ thử lại tới khi được bật lại.
        assert!(disabled.to_string().contains("tạm tắt"));
        assert!(is_retryable(&disabled));
        assert!(!matches!(disabled, AppError::Forbidden(_)));
        let missing = map_http_error(409, r#"{"detail":"Historical object is not available"}"#);
        assert!(missing.to_string().contains("không còn trên máy chủ"));
        assert!(!is_retryable(&missing));
    }

    /// Parse change feed và download-auth phải giữ đúng dữ liệu và không bao giờ lộ
    /// `storage_key` ra ngoài.
    #[test]
    fn decodes_change_feed_and_download_auth() {
        let changes: crate::api::FolderChangesDto = serde_json::from_str(
            r#"{
                "folder_id": 1,
                "changes": [{
                    "id": 101,
                    "change_type": "CANONICAL_VERSION",
                    "folder_id": 1,
                    "file_id": 10,
                    "logical_path": "ABC.xlsx",
                    "current_version_id": 5,
                    "version_number": 5,
                    "content_hash": "abc",
                    "size": 12,
                    "source": "RESTORE",
                    "changed_at": "2026-08-27 12:00:00",
                    "changed_by_device_id": 3
                }],
                "next_cursor": 101,
                "has_more": false,
                "limit": 50
            }"#,
        )
        .unwrap();
        assert_eq!(changes.next_cursor, 101);
        assert_eq!(changes.changes[0].source.as_deref(), Some("RESTORE"));
        assert!(!format!("{:?}", changes).contains("storage_key"));
        let auth: crate::api::DownloadAuthDto = serde_json::from_str(
            r#"{"file_id":10,"version_id":5,"version_number":5,"size":12,"content_hash":"abc","checksum_algorithm":"sha256","url":"http://localhost:29000/medilab/x","expires_in":900}"#,
        )
        .unwrap();
        assert_eq!(auth.version_id, 5);
        assert!(auth.url.contains("localhost:29000"));
    }

    /// Parse phiên ONLYOFFICE phải giữ đúng dữ liệu và không bao giờ lộ `storage_key`/`api_key`
    /// khi serialize lại.
    #[test]
    fn decodes_office_session_without_exposing_storage_key() {
        let parsed: crate::api::OfficeSessionDto = serde_json::from_str(
            r#"{
                "session_id": 3,
                "file_id": 10,
                "base_version_id": 4,
                "document_key": "ooabc",
                "created": true,
                "state": "open",
                "document_server_url": "http://localhost:28880",
                "document_type": "cell",
                "file_type": "xlsx",
                "config": {
                    "documentType": "cell",
                    "width": "100%",
                    "height": "100%",
                    "document": {
                        "fileType": "xlsx",
                        "key": "ooabc",
                        "title": "ABC.xlsx",
                        "url": "http://odoo:8069/api/sync/v1/office/source/tok",
                        "permissions": {"edit": true, "download": false, "print": false, "comment": true}
                    },
                    "editorConfig": {
                        "mode": "edit",
                        "lang": "vi",
                        "type": "desktop",
                        "callbackUrl": "http://odoo:8069/api/sync/v1/office/callback/tok",
                        "user": {"id": "2", "name": "Kỹ thuật viên A"},
                        "customization": {"autosave": true, "forcesave": false, "uiTheme": "theme-gray", "futureOption": 7}
                    },
                    "token": "header.payload.sig"
                }
            }"#,
        )
        .unwrap();
        assert_eq!(parsed.session_id, 3);
        // Config đi qua lớp Rust rồi mới tới webview: `uiTheme` (và tùy chỉnh server thêm sau này)
        // không được rơi mất khi serialize lại, nếu không editor sẽ theo theme tối của hệ điều hành.
        let forwarded = serde_json::to_value(&parsed).unwrap();
        let customization = &forwarded["config"]["editorConfig"]["customization"];
        assert_eq!(customization["uiTheme"], "theme-gray");
        assert_eq!(customization["futureOption"], 7);
        assert_eq!(customization["autosave"], true);
        assert_eq!(parsed.document_key, "ooabc");
        assert_eq!(parsed.config.editor_config.user.id, "2");
        assert!(!parsed.config.document.permissions.download);
        let dumped = serde_json::to_string(&parsed).unwrap();
        assert!(!dumped.contains("storage_key"));
        assert!(!dumped.contains("api_key"));
    }

    /// Parse ngữ cảnh mẫu LIMS (tên/mã mẫu, category, tình trạng, nguồn thiết bị) trên folder;
    /// payload cũ thiếu các field này vẫn parse được với giá trị rỗng.
    #[test]
    fn decodes_lab_folder_context() {
        let parsed: FolderDto = serde_json::from_str(
            r#"{
                "id": 9,
                "name": "Kết quả · Mẫu A",
                "logical_root": "HS.1-result",
                "sync_mode": "upload_only",
                "enabled": true,
                "device_id": 1,
                "user_id": 2,
                "rules": [],
                "sample_name": "Mẫu A",
                "sample_code": "HS.1",
                "category": "result",
                "workflow_status": "dang_thuc_hien",
                "nguon_thiet_bi": "Analyzer-X"
            }"#,
        )
        .unwrap();
        assert_eq!(parsed.sample_name.as_deref(), Some("Mẫu A"));
        assert_eq!(parsed.category.as_deref(), Some("result"));
        assert_eq!(parsed.nguon_thiet_bi.as_deref(), Some("Analyzer-X"));
        let legacy: FolderDto = serde_json::from_str(
            r#"{"id":1,"name":"Lab","logical_root":"Lab","sync_mode":"upload_only","enabled":true,"rules":[]}"#,
        )
        .unwrap();
        assert!(legacy.sample_name.is_none());
        assert!(legacy.category.is_none());
    }

    /// Lỗi 409 "checked out" dịch thành thông báo "khóa"; lỗi 409 "Sample is closed" dịch thành
    /// thông báo "kết thúc".
    #[test]
    fn maps_checkout_and_closed_sample_errors() {
        assert!(map_http_error(409, r#"{"detail":"File is checked out"}"#)
            .to_string()
            .contains("khóa"));
        assert!(map_http_error(409, r#"{"detail":"Sample is closed"}"#)
            .to_string()
            .contains("kết thúc"));
    }

    /// Lỗi 400 "unsupported office type" phải dịch thành thông báo không hỗ trợ chỉnh sửa.
    #[test]
    fn maps_unsupported_office_type() {
        let err = map_http_error(400, r#"{"detail":"Unsupported office type"}"#);
        assert!(err.to_string().contains("không hỗ trợ"));
    }

    /// `object_reused` phải mặc định false khi server không gửi field đó trong payload.
    #[test]
    fn prepare_defaults_object_reused_false() {
        let parsed: PrepareResponse = serde_json::from_str(
            r#"{"session_id":1,"file_id":2,"deduplicated":false,"version_id":null,"version_number":null,"part_size":1,"storage_key":"sync/2/abc","s3_upload_id":"u","expires_at":null}"#,
        )
        .unwrap();
        assert!(!parsed.object_reused);
        assert!(!parsed.deduplicated);
    }
}
