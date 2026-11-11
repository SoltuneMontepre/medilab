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
    path: String,
    size: i64,
    base: Option<i64>,
    status: String,
    version: Option<i64>,
    parts: HashMap<i64, Vec<u8>>,
}

/// State dùng chung của server giả.
#[derive(Debug, Default)]
struct State {
    part_size: i64,
    lose_prepare: bool,
    lose_finalize: bool,
    prepare_keys: HashMap<String, i64>,
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

    pub fn lose_prepare_reply(&self) {
        self.state.lock().unwrap().lose_prepare = true;
    }
    pub fn lose_finalize_reply(&self) {
        self.state.lock().unwrap().lose_finalize = true;
    }
    pub fn upload_count(&self) -> usize {
        self.state.lock().unwrap().sessions.len()
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
        while let Some((request_line, body, headers)) = read_request(&mut reader).await {
            let mut parts = request_line.split_whitespace();
            let method = parts.next().unwrap_or_default().to_string();
            let path = parts.next().unwrap_or_default().to_string();
            let (status, extra_headers, response_body) =
                self.respond(&method, &path, &body, &headers).await;
            let lose = {
                let mut state = self.state.lock().unwrap();
                if method == "POST" && path.ends_with("/uploads") {
                    std::mem::take(&mut state.lose_prepare)
                } else if method == "POST" && path.ends_with("/finalize") {
                    std::mem::take(&mut state.lose_finalize)
                } else {
                    false
                }
            };
            if lose {
                return;
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

    /// Trả lời một request: ghi nhận PUT part đang bay, chờ hold hoặc độ trễ nếu test đặt, rồi
    /// định tuyến.
    async fn respond(
        &self,
        method: &str,
        path: &str,
        body: &[u8],
        headers: &HashMap<String, String>,
    ) -> (String, String, String) {
        if path.starts_with("/s3/") || path.starts_with("/objects/") {
            assert_eq!(
                headers.get("user-agent").map(String::as_str),
                Some(concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")))
            );
            assert!(!headers.contains_key("authorization"));
            assert!(!headers.contains_key("x-sync-device-id"));
        }
        let put_part = put_part_number(method, path);
        if let Some(part) = put_part {
            let mut state = self.state.lock().unwrap();
            state.puts_in_flight += 1;
            state.max_puts_in_flight = state.max_puts_in_flight.max(state.puts_in_flight);
            state.put_arrivals.push(part);
        }
        if let Some(hold) = self.take_hold(method, path) {
            hold.started.notify_one();
            hold.release.notified().await;
        }
        let delay =
            put_part.and_then(|part| self.state.lock().unwrap().delayed_parts.remove(&part));
        if let Some(millis) = delay {
            tokio::time::sleep(std::time::Duration::from_millis(millis)).await;
        }
        let (status, extra_headers, response_body) = self.route(method, path, body, headers);
        if let Some(part) = put_part {
            let mut state = self.state.lock().unwrap();
            state.puts_in_flight -= 1;
            if status.starts_with("200") {
                state.put_completions.push(part);
            }
        }
        (status, extra_headers, response_body)
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
            ("POST", path) if path.ends_with("/uploads") => "prepare",
            ("POST", path) if path.ends_with("/finalize") => "finalize",
            _ => return None,
        };
        self.state.lock().unwrap().held_requests.remove(kind)
    }

    /// Xử lý một request và trả `(status line, header thêm, body)`.
    fn route(
        &self,
        method: &str,
        path: &str,
        body: &[u8],
        headers: &HashMap<String, String>,
    ) -> (String, String, String) {
        let mut state = self.state.lock().unwrap();
        let bare = path.split('?').next().unwrap();
        let segments: Vec<_> = bare.trim_matches('/').split('/').collect();
        match (method, segments.as_slice()) {
            ("POST", ["medilab", "api", "v1", "folders", _, "uploads"]) => {
                let payload: serde_json::Value = serde_json::from_slice(body).unwrap();
                let key = &headers["idempotency-key"];
                if let Some(id) = state.prepare_keys.get(key) {
                    return ok(upload_value(*id, &state.sessions[id], state.part_size));
                }
                let id = state.next_session_id;
                state.next_session_id += 1;
                let hash = payload["sha256"].as_str().unwrap().to_string();
                let unchanged = state.dedup_hashes.contains(&hash);
                let session = Session {
                    declared_hash: hash,
                    path: payload["path"].as_str().unwrap().into(),
                    size: payload["size"].as_i64().unwrap(),
                    base: payload["base_version_id"].as_i64(),
                    status: if unchanged { "unchanged" } else { "prepared" }.into(),
                    version: unchanged.then_some(1),
                    parts: HashMap::new(),
                };
                let result = upload_value(id, &session, state.part_size);
                state.sessions.insert(id, session);
                state.prepare_keys.insert(key.clone(), id);
                ok(result)
            }
            ("GET", ["medilab", "api", "v1", "folders", _, "uploads", id]) => {
                let id = id.parse().unwrap();
                ok(upload_value(id, &state.sessions[&id], state.part_size))
            }
            ("POST", ["medilab", "api", "v1", "folders", _, "uploads", id, "parts"]) => {
                state.presign_count += 1;
                let payload: serde_json::Value = serde_json::from_slice(body).unwrap();
                let numbers: Vec<i64> =
                    serde_json::from_value(payload["part_numbers"].clone()).unwrap();
                state.presign_requests.push(numbers.clone());
                ok(
                    serde_json::json!({"parts":numbers.into_iter().map(|n|serde_json::json!({"number":n,"url":format!("{}/s3/{id}/{n}?X-Amz-Signature=test",self.base)})).collect::<Vec<_>>(),"expires_at":expires()}),
                )
            }
            ("PUT", ["s3", id, part]) => {
                state.put_count += 1;
                let number: i64 = part.parse().unwrap();
                if state.rejected_parts.remove(&number) {
                    return ("403 Forbidden".into(), String::new(), "{}".into());
                }
                if state.reject_next_puts > 0 {
                    state.reject_next_puts -= 1;
                    return ("403 Forbidden".into(), String::new(), "{}".into());
                }
                state
                    .sessions
                    .get_mut(&id.parse().unwrap())
                    .unwrap()
                    .parts
                    .insert(number, body.to_vec());
                (
                    "200 OK".into(),
                    format!("etag: \"etag-{id}-{part}\"\r\n"),
                    String::new(),
                )
            }
            ("POST", ["medilab", "api", "v1", "folders", _, "uploads", id, "finalize"]) => {
                assert!(body.is_empty(), "finalize has no request body");
                let id: i64 = id.parse().unwrap();
                if state.sessions[&id].status == "prepared" {
                    let session = &state.sessions[&id];
                    let mut numbers: Vec<_> = session.parts.keys().copied().collect();
                    numbers.sort_unstable();
                    let object: Vec<u8> = numbers
                        .iter()
                        .flat_map(|n| session.parts[n].iter().copied())
                        .collect();
                    let version = FinalizedVersion {
                        declared_hash: session.declared_hash.clone(),
                        actual_hash: hex::encode(Sha256::digest(&object)),
                        size: object.len(),
                    };
                    state.versions.push(version);
                    let version_id = state.versions.len() as i64;
                    state.finalize_requests.push(
                        numbers
                            .into_iter()
                            .map(|n| (n, format!("etag-{id}-{n}")))
                            .collect(),
                    );
                    let session = state.sessions.get_mut(&id).unwrap();
                    session.status = "completed".into();
                    session.version = Some(version_id);
                }
                (
                    "202 Accepted".into(),
                    String::new(),
                    upload_value(id, &state.sessions[&id], state.part_size).to_string(),
                )
            }
            ("GET", ["medilab", "api", "v1", "folders", _, "files"]) => {
                let mut files:Vec<_>=state.published.iter().map(|(id,(vid,content))|serde_json::json!({"id":id,"path":"f","current_version":version_value(*vid,content.len() as i64,&hex::encode(Sha256::digest(content.as_bytes()))),"lock":null})).collect();
                for (id, s) in state.sessions.iter().filter(|(_, s)| s.version.is_some()) {
                    files.push(serde_json::json!({"id":id,"path":s.path,"current_version":version_value(s.version.unwrap(),s.size,&s.declared_hash),"lock":null}));
                }
                ok(serde_json::json!({"files":files,"next_after":null}))
            }
            ("GET", ["medilab", "api", "v1", "folders", _, "files", file, "versions"]) => {
                let (id, content) = &state.published[&file.parse::<i64>().unwrap()];
                ok(
                    serde_json::json!({"versions":[version_value(*id,content.len() as i64,&hex::encode(Sha256::digest(content.as_bytes())))]}),
                )
            }
            (
                "POST",
                ["medilab", "api", "v1", "folders", _, "files", file, "versions", _, "download"],
            ) => ok(
                serde_json::json!({"url":format!("{}/objects/{file}?X-Amz-Signature=test",self.base),"expires_at":expires()}),
            ),
            ("GET", ["objects", file]) => {
                let (_, content) = state.published[&file.parse::<i64>().unwrap()].clone();
                ("200 OK".into(), String::new(), content)
            }
            _ => (
                "404 Not Found".into(),
                String::new(),
                serde_json::json!({"error":{"code":"not_found","message":"Not found"}}).to_string(),
            ),
        }
    }
}

/// Đọc request line, header và body của một request; `None` khi client đóng kết nối hoặc lỗi đọc.
async fn read_request(
    reader: &mut BufReader<TcpStream>,
) -> Option<(String, Vec<u8>, HashMap<String, String>)> {
    let mut request_line = String::new();
    if reader.read_line(&mut request_line).await.unwrap_or(0) == 0 {
        return None;
    }
    let mut content_length = 0usize;
    let mut headers = HashMap::new();
    loop {
        let mut header = String::new();
        if reader.read_line(&mut header).await.unwrap_or(0) == 0 {
            return None;
        }
        let header = header.trim_end();
        if header.is_empty() {
            break;
        }
        if let Some((name, value)) = header.split_once(':') {
            headers.insert(name.to_ascii_lowercase(), value.trim().into());
            if name.eq_ignore_ascii_case("content-length") {
                content_length = value.trim().parse().unwrap_or(0);
            }
        }
    }
    let mut body = vec![0u8; content_length];
    reader.read_exact(&mut body).await.ok()?;
    Some((request_line, body, headers))
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

fn expires() -> String {
    (chrono::Utc::now() + chrono::Duration::minutes(15)).to_rfc3339()
}
fn version_value(id: i64, size: i64, hash: &str) -> serde_json::Value {
    serde_json::json!({"id":id,"number":id,"source":"synced","size":size,"sha256":hash,
        "parent_version_id":null,"restored_from_id":null,"saved_by":{"id":2,"name":"Tester"},"device":{"id":1,"name":"PC"},"created_at":"2026-10-25T00:00:00Z"})
}
fn upload_value(id: i64, s: &Session, part_size: i64) -> serde_json::Value {
    serde_json::json!({"upload":{"id":id,"path":s.path,"status":s.status,"failure_code":null,"size":s.size,"sha256":s.declared_hash,"base_version_id":s.base,"part_size":part_size,
        "part_count":if s.size==0 || s.status=="unchanged" {0} else {(s.size+part_size-1)/part_size},"expires_at":expires(),"version":s.version.map(|v|version_value(v,s.size,&s.declared_hash))}})
}
