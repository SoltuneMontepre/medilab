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
            .user_agent(concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")))
            .redirect(reqwest::redirect::Policy::none())
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
            .redirect(reqwest::redirect::Policy::none())
            .build()
    })
}

/// Client HTTP dùng chung để GET tệp qua presigned URL (MinIO/S3). Không có timeout tổng: tệp
/// lớn trên mạng chậm là hợp lệ; kết nối treo (không nhận được byte nào) bị cắt bằng read timeout.
pub(crate) fn storage_download_http() -> AppResult<reqwest::Client> {
    shared_client(&STORAGE_DOWNLOAD_HTTP, || {
        reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .redirect(reqwest::redirect::Policy::none())
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
pub struct LoginResponse {
    pub api_key: String,
    pub device_id: i64,
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
    #[serde(default)]
    pub next_after: Option<i64>,
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

async fn send(request: reqwest::RequestBuilder) -> AppResult<reqwest::Response> {
    for attempt in 1..=3 {
        let cloned = request
            .try_clone()
            .ok_or_else(|| AppError::Message("Không thể gửi lại yêu cầu".into()))?;
        match ApiClient::map_response(send_once(cloned).await?).await {
            Ok(response) => return Ok(response),
            Err(AppError::Api {
                ref code,
                retry_after,
                ..
            }) if attempt < 3
                && matches!(
                    code.as_str(),
                    "too_many_attempts" | "try_again" | "storage_unavailable"
                ) =>
            {
                let delay = crate::sync::retry::backoff_secs(attempt).max(retry_after.unwrap_or(0));
                tokio::time::sleep(Duration::from_secs(delay as u64)).await;
            }
            Err(err) => return Err(err),
        }
    }
    unreachable!()
}

async fn send_once(request: reqwest::RequestBuilder) -> AppResult<reqwest::Response> {
    let request = request.header(
        "User-Agent",
        concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")),
    );
    #[cfg(not(test))]
    {
        Ok(request.send().await?)
    }
    #[cfg(test)]
    {
        let (client, request) = request.build_split();
        let request = request?;
        let method = request.method().as_str().to_string();
        let url = request.url().clone();
        let headers = request
            .headers()
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_str().unwrap().into()))
            .collect();
        crate::contract::request(
            &method,
            &url,
            &headers,
            request
                .body()
                .and_then(|b| b.as_bytes())
                .unwrap_or_default(),
        );
        let response = client.execute(request).await?;
        let status = response.status();
        let headers = response.headers().clone();
        let body = response.bytes().await?;
        let header_values = headers
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_str().unwrap().into()))
            .collect();
        crate::contract::response(&method, url.path(), status.as_u16(), &header_values, &body);
        let mut restored = http::Response::builder().status(status);
        *restored.headers_mut().unwrap() = headers;
        Ok(reqwest::Response::from(restored.body(body).unwrap()))
    }
}

impl ApiClient {
    pub fn new(base: &str, api_key: &str, device_id: i64) -> AppResult<Self> {
        crate::server_url::endpoint(base, "medilab/api/v1")?;
        Ok(Self {
            http: odoo_http()?,
            base: base.trim_end_matches('/').into(),
            api_key: api_key.into(),
            device_id,
        })
    }

    #[cfg(test)]
    pub fn device_id(&self) -> i64 {
        self.device_id
    }

    fn headers(&self) -> AppResult<HeaderMap> {
        let mut headers = HeaderMap::new();
        let mut value = HeaderValue::from_str(&format!("Bearer {}", self.api_key))
            .map_err(|_| AppError::Message("Khóa thiết bị không hợp lệ".into()))?;
        value.set_sensitive(true);
        headers.insert(AUTHORIZATION, value);
        Ok(headers)
    }

    fn url(&self, path: &str) -> AppResult<url::Url> {
        crate::server_url::endpoint(&self.base, &format!("medilab/api/v1/{path}"))
    }

