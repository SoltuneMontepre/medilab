//! Server giả lập API upload của Odoo (`prepare`/`presign`/`finalize`) và PUT part lên storage,
//! cùng API download (`GET file`, `authorize download`, GET object), chỉ dùng trong test. Server tự ghép object từ các part đã nhận và tính SHA-256 thật của nó,
//! để test chứng minh được object nào đã được finalize.

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};

/// Một version đã được finalize trên server giả: hash client khai lúc prepare và hash thật của
/// object ghép từ các part.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FinalizedVersion {
    pub declared_hash: String,
    pub actual_hash: String,
    pub size: usize,
}

/// Một session multipart đang mở trên server giả.
#[derive(Debug, Default)]
struct Session {
    declared_hash: String,
    parts: HashMap<i64, Vec<u8>>,
}

/// State dùng chung của server giả.
#[derive(Debug, Default)]
struct State {
    part_size: i64,
    next_session_id: i64,
    sessions: HashMap<i64, Session>,
    versions: Vec<FinalizedVersion>,
    dedup_hashes: HashSet<String>,
    reject_next_puts: usize,
    /// PUT của các part này bị giữ lại (không trả response) tới khi được thả; dùng một lần.
    held_parts: HashMap<i64, PartHold>,
    /// Request `prepare`/`finalize` bị giữ lại tới khi được thả; dùng một lần.
    held_requests: HashMap<&'static str, PartHold>,
    put_count: usize,
    presign_count: usize,
    /// PUT của các part này bị trả 403 một lần (giả lập URL presigned của đúng part đó hết hạn).
    rejected_parts: HashSet<i64>,
    /// Số PUT đang được server xử lý (đã tới, chưa trả response) và mức cao nhất quan sát được.
    puts_in_flight: usize,
    max_puts_in_flight: usize,
    /// Part number của các PUT theo thứ tự tới server / theo thứ tự trả response thành công.
    put_arrivals: Vec<i64>,
    put_completions: Vec<i64>,
    /// Danh sách part number của từng lần gọi presign.
    presign_requests: Vec<Vec<i64>>,
    /// PUT của part này chờ thêm số mili-giây này trước khi trả response (một lần).
    delayed_parts: HashMap<i64, u64>,
    /// `(part_number, etag)` theo đúng thứ tự trong payload của từng lần finalize.
    finalize_requests: Vec<Vec<(i64, String)>>,
    /// Version chuẩn hiện hành của từng tệp remote để tải xuống: `(version_id, nội dung)`.
    published: HashMap<i64, (i64, String)>,
}

/// Điều khiển một PUT bị giữ: `started` báo khi request của part đã tới server (body đã nhận),
/// `release` thả nó để server trả response.
#[derive(Debug, Clone, Default)]
pub struct PartHold {
    pub started: Arc<tokio::sync::Notify>,
    pub release: Arc<tokio::sync::Notify>,
}

/// Tay cầm tới server giả đang chạy trên cổng ngẫu nhiên của loopback.
#[derive(Clone)]
pub struct MockSyncServer {
    pub base: String,
    state: Arc<Mutex<State>>,
}