    async fn map_response(response: reqwest::Response) -> AppResult<reqwest::Response> {
        if response.status().is_success() {
            return Ok(response);
        }
        let status = response.status().as_u16();
        let retry_after = response
            .headers()
            .get("Retry-After")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse::<i64>().ok())
            .filter(|v| *v >= 0);
        let body = response.text().await.unwrap_or_default();
        let mut error = map_http_error(status, &body);
        if let AppError::Api {
            retry_after: wait, ..
        } = &mut error
        {
            *wait = retry_after;
        }
        Err(error)
    }

    pub fn sanitize_url(url: &str) -> String {
        url.split('?').next().unwrap_or("[invalid-url]").into()
    }

    pub async fn login(
        base: &str,
        login: &str,
        password: &str,
        device_name: &str,
        os: &str,
        _app_version: &str,
        client_uid: &str,
    ) -> AppResult<LoginResponse> {
        let url = crate::server_url::endpoint(base, "medilab/api/v1/sign-in")?;
        let response=send(odoo_http()?.post(url).timeout(LOGIN_TIMEOUT).json(&serde_json::json!({
            "login": login, "password": password, "name": device_name, "platform": os, "client_uid": client_uid,
        }))).await?;
        let wire: crate::wire::SignedIn = Self::map_response(response).await?.json().await?;
        Ok(LoginResponse {
            api_key: wire.key,
            device_id: wire.device.id,
        })
    }

    pub async fn devices(&self) -> AppResult<Vec<crate::wire::Device>> {
        let response = send(self.http.get(self.url("devices")?).headers(self.headers()?)).await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::Devices>()
            .await?
            .devices)
    }

    pub async fn me(&self) -> AppResult<()> {
        let devices = self.devices().await?;
        if devices.iter().any(|d| {
            d.id == self.device_id
                && d.current
                && d.status == "signed_in"
                && matches!(d.platform.as_str(), "linux" | "windows")
        }) {
            Ok(())
        } else {
            Err(AppError::Unauthenticated)
        }
    }

    pub async fn revoke_device(&self, device_id: i64) -> AppResult<()> {
        let response = send(
            self.http
                .post(self.url(&format!("devices/{device_id}/revoke"))?)
                .headers(self.headers()?),
        )
        .await?;
        Self::map_response(response).await?;
        Ok(())
    }

    pub async fn logout(&self) -> AppResult<()> {
        match send(
            self.http
                .post(self.url("sign-out")?)
                .headers(self.headers()?),
        )
        .await
        {
            Ok(_) | Err(AppError::Unauthenticated) => Ok(()),
            Err(err) => Err(err),
        }
    }

    async fn rules(&self, folder_id: i64) -> AppResult<Vec<RuleDto>> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/rules"))?)
                .headers(self.headers()?),
        )
        .await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::Rules>()
            .await?
            .rules
            .into_iter()
            .map(Into::into)
            .collect())
    }

    pub async fn list_folders(&self) -> AppResult<Vec<FolderDto>> {
        let response = send(self.http.get(self.url("folders")?).headers(self.headers()?)).await?;
        let wire: crate::wire::Folders = Self::map_response(response).await?.json().await?;
        let mut folders = Vec::new();
        for f in wire.folders {
            let rules = self.rules(f.id).await?;
            folders.push(f.into_dto(rules));
        }
        Ok(folders)
    }

    pub async fn list_members(&self, folder_id: i64) -> AppResult<FolderMembersDto> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/members"))?)
                .headers(self.headers()?),
        )
        .await?;
        let members = Self::map_response(response)
            .await?
            .json::<crate::wire::Members>()
            .await?
            .members;
        let folder = self
            .list_folders()
            .await?
            .into_iter()
            .find(|f| f.id == folder_id)
            .ok_or(AppError::Forbidden(404))?;
        let owner = members
            .iter()
            .find(|m| m.role == "owner")
            .map(|m| m.user.clone())
            .ok_or_else(|| AppError::Message("Thiếu chủ sở hữu thư mục".into()))?;
        Ok(FolderMembersDto {
            folder_id,
            owner,
            my_role: folder.my_role.unwrap_or_default(),
            can_manage_members: folder.can_manage_members,
            mapped: folder.category.is_some(),
            members,
        })
    }

    pub async fn add_member(&self, folder_id: i64, user_id: i64) -> AppResult<MemberDto> {
        let response = send(
            self.http
                .post(self.url(&format!("folders/{folder_id}/members"))?)
                .headers(self.headers()?)
                .json(&serde_json::json!({"user_id":user_id})),
        )
        .await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::OneMember>()
            .await?
            .member)
    }

    pub async fn remove_member(&self, folder_id: i64, member_id: i64) -> AppResult<()> {
        let response = send(
            self.http
                .delete(self.url(&format!("folders/{folder_id}/members/{member_id}"))?)
                .headers(self.headers()?),
        )
        .await?;
        Self::map_response(response).await?;
        Ok(())
    }

    pub async fn search_member_candidates(
        &self,
        folder_id: i64,
        query: &str,
    ) -> AppResult<Vec<MemberUserDto>> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/member-candidates"))?)
                .headers(self.headers()?)
                .query(&[("q", query)]),
        )
        .await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::Candidates>()
            .await?
            .candidates)
    }

    pub async fn create_folder(
        &self,
        name: &str,
        _logical_root: &str,
        rules: &[RuleDto],
    ) -> AppResult<FolderDto> {
        let response = send(
            self.http
                .post(self.url("folders")?)
                .headers(self.headers()?)
                .header("Idempotency-Key", uuid::Uuid::new_v4().to_string())
                .json(&serde_json::json!({"name":name})),
        )
        .await?;
        let folder = Self::map_response(response)
            .await?
            .json::<crate::wire::OneFolder>()
            .await?
            .folder;
        for r in rules {
            let response=send(self.http.post(self.url(&format!("folders/{}/rules",folder.id))?).headers(self.headers()?).json(&serde_json::json!({"kind":r.r#type,"pattern":r.pattern,"recursive":r.recursive}))).await?;
            Self::map_response(response).await?;
        }
        let rules = self.rules(folder.id).await?;
        Ok(folder.into_dto(rules))
    }

    pub async fn prepare(
        &self,
        folder_id: i64,
        path: &str,
        size: i64,
        sha256: &str,
        base_version_id: i64,
        key: &str,
    ) -> AppResult<crate::wire::Upload> {
        let response=send(self.http.post(self.url(&format!("folders/{folder_id}/uploads"))?).headers(self.headers()?).header("Idempotency-Key",key).json(&serde_json::json!({
            "path":path,"size":size,"sha256":sha256,"base_version_id":(base_version_id > 0).then_some(base_version_id),
        }))).await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::OneUpload>()
            .await?
            .upload)
    }

    pub async fn upload(&self, folder_id: i64, id: i64) -> AppResult<crate::wire::Upload> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/uploads/{id}"))?)
                .headers(self.headers()?),
        )
        .await?;
        Ok(Self::map_response(response)
            .await?
            .json::<crate::wire::OneUpload>()
            .await?
            .upload)
    }

    pub async fn presign(
        &self,
        folder_id: i64,
        id: i64,
        numbers: &[i64],
    ) -> AppResult<Vec<PresignPart>> {
        let response = send(
            self.http
                .post(self.url(&format!("folders/{folder_id}/uploads/{id}/parts"))?)
                .headers(self.headers()?)
                .json(&serde_json::json!({"part_numbers":numbers})),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Parts>()
            .await?;
        let expires_in = crate::wire::ttl(&wire.expires_at);
        Ok(wire
            .parts
            .into_iter()
            .map(|p| PresignPart {
                part_number: p.number,
                url: p.url,
                expires_in,
            })
            .collect())
    }

    pub async fn finalize(
        &self,
        folder_id: i64,
        id: i64,
        _parts: &[(i64, String)],
    ) -> AppResult<FinalizeResponse> {
        let response = send(
            self.http
                .post(self.url(&format!("folders/{folder_id}/uploads/{id}/finalize"))?)
                .headers(self.headers()?),
        )
        .await?;
        let mut upload = Self::map_response(response)
            .await?
            .json::<crate::wire::OneUpload>()
            .await?
            .upload;
        for _ in 0..30 {
            match upload.status.as_str() {
                "completed" | "conflict" | "unchanged" => {
                    let file = self
                        .file_by_path(
                            folder_id,
                            &upload.path,
                            upload.version.as_ref().map(|v| v.id),
                        )
                        .await?;
                    return Ok(FinalizeResponse {
                        status: upload.status,
                        file_id: file.id,
                        version_id: upload.version.as_ref().map(|v| v.id),
                        version_number: upload.version.as_ref().map(|v| v.number),
                        conflict_id: None,
                        server_version_id: file.current_version_id,
                    });
                }
                "failed" => {
                    return Err(AppError::UploadFailed(
                        upload
                            .failure_code
                            .unwrap_or_else(|| "verification_failed".into()),
                    ))
                }
                "expired" => return Err(AppError::UploadExpired),
                "refused" => {
                    let code = upload.failure_code.unwrap_or_default();
                    let status = match code.as_str() {
                        "device_revoked" | "permission_denied" => 403,
                        "invalid_key" => 401,
                        "not_found" => 404,
                        _ => 409,
                    };
                    return Err(map_http_error(
                        status,
                        &serde_json::json!({"error":{"code":code,"message":"Tải lên bị từ chối"}})
                            .to_string(),
                    ));
                }
                "verifying" => {}
                _ => return Err(AppError::Message("Trạng thái tải lên không hợp lệ".into())),
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
            upload = self.upload(folder_id, id).await?;
        }
        Err(AppError::UploadPending)
    }

    pub async fn put_part(url: &str, bytes: bytes::Bytes) -> AppResult<String> {
        let response = storage_upload_http()?
            .put(url)
            .timeout(part_upload_timeout(bytes.len()))
            .body(bytes)
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status().as_u16();
            return Err(if status == 403 {
                AppError::PresignedUrlRejected(status)
            } else {
                AppError::StorageStatus(status)
            });
        }
        Ok(response
            .headers()
            .get("etag")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .trim_matches('"')
            .into())
    }

    pub async fn folder_files(
        &self,
        folder_id: i64,
        limit: i64,
        after: i64,
    ) -> AppResult<FolderFileListDto> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/files"))?)
                .headers(self.headers()?)
                .query(&[("limit", limit), ("after", after)]),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Files>()
            .await?;
        Ok(FolderFileListDto {
            folder_id,
            total: 0,
            limit,
            offset: after,
            next_after: wire.next_after,
            items: wire
                .files
                .into_iter()
                .map(|f| f.into_dto(folder_id))
                .collect(),
        })
    }

    pub async fn get_file(&self, folder_id: i64, file_id: i64) -> AppResult<FileDetailDto> {
        let mut after = 0;
        loop {
            let page = self.folder_files(folder_id, 100, after).await?;
            if let Some(file) = page.items.into_iter().find(|f| f.id == file_id) {
                return Ok(file);
            }
            match page.next_after {
                Some(next) if next > after => after = next,
                _ => return Err(AppError::Forbidden(404)),
            }
        }
    }

    async fn file_by_path(
        &self,
        folder_id: i64,
        path: &str,
        version_id: Option<i64>,
    ) -> AppResult<FileDetailDto> {
        let mut after = 0;
        let mut candidates = Vec::new();
        loop {
            let page = self.folder_files(folder_id, 100, after).await?;
            candidates.extend(page.items.iter().map(|f| f.id));
            if let Some(file) = page.items.into_iter().find(|f| {
                f.logical_path == path
                    || (version_id.is_some() && f.current_version_id == version_id)
            }) {
                return Ok(file);
            }
            match page.next_after {
                Some(next) if next > after => after = next,
                _ => break,
            }
        }
        if let Some(version_id) = version_id {
            for file_id in candidates {
                match self.get_file_version(folder_id, file_id, version_id).await {
                    Ok(_) => return self.get_file(folder_id, file_id).await,
                    Err(AppError::Forbidden(404)) => {}
                    Err(err) => return Err(err),
                }
            }
        }
        Err(AppError::Forbidden(404))
    }

    pub async fn get_file_versions(
        &self,
        folder_id: i64,
        file_id: i64,
        limit: i64,
        offset: i64,
    ) -> AppResult<FileVersionListDto> {
        let file = self.get_file(folder_id, file_id).await?;
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/files/{file_id}/versions"))?)
                .headers(self.headers()?),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Versions>()
            .await?;
        let total = wire.versions.len() as i64;
        Ok(FileVersionListDto {
            file_id,
            total,
            limit,
            offset,
            items: wire
                .versions
                .into_iter()
                .skip(offset.max(0) as usize)
                .take(limit.clamp(1, 100) as usize)
                .map(|v| v.into_dto(file_id, file.current_version_id))
                .collect(),
        })
    }

    pub async fn get_file_version(
        &self,
        folder_id: i64,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<FileVersionDto> {
        let current = self.get_file(folder_id, file_id).await?.current_version_id;
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/files/{file_id}/versions"))?)
                .headers(self.headers()?),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Versions>()
            .await?;
        wire.versions
            .into_iter()
            .find(|v| v.id == version_id)
            .map(|v| v.into_dto(file_id, current))
            .ok_or(AppError::Forbidden(404))
    }

    pub async fn restore_file_version(
        &self,
        folder_id: i64,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<FileVersionDto> {
        let response = send(
            self.http
                .post(self.url(&format!(
                    "folders/{folder_id}/files/{file_id}/versions/{version_id}/restore"
                ))?)
                .headers(self.headers()?)
                .header("Idempotency-Key", uuid::Uuid::new_v4().to_string()),
        )
        .await?;
        let version = Self::map_response(response)
            .await?
            .json::<crate::wire::OneVersion>()
            .await?
            .version;
        let id = version.id;
        Ok(version.into_dto(file_id, Some(id)))
    }

    pub async fn folder_changes(
        &self,
        folder_id: i64,
        after: i64,
        limit: i64,
    ) -> AppResult<FolderChangesDto> {
        let response = send(
            self.http
                .get(self.url(&format!("folders/{folder_id}/changes"))?)
                .headers(self.headers()?)
                .query(&[("limit", limit), ("after", after)]),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Changes>()
            .await?;
        let changes: Vec<_> = wire
            .changes
            .into_iter()
            .map(|c| FolderChangeDto {
                id: c.id,
                change_type: "CANONICAL_VERSION".into(),
                folder_id,
                file_id: c.file.id,
                logical_path: c.file.path,
                current_version_id: Some(c.version.id),
                version_number: Some(c.version.number),
                content_hash: Some(c.version.sha256),
                size: c.version.size,
                source: Some(c.version.source),
                changed_at: Some(c.version.created_at),
                changed_by_device_id: c.version.device.map(|d| d.id),
            })
            .collect();
        let next_cursor = wire
            .next_after
            .or_else(|| changes.last().map(|c| c.id))
            .unwrap_or(after);
        Ok(FolderChangesDto {
            folder_id,
            changes,
            next_cursor,
            has_more: wire.next_after.is_some(),
            limit,
        })
    }

    pub async fn authorize_download(
        &self,
        folder_id: i64,
        file_id: i64,
        version_id: i64,
    ) -> AppResult<DownloadAuthDto> {
        let version = self
            .get_file_version(folder_id, file_id, version_id)
            .await?;
        let response = send(
            self.http
                .post(self.url(&format!(
                    "folders/{folder_id}/files/{file_id}/versions/{version_id}/download"
                ))?)
                .headers(self.headers()?),
        )
        .await?;
        let wire = Self::map_response(response)
            .await?
            .json::<crate::wire::Download>()
            .await?;
        Ok(DownloadAuthDto {
            file_id,
            version_id,
            version_number: version.version_number,
            size: version.size,
            content_hash: version.content_hash,
            checksum_algorithm: "sha256".into(),
            expires_in: crate::wire::ttl(&wire.expires_at),
            url: wire.url,
        })
    }
}

/// Dịch lỗi HTTP của server thành thông báo tiếng Việt dễ hiểu cho người dùng — bao gồm các lý
/// do từ chối theo tình trạng mẫu (đã lưu trữ, đã kết thúc) mà server enforce, ở đây chỉ diễn
/// giải lại, không tự quyết định.
pub fn map_http_error(status: u16, body: &str) -> AppError {
    #[derive(Deserialize)]
    struct ErrorBody {
        error: Refusal,
    }
    #[derive(Deserialize)]
    struct Refusal {
        code: String,
        message: String,
    }
    let Ok(error) = serde_json::from_str::<ErrorBody>(body) else {
        return AppError::Api {
            status,
            code: "invalid_response".into(),
            message: format!("Máy chủ trả HTTP {status}"),
            retry_after: None,
        };
    };
    match (status, error.error.code.as_str()) {
        (410, "client_update_required") => {
            AppError::ClientUpdateRequired(crate::error::redact_url_queries(&error.error.message))
        }
        (401, "invalid_key") | (403, "device_revoked") => AppError::Unauthenticated,
        (403, "permission_denied") | (404, "not_found") => AppError::Forbidden(status),
        _ => AppError::Api {
            status,
            code: error.error.code,
            message: crate::error::redact_url_queries(&error.error.message),
            retry_after: None,
        },
    }
}

/// True nếu lỗi có khả năng là tạm thời (mạng, 502/503/504, timeout, ...) và đáng thử lại.
pub fn is_retryable(err: &AppError) -> bool {
    match err {
        AppError::Api { code, status, .. } => {
            matches!(
                code.as_str(),
                "too_many_attempts"
                    | "try_again"
                    | "storage_unavailable"
                    | "folder_disabled"
                    | "locked"
                    | "upload_incomplete"
                    | "upload_closed"
            ) || *status >= 500
        }
        AppError::UploadPending | AppError::UploadExpired => true,
        AppError::StorageStatus(status) => *status >= 500 || *status == 429,
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
            Some("member") => unbound.shared.push(remote),
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
        FolderMembersDto,
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
            409,
            r#"{"error":{"code":"folder_disabled","message":"tạm tắt"}}"#
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
            shared_fixture(2, "SharedBound", Some("member")),
            shared_fixture(3, "SharedFree", Some("member")),
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
                shared_fixture(1, "A", Some("member")),
                shared_fixture(2, "B", Some("member")),
                shared_fixture(3, "C", Some("member")),
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
                shared_fixture(11, "LabResults", Some("member")),
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
                "owner_name":"Dr. A","my_role":"member","can_manage_members":false,"future_field":1}"#,
        )
        .unwrap();
        assert_eq!(current.owner_name.as_deref(), Some("Dr. A"));
        assert_eq!(current.my_role.as_deref(), Some("member"));

        let members: FolderMembersDto = serde_json::from_str(
            r#"{"folder_id":1,"owner":{"id":2,"name":"Dr. A"},"my_role":"member",
                "members":[{"id":9,"user":{"id":3,"name":"B","login":"b"},"role":"upload","effective_access":false}]}"#,
        )
        .unwrap();
        assert!(!members.can_manage_members);
        assert!(!members.members[0].effective_access);
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

    #[test]
    fn api_error_codes_control_auth_permissions_and_retry_independent_of_language() {
        for message in ["unrelated 503 ONLYOFFICE", "Từ chối", "任意"] {
            let body = |code: &str| {
                serde_json::json!({"error":{"code":code,"message":message}}).to_string()
            };
            assert!(matches!(
                map_http_error(401, &body("invalid_key")),
                AppError::Unauthenticated
            ));
            assert!(matches!(
                map_http_error(403, &body("device_revoked")),
                AppError::Unauthenticated
            ));
            assert!(matches!(
                map_http_error(403, &body("permission_denied")),
                AppError::Forbidden(403)
            ));
            assert!(matches!(
                map_http_error(404, &body("not_found")),
                AppError::Forbidden(404)
            ));
            assert!(!is_retryable(&map_http_error(
                401,
                &body("invalid_credentials")
            )));
            assert!(is_retryable(&map_http_error(
                429,
                &body("too_many_attempts")
            )));
            assert!(is_retryable(&map_http_error(503, &body("try_again"))));
            assert!(is_retryable(&map_http_error(409, &body("folder_disabled"))));
            assert!(!is_retryable(&map_http_error(
                409,
                &body("folder_archived")
            )));
        }
        assert!(!matches!(
            map_http_error(401, "not JSON"),
            AppError::Unauthenticated
        ));
    }
}