impl MockSyncServer {
    /// Khởi động server với kích thước part cho trước.
    pub async fn start(part_size: i64) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let state = Arc::new(Mutex::new(State {
            part_size,
            next_session_id: 1,
            ..State::default()
        }));
        let server = Self { base, state };
        let accept = server.clone();
        tokio::spawn(async move {
            while let Ok((stream, _)) = listener.accept().await {
                let connection = accept.clone();
                tokio::spawn(async move { connection.serve(stream).await });
            }
        });
        server
    }

    /// Các version đã finalize theo thứ tự.
    pub fn versions(&self) -> Vec<FinalizedVersion> {
        self.state.lock().unwrap().versions.clone()
    }

    /// Số lần PUT part server đã nhận (kể cả lần bị từ chối).
    pub fn put_count(&self) -> usize {
        self.state.lock().unwrap().put_count
    }

    /// Số lần gọi presign.
    pub fn presign_count(&self) -> usize {
        self.state.lock().unwrap().presign_count
    }

    /// Cho `prepare` trả `deduplicated` với hash này (giả lập server đã có nội dung đó).
    pub fn add_dedup_hash(&self, hash: &str) {
        self.state
            .lock()
            .unwrap()
            .dedup_hashes
            .insert(hash.to_string());
    }

    /// Số PUT server đang xử lý (đã tới, chưa trả response).
    pub fn puts_in_flight(&self) -> usize {
        self.state.lock().unwrap().puts_in_flight
    }

    /// Mức PUT đồng thời cao nhất server đã thấy.
    pub fn max_puts_in_flight(&self) -> usize {
        self.state.lock().unwrap().max_puts_in_flight
    }

    /// Part number của các PUT theo thứ tự tới server (kể cả PUT bị giữ rồi bị client hủy).
    pub fn put_arrivals(&self) -> Vec<i64> {
        self.state.lock().unwrap().put_arrivals.clone()
    }

    /// Part number của các PUT đã trả response thành công, theo thứ tự hoàn tất.
    pub fn put_completions(&self) -> Vec<i64> {
        self.state.lock().unwrap().put_completions.clone()
    }

    /// Danh sách part number của từng lần gọi presign.
    pub fn presign_requests(&self) -> Vec<Vec<i64>> {
        self.state.lock().unwrap().presign_requests.clone()
    }

    /// PUT kế tiếp của `part_number` trả response chậm thêm `millis` mili-giây (một lần).
    pub fn delay_part(&self, part_number: i64, millis: u64) {
        self.state
            .lock()
            .unwrap()
            .delayed_parts
            .insert(part_number, millis);
    }

    /// `(part_number, etag)` theo thứ tự payload của từng lần finalize.
    pub fn finalize_requests(&self) -> Vec<Vec<(i64, String)>> {
        self.state.lock().unwrap().finalize_requests.clone()
    }

    /// Trả 403 cho PUT kế tiếp của `part_number` (một lần).
    pub fn reject_part(&self, part_number: i64) {
        self.state
            .lock()
            .unwrap()
            .rejected_parts
            .insert(part_number);
    }

    /// Giữ PUT kế tiếp của `part_number` (ở bất kỳ session nào) cho tới khi `release`; trả tay cầm.
    pub fn hold_part(&self, part_number: i64) -> PartHold {
        let hold = PartHold::default();
        self.state
            .lock()
            .unwrap()
            .held_parts
            .insert(part_number, hold.clone());
        hold
    }

    /// Từ chối `count` lần PUT kế tiếp bằng 403 (giả lập URL presigned hết hạn).
    pub fn reject_next_puts(&self, count: usize) {
        self.state.lock().unwrap().reject_next_puts = count;
    }

    /// Phục vụ các request trên một kết nối keep-alive cho tới khi client đóng.
    async fn serve(&self, stream: TcpStream) {
        let mut reader = BufReader::new(stream);
        loop {
            let mut request_line = String::new();
            if reader.read_line(&mut request_line).await.unwrap_or(0) == 0 {
                return;
            }
            let mut content_length = 0usize;
            loop {
                let mut header = String::new();
                if reader.read_line(&mut header).await.unwrap_or(0) == 0 {
                    return;
                }
                let header = header.trim_end();
                if header.is_empty() {
                    break;
                }
                if let Some((name, value)) = header.split_once(':') {
                    if name.eq_ignore_ascii_case("content-length") {
                        content_length = value.trim().parse().unwrap_or(0);
                    }
                }
            }
            let mut body = vec![0u8; content_length];
            if reader.read_exact(&mut body).await.is_err() {
                return;
            }
            let mut parts = request_line.split_whitespace();
            let method = parts.next().unwrap_or_default().to_string();
            let path = parts.next().unwrap_or_default().to_string();
            let put_part = put_part_number(&method, &path);
            if let Some(part) = put_part {
                let mut state = self.state.lock().unwrap();
                state.puts_in_flight += 1;
                state.max_puts_in_flight = state.max_puts_in_flight.max(state.puts_in_flight);
                state.put_arrivals.push(part);
            }
            if let Some(hold) = self.take_hold(&method, &path) {
                hold.started.notify_one();
                hold.release.notified().await;
            }
            let delay =
                put_part.and_then(|part| self.state.lock().unwrap().delayed_parts.remove(&part));
            if let Some(millis) = delay {
                tokio::time::sleep(std::time::Duration::from_millis(millis)).await;
            }
            let (status, extra_headers, response_body) = self.route(&method, &path, &body);
            if let Some(part) = put_part {
                let mut state = self.state.lock().unwrap();
                state.puts_in_flight -= 1;
                if status.starts_with("200") {
                    state.put_completions.push(part);
                }
            }
            let head = format!(
                "HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\n{extra_headers}\r\n",
                response_body.len()
            );
            let stream = reader.get_mut();
            if stream.write_all(head.as_bytes()).await.is_err()
                || stream.write_all(response_body.as_bytes()).await.is_err()
            {
                return;
            }
        }
    }

    /// Đặt `content` làm version chuẩn `version_id` của tệp remote `remote_file_id` để client tải
    /// xuống; trả SHA-256 hex của nội dung.
    pub fn publish_file(&self, remote_file_id: i64, version_id: i64, content: &str) -> String {
        self.state
            .lock()
            .unwrap()
            .published
            .insert(remote_file_id, (version_id, content.to_string()));
        hex::encode(Sha256::digest(content.as_bytes()))
    }

    /// Giữ lại request `kind` (`"prepare"` hoặc `"finalize"`) kế tiếp: server đã nhận nhưng chưa
    /// xử lý cho tới khi `release`; dùng để chen thao tác vào giữa lúc request đang bay.
    pub fn hold_request(&self, kind: &'static str) -> PartHold {
        let hold = PartHold::default();
        self.state
            .lock()
            .unwrap()
            .held_requests
            .insert(kind, hold.clone());
        hold
    }

    /// Lấy (và gỡ) hold nếu request là PUT part hoặc `prepare`/`finalize` đang bị giữ.
    fn take_hold(&self, method: &str, path: &str) -> Option<PartHold> {
        if let Some(part) = put_part_number(method, path) {
            return self.state.lock().unwrap().held_parts.remove(&part);
        }
        let kind = match (method, path) {
            ("POST", path) if path.ends_with("/uploads/prepare") => "prepare",
            ("POST", path) if path.ends_with("/finalize") => "finalize",
            _ => return None,
        };
        self.state.lock().unwrap().held_requests.remove(kind)
    }

    /// Xử lý một request và trả `(status line, header thêm, body)`.
    fn route(&self, method: &str, path: &str, body: &[u8]) -> (String, String, String) {
        let mut state = self.state.lock().unwrap();
        let segments: Vec<&str> = path.trim_start_matches('/').split('/').collect();
        match (method, segments.as_slice()) {
            ("POST", ["api", "sync", "v1", "uploads", "prepare"]) => {
                let payload: serde_json::Value = serde_json::from_slice(body).unwrap();
                let hash = payload["content_hash"].as_str().unwrap().to_string();
                let part_size = state.part_size;
                if state.dedup_hashes.contains(&hash) {
                    return ok(serde_json::json!({
                        "session_id": null, "file_id": 1, "deduplicated": true,
                        "version_id": 1, "version_number": 1, "part_size": part_size,
                        "storage_key": "k", "s3_upload_id": null, "expires_at": null,
                    }));
                }
                let session_id = state.next_session_id;
                state.next_session_id += 1;
                state.sessions.insert(
                    session_id,
                    Session {
                        declared_hash: hash,
                        parts: HashMap::new(),
                    },
                );
                ok(serde_json::json!({
                    "session_id": session_id, "file_id": 1, "deduplicated": false,
                    "version_id": null, "version_number": null, "part_size": part_size,
                    "storage_key": "k", "s3_upload_id": "u", "expires_at": null,
                }))
            }
            ("POST", ["api", "sync", "v1", "uploads", session, "parts", "presign"]) => {
                state.presign_count += 1;
                let payload: serde_json::Value = serde_json::from_slice(body).unwrap();
                let requested: Vec<i64> = payload["part_numbers"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|number| number.as_i64().unwrap())
                    .collect();
                state.presign_requests.push(requested);
                let parts: Vec<serde_json::Value> = payload["part_numbers"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|number| {
                        serde_json::json!({
                            "part_number": number,
                            "url": format!("{}/s3/{session}/{number}?X-Amz-Signature=test", self.base),
                            "expires_in": 900,
                        })
                    })
                    .collect();
                ok(serde_json::json!({ "parts": parts }))
            }
            ("PUT", ["s3", session, part]) => {
                state.put_count += 1;
                let part_number: i64 = part.split('?').next().unwrap().parse().unwrap();
                if state.rejected_parts.remove(&part_number) {
                    return ("403 Forbidden".into(), String::new(), "{}".into());
                }
                if state.reject_next_puts > 0 {
                    state.reject_next_puts -= 1;
                    return ("403 Forbidden".into(), String::new(), "{}".into());
                }
                let session: i64 = session.parse().unwrap();
                let part: i64 = part.split('?').next().unwrap().parse().unwrap();
                state
                    .sessions
                    .get_mut(&session)
                    .unwrap()
                    .parts
                    .insert(part, body.to_vec());
                (
                    "200 OK".into(),
                    format!("etag: \"etag-{session}-{part}\"\r\n"),
                    String::new(),
                )
            }
            ("POST", ["api", "sync", "v1", "uploads", session, "finalize"]) => {
                let session_id: i64 = session.parse().unwrap();
                let payload: serde_json::Value = serde_json::from_slice(body).unwrap();
                let sent: Vec<(i64, String)> = payload["parts"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|part| {
                        (
                            part["part_number"].as_i64().unwrap(),
                            part["etag"].as_str().unwrap().to_string(),
                        )
                    })
                    .collect();
                state.finalize_requests.push(sent);
                let session = state.sessions.remove(&session_id).unwrap();
                let mut object = Vec::new();
                for part in payload["parts"].as_array().unwrap() {
                    let number = part["part_number"].as_i64().unwrap();
                    object.extend_from_slice(&session.parts[&number]);
                }
                state.versions.push(FinalizedVersion {
                    declared_hash: session.declared_hash,
                    actual_hash: hex::encode(Sha256::digest(&object)),
                    size: object.len(),
                });
                let version_id = state.versions.len();
                ok(serde_json::json!({
                    "status": "committed", "file_id": 1, "version_id": version_id,
                    "version_number": version_id, "conflict_id": null, "server_version_id": null,
                }))
            }
            ("GET", ["api", "sync", "v1", "files", file]) => {
                let file_id: i64 = file.parse().unwrap();
                let Some((version_id, content)) = state.published.get(&file_id) else {
                    return ("404 Not Found".into(), String::new(), "{}".into());
                };
                ok(serde_json::json!({
                    "id": file_id, "folder_id": 7, "name": "f", "logical_path": "f",
                    "current_version_id": version_id, "version_count": 1, "updated_at": null,
                    "current_version": {
                        "id": version_id, "file_id": file_id, "version_number": 1,
                        "size": content.len(),
                        "content_hash": hex::encode(Sha256::digest(content.as_bytes())),
                        "checksum_algorithm": "sha256", "source": "upload", "created_at": null,
                        "created_by": null, "device": null, "is_canonical": true,
                        "parent_version_id": null, "restored_from_version_id": null,
                        "object_available": true,
                    },
                }))
            }
            ("POST", ["api", "sync", "v1", "files", file, "versions", version, "download"]) => {
                let file_id: i64 = file.parse().unwrap();
                let (_, content) = state.published[&file_id].clone();
                ok(serde_json::json!({
                    "file_id": file_id, "version_id": version.parse::<i64>().unwrap(),
                    "version_number": 1, "size": content.len(),
                    "content_hash": hex::encode(Sha256::digest(content.as_bytes())),
                    "checksum_algorithm": "sha256",
                    "url": format!("{}/objects/{file_id}?X-Amz-Signature=test", self.base),
                    "expires_in": 900,
                }))
            }
            ("GET", ["objects", file]) => {
                let file_id: i64 = file.split('?').next().unwrap().parse().unwrap();
                let (_, content) = state.published[&file_id].clone();
                ("200 OK".into(), String::new(), content)
            }
            _ => ("404 Not Found".into(), String::new(), "{}".into()),
        }
    }
}

/// Part number của một request PUT part (`/s3/{session}/{part}?…`), `None` với request khác.
fn put_part_number(method: &str, path: &str) -> Option<i64> {
    if method != "PUT" {
        return None;
    }
    path.trim_start_matches('/')
        .split('/')
        .nth(2)?
        .split('?')
        .next()?
        .parse()
        .ok()
}

/// Response 200 với body JSON.
fn ok(body: serde_json::Value) -> (String, String, String) {
    ("200 OK".into(), String::new(), body.to_string())
}
