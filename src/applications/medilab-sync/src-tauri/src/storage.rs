use crate::error::{AppError, AppResult};
use crate::sync::rules::SyncRule;
use parking_lot::Mutex;
use rusqlite::{params, Connection, OptionalExtension};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

/// State bền cục bộ (SQLite): folder, tệp, job đồng bộ, và metadata phiên. Không bao giờ là
/// bằng chứng về quyền phía server.
#[derive(Clone)]
pub struct Db {
    conn: Arc<Mutex<Connection>>,
}

/// Giá trị `access_state` mặc định cho folder cũ chưa từng được set (migration).
fn default_access_ok() -> String {
    "ok".into()
}

/// Một folder đã đăng ký đồng bộ cục bộ, kèm ngữ cảnh mẫu LIMS lưu lại từ lần đồng bộ gần nhất.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FolderRow {
    pub id: i64,
    pub local_path: String,
    pub remote_id: Option<i64>,
    pub logical_root: String,
    pub enabled: bool,
    pub recursive: bool,
    #[serde(default)]
    pub sample_name: Option<String>,
    #[serde(default)]
    pub sample_code: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub workflow_status: Option<String>,
    #[serde(default)]
    pub instrument_label: Option<String>,
    #[serde(default = "default_access_ok")]
    pub access_state: String,
}

/// Một job đồng bộ (tải lên hoặc tải xuống) đang chờ, chạy, lỗi, hay đã xong, cùng state phiên
/// tải lên dở (nếu có) để phục hồi sau khi khởi động lại.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct JobRow {
    pub id: i64,
    pub folder_id: i64,
    pub file_id: i64,
    pub relative_path: String,
    pub operation: String,
    pub status: String,
    pub attempt_count: i64,
    pub last_error: Option<String>,
    pub bytes_total: i64,
    pub bytes_done: i64,
    pub remote_file_id: Option<i64>,
    pub remote_version_id: Option<i64>,
    #[serde(default)]
    pub session_id: Option<i64>,
    #[serde(default)]
    pub uploaded_parts: Option<String>,
    #[serde(default)]
    pub content_hash: Option<String>,
    #[serde(default)]
    pub target_version_number: Option<i64>,
    /// Kích thước part của session multipart đang dở (theo `prepare`); `None` với job cũ hoặc
    /// download.
    #[serde(default)]
    pub part_size: Option<i64>,
}

/// Dấu vân tay nội dung của một tệp cục bộ đã lưu trong `sync_file`: kích thước, mtime (giây
/// Unix) và SHA-256 tính lúc enqueue hoặc lần hash lại gần nhất.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileFingerprint {
    pub size: i64,
    pub mtime: i64,
    pub sha256: Option<String>,
}

/// Danh tính một binding folder cục bộ tại thời điểm đọc: `id` một mình không đủ vì SQLite tái
/// dùng rowid khi gỡ rồi gắn thư mục khác; `local_path` + `remote_id` phân biệt hai binding.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FolderBinding {
    pub id: i64,
    pub local_path: String,
    pub remote_id: Option<i64>,
}

/// Danh tính của MỘT job đang chạy (upload hoặc download), chụp một lần ngay khi task bắt đầu xử
/// lý nó: job (id + loại), dòng tệp (id + đường dẫn, và tệp remote với download) và binding folder.
/// `job_id`/`file_id`/`folder_id` trơn không đủ vì gỡ thư mục cascade xóa job/tệp và SQLite tái
/// dùng rowid khi gắn lại; mọi lượt ghi bền của task sau một lần await phải chứng minh danh tính
/// này vẫn còn nguyên (`Db::with_running_job`). Snapshot bất biến: task không bao giờ đọc lại
/// folder/tệp theo id trơn.
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunningJob {
    pub job_id: i64,
    pub file_id: i64,
    pub operation: String,
    pub relative_path: String,
    /// Tệp remote mà job download nhắm tới. `None` với upload: lần upload đầu chưa có tệp remote
    /// và finalize mới gán nó, nên không phải là danh tính của lượt chạy.
    pub remote_file_id: Option<i64>,
    pub binding: FolderBinding,
}

impl RunningJob {
    /// Đường dẫn tệp trên đĩa, tính từ binding đã chụp (không đọc lại folder theo id).
    pub fn local_path(&self) -> PathBuf {
        Path::new(&self.binding.local_path).join(&self.relative_path)
    }
}

impl FolderRow {
    /// Danh tính binding của dòng folder này.
    pub fn binding(&self) -> FolderBinding {
        FolderBinding {
            id: self.id,
            local_path: self.local_path.clone(),
            remote_id: self.remote_id,
        }
    }
}

/// Ánh xạ cục bộ giữa một tệp đã biết trên server và đường dẫn tương đối của nó trong một folder.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RemoteFileRow {
    pub id: i64,
    pub folder_id: i64,
    pub relative_path: String,
    pub remote_file_id: Option<i64>,
    pub remote_version_id: Option<i64>,
    pub last_synced_hash: Option<String>,
    pub suppress_hash: Option<String>,
    pub status: String,
}

impl Db {
    /// Mở (hoặc tạo) tệp SQLite tại `path`, bật WAL/foreign keys, rồi chạy migration.
    pub fn open(path: &Path) -> AppResult<Self> {
        let conn = Connection::open(path)?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "busy_timeout", 5000)?;
        let db = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        db.migrate()?;
        Ok(db)
    }

    /// Tạo bảng nếu chưa có và thêm cột mới qua `ensure_column`; đây là cơ chế tiến hóa schema
    /// duy nhất của app, không thay thế tiện tay.
    fn migrate(&self) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_folder (
                id INTEGER PRIMARY KEY,
                local_path TEXT NOT NULL UNIQUE,
                remote_id INTEGER,
                logical_root TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                recursive INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sync_rule (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                recursive INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(folder_id) REFERENCES sync_folder(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sync_file (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                relative_path TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime INTEGER NOT NULL,
                sha256 TEXT,
                remote_file_id INTEGER,
                remote_version_id INTEGER,
                status TEXT NOT NULL DEFAULT 'local',
                UNIQUE(folder_id, relative_path),
                FOREIGN KEY(folder_id) REFERENCES sync_folder(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sync_job (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                relative_path TEXT NOT NULL,
                operation TEXT NOT NULL DEFAULT 'upload',
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_retry_at INTEGER,
                last_error TEXT,
                bytes_total INTEGER NOT NULL DEFAULT 0,
                bytes_done INTEGER NOT NULL DEFAULT 0,
                remote_file_id INTEGER,
                remote_version_id INTEGER,
                session_id INTEGER,
                uploaded_parts TEXT,
                content_hash TEXT,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(folder_id) REFERENCES sync_folder(id) ON DELETE CASCADE,
                FOREIGN KEY(file_id) REFERENCES sync_file(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_job
                ON sync_job(file_id, operation)
                WHERE status IN ('pending','running','retry_wait');
            "#,
        )?;
        Self::ensure_column(&conn, "sync_file", "last_synced_hash", "TEXT")?;
        Self::ensure_column(&conn, "sync_file", "suppress_hash", "TEXT")?;
        Self::ensure_column(&conn, "sync_job", "target_version_number", "INTEGER")?;
        Self::ensure_column(&conn, "sync_folder", "sample_name", "TEXT")?;
        Self::ensure_column(&conn, "sync_folder", "sample_code", "TEXT")?;
        Self::ensure_column(&conn, "sync_folder", "category", "TEXT")?;
        Self::ensure_column(&conn, "sync_folder", "workflow_status", "TEXT")?;
        Self::ensure_column(&conn, "sync_folder", "instrument_label", "TEXT")?;
        Self::ensure_column(&conn, "sync_folder", "access_state", "TEXT")?;
        Self::ensure_column(
            &conn,
            "sync_job",
            "rerun_requested",
            "INTEGER NOT NULL DEFAULT 0",
        )?;
        Self::ensure_column(&conn, "sync_job", "part_size", "INTEGER")?;
        conn.execute(
            "UPDATE sync_folder SET access_state = 'ok' WHERE access_state IS NULL",
            [],
        )?;
        conn.execute(
            "UPDATE sync_file SET last_synced_hash = sha256
             WHERE status = 'synced' AND last_synced_hash IS NULL AND sha256 IS NOT NULL",
            [],
        )?;
        Ok(())
    }

    /// Thêm một cột vào `table` nếu nó chưa tồn tại (idempotent, an toàn gọi lại nhiều lần).
    fn ensure_column(conn: &Connection, table: &str, column: &str, decl: &str) -> AppResult<()> {
        let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let names: Vec<String> = stmt
            .query_map([], |row| row.get::<_, String>(1))?
            .collect::<Result<Vec<_>, _>>()?;
        if !names.iter().any(|name| name == column) {
            conn.execute(
                &format!("ALTER TABLE {table} ADD COLUMN {column} {decl}"),
                [],
            )?;
        }
        Ok(())
    }

    /// Đọc một giá trị metadata tùy ý theo key (tự do, dạng chuỗi).
    pub fn meta_get(&self, key: &str) -> AppResult<Option<String>> {
        let conn = self.conn.lock();
        let value = conn
            .query_row(
                "SELECT value FROM app_meta WHERE key = ?1",
                params![key],
                |row| row.get(0),
            )
            .optional()?;
        Ok(value)
    }

    /// Ghi (upsert) một giá trị metadata theo key.
    pub fn meta_set(&self, key: &str, value: &str) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute(
            "INSERT INTO app_meta(key, value) VALUES(?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    /// Chạy lúc khởi động: đưa job đang dở dang lúc thoát (`running`) về `pending`, và dọn job
    /// lỗi đã bị lượt sau thay thế.
    pub fn recover_jobs(&self) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute(
            "UPDATE sync_job SET status = 'pending', rerun_requested = 0 WHERE status = 'running'",
            [],
        )?;
        delete_resolved_failed_jobs(&conn)?;
        Ok(())
    }

    /// Tạo hoặc cập nhật binding folder cục bộ (đường dẫn ↔ logical root ↔ id trên server) cùng
    /// rule đặt tên/lọc của nó.
    pub fn upsert_folder(
        &self,
        local_path: &str,
        logical_root: &str,
        remote_id: Option<i64>,
        recursive: bool,
        rules: &[SyncRule],
    ) -> AppResult<i64> {
        let conn = self.conn.lock();
        conn.execute(
            "INSERT INTO sync_folder(local_path, remote_id, logical_root, enabled, recursive)
             VALUES(?1, ?2, ?3, 1, ?4)
             ON CONFLICT(local_path) DO UPDATE SET
                remote_id = excluded.remote_id,
                logical_root = excluded.logical_root,
                recursive = excluded.recursive,
                enabled = 1",
            params![local_path, remote_id, logical_root, recursive as i64],
        )?;
        let id: i64 = conn.query_row(
            "SELECT id FROM sync_folder WHERE local_path = ?1",
            params![local_path],
            |row| row.get(0),
        )?;
        conn.execute("DELETE FROM sync_rule WHERE folder_id = ?1", params![id])?;
        for rule in rules {
            conn.execute(
                "INSERT INTO sync_rule(folder_id, type, pattern, recursive, enabled)
                 VALUES(?1, ?2, ?3, ?4, ?5)",
                params![
                    id,
                    rule.kind,
                    rule.pattern,
                    rule.recursive as i64,
                    rule.enabled as i64
                ],
            )?;
        }
        Ok(id)
    }

    /// Lưu lại ngữ cảnh mẫu LIMS (tên/mã mẫu, category, tình trạng, nguồn thiết bị) mà server trả
    /// về cho folder này, và đánh dấu truy cập ok. Chỉ lưu để hiển thị — không tự kiểm hay ràng
    /// buộc gì trên các field này.
    pub fn apply_folder_lab_context(
        &self,
        folder_id: i64,
        remote: &crate::api::FolderDto,
    ) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute(
            "UPDATE sync_folder SET
                sample_name = ?2,
                sample_code = ?3,
                category = ?4,
                workflow_status = ?5,
                instrument_label = ?6,
                access_state = 'ok'
             WHERE id = ?1",
            params![
                folder_id,
                remote.sample_name.as_deref(),
                remote.sample_code.as_deref(),
                remote.category.as_deref(),
                remote.workflow_status.as_deref(),
                remote.nguon_thiet_bi.as_deref()
            ],
        )?;
        Ok(())
    }

    /// Lưu lại trạng thái truy cập folder (`ok`/`denied`/...) sau lượt gọi server gần nhất. Chỉ
    /// là nơi ghi dữ liệu; quyết định khi nào đặt `denied` và việc enforce dựa trên giá trị này
    /// nằm ở caller (`sync::engine`), không phải ở đây.
    pub fn set_folder_access_state(&self, folder_id: i64, access_state: &str) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute(
            "UPDATE sync_folder SET access_state = ?2 WHERE id = ?1",
            params![folder_id, access_state],
        )?;
        Ok(())
    }

    /// Liệt kê mọi folder đã đăng ký cục bộ, kèm ngữ cảnh mẫu LIMS và trạng thái truy cập.
    pub fn list_folders(&self) -> AppResult<Vec<FolderRow>> {
        let conn = self.conn.lock();
        let mut stmt = conn.prepare(
            "SELECT id, local_path, remote_id, logical_root, enabled, recursive,
                    sample_name, sample_code, category, workflow_status, instrument_label,
                    COALESCE(access_state, 'ok')
             FROM sync_folder ORDER BY id",
        )?;
        let rows = stmt
            .query_map([], |row| {
                Ok(FolderRow {
                    id: row.get(0)?,
                    local_path: row.get(1)?,
                    remote_id: row.get(2)?,
                    logical_root: row.get(3)?,
                    enabled: row.get::<_, i64>(4)? == 1,
                    recursive: row.get::<_, i64>(5)? == 1,
                    sample_name: row.get(6)?,
                    sample_code: row.get(7)?,
                    category: row.get(8)?,
                    workflow_status: row.get(9)?,
                    instrument_label: row.get(10)?,
                    access_state: row.get(11)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Xóa binding folder cục bộ (rule, tệp, job liên quan bị xóa theo qua CASCADE).
    pub fn delete_folder(&self, folder_id: i64) -> AppResult<()> {
        let conn = self.conn.lock();
        let deleted = conn.execute("DELETE FROM sync_folder WHERE id = ?1", params![folder_id])?;
        if deleted == 0 {
            return Err(AppError::FolderNotFound);
        }
        conn.execute(
            "DELETE FROM app_meta WHERE key = ?1",
            params![format!("needs_hydration:{folder_id}")],
        )?;
        Ok(())
    }

    /// Đặt/xóa cờ bền "folder này vừa được gắn và chưa hydrate xong từ server". Cờ sống qua lần
    /// khởi động lại nên một lượt hydrate hỏng vì mất mạng sẽ được thử lại.
    pub fn set_needs_hydration(&self, folder_id: i64, needed: bool) -> AppResult<()> {
        let key = format!("needs_hydration:{folder_id}");
        if needed {
            return self.meta_set(&key, "1");
        }
        let conn = self.conn.lock();
        conn.execute("DELETE FROM app_meta WHERE key = ?1", params![key])?;
        Ok(())
    }

    /// True nếu folder còn cờ chờ hydrate.
    pub fn needs_hydration(&self, folder_id: i64) -> AppResult<bool> {
        Ok(self
            .meta_get(&format!("needs_hydration:{folder_id}"))?
            .is_some())
    }

    /// Đọc rule đặt tên/lọc tệp đã lưu cục bộ cho một folder.
    pub fn folder_rules(&self, folder_id: i64) -> AppResult<Vec<SyncRule>> {
        let conn = self.conn.lock();
        let mut stmt = conn.prepare(
            "SELECT type, pattern, recursive, enabled FROM sync_rule WHERE folder_id = ?1",
        )?;
        let rows = stmt
            .query_map(params![folder_id], |row| {
                Ok(SyncRule {
                    kind: row.get(0)?,
                    pattern: row.get(1)?,
                    recursive: row.get::<_, i64>(2)? == 1,
                    enabled: row.get::<_, i64>(3)? == 1,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Tạo hoặc cập nhật bản ghi tệp cục bộ (kích thước, mtime, hash), đặt lại trạng thái
    /// `pending` để được xét đồng bộ.
    #[cfg(test)]
    pub fn upsert_file(
        &self,
        folder_id: i64,
        relative_path: &str,
        size: i64,
        mtime: i64,
        sha256: &str,
    ) -> AppResult<i64> {
        let conn = self.conn.lock();
        upsert_file_on(&conn, folder_id, relative_path, size, mtime, sha256)
    }

    /// Đọc hash SHA-256 đã lưu cục bộ của một tệp theo đường dẫn.
    pub fn file_sha(&self, folder_id: i64, relative_path: &str) -> AppResult<Option<String>> {
        let conn = self.conn.lock();
        let value = conn
            .query_row(
                "SELECT sha256 FROM sync_file WHERE folder_id = ?1 AND relative_path = ?2",
                params![folder_id, relative_path],
                |row| row.get(0),
            )
            .optional()?;
        Ok(value)
    }

    /// Đọc dấu vân tay nội dung đã lưu lúc enqueue của một tệp: kích thước, mtime (giây) và
    /// SHA-256. Dùng làm expected hash cho lượt upload nếu metadata hiện tại vẫn khớp.
    #[cfg(test)]
    pub fn file_fingerprint(&self, file_id: i64) -> AppResult<Option<FileFingerprint>> {
        let conn = self.conn.lock();
        file_fingerprint_on(&conn, file_id)
    }

    /// Đọc state phiên upload đã lưu của một job: `(session_id, uploaded_parts, content_hash)`.
    /// Chỉ cho test: `list_jobs` cố ý không trả các cột này cho UI.
    #[cfg(test)]
    pub fn job_session_state(
        &self,
        job_id: i64,
    ) -> AppResult<(Option<i64>, Option<String>, Option<String>)> {
        let conn = self.conn.lock();
        Ok(conn.query_row(
            "SELECT session_id, uploaded_parts, content_hash FROM sync_job WHERE id = ?1",
            params![job_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )?)
    }

    /// Đọc trạng thái đồng bộ cục bộ của một tệp (`pending`/`synced`/`conflict`/...).
    pub fn file_status(&self, folder_id: i64, relative_path: &str) -> AppResult<Option<String>> {
        let conn = self.conn.lock();
        let value = conn
            .query_row(
                "SELECT status FROM sync_file WHERE folder_id = ?1 AND relative_path = ?2",
                params![folder_id, relative_path],
                |row| row.get(0),
            )
            .optional()?;
        Ok(value)
    }

    /// Chạy `write` trong MỘT transaction, dưới cùng mutex với `delete_folder`, chỉ khi binding
    /// `binding` vẫn còn nguyên (cùng `id`, `local_path`, `remote_id`). Mọi thao tác ghi dựa trên
    /// một danh sách folder đọc từ trước (quét cục bộ, poll change feed, hydrate) phải đi qua đây:
    /// thư mục có thể bị gỡ — hoặc gỡ rồi gắn thư mục khác trùng rowid — trong lúc chờ hash/HTTP.
    /// Trả `None` (không ghi gì) khi binding đã đổi.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    pub fn with_current_binding<T>(
        &self,
        binding: &FolderBinding,
        write: impl FnOnce(&Connection) -> AppResult<T>,
    ) -> AppResult<Option<T>> {
        let conn = self.conn.lock();
        let tx = conn.unchecked_transaction()?;
        if !binding_is_current(&tx, binding)? {
            return Ok(None);
        }
        let value = write(&tx)?;
        tx.commit()?;
        Ok(Some(value))
    }

    /// Như `with_current_binding`, và thêm điều kiện tệp `file_id` vẫn thuộc folder đó (tệp có thể
    /// đã bị cascade xóa, hoặc id của nó đã được tái dùng cho tệp khác).
    pub fn with_bound_file<T>(
        &self,
        binding: &FolderBinding,
        file_id: i64,
        write: impl FnOnce(&Connection) -> AppResult<T>,
    ) -> AppResult<Option<T>> {
        let conn = self.conn.lock();
        let tx = conn.unchecked_transaction()?;
        if !binding_is_current(&tx, binding)? || !file_in_folder(&tx, file_id, binding.id)? {
            return Ok(None);
        }
        let value = write(&tx)?;
        tx.commit()?;
        Ok(Some(value))
    }

    /// Ghi một thay đổi cục bộ đã hash (upsert `sync_file` + xếp hàng upload) trong một
    /// transaction qua `with_current_binding`: lượt quét đọc danh sách folder trước rồi mới hash
    /// từng tệp (có thể nhiều giây), nên thư mục có thể đã bị gỡ. Trả `None` khi đã bỏ qua.
    pub fn record_local_change(
        &self,
        binding: &FolderBinding,
        relative_path: &str,
        size: i64,
        mtime: i64,
        sha256: &str,
    ) -> AppResult<Option<i64>> {
        self.with_current_binding(binding, |conn| {
            let file_id = upsert_file_on(conn, binding.id, relative_path, size, mtime, sha256)?;
            let (remote_file_id, remote_version_id): (Option<i64>, Option<i64>) = conn.query_row(
                "SELECT remote_file_id, remote_version_id FROM sync_file WHERE id = ?1",
                params![file_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )?;
            enqueue_upload_on(
                conn,
                binding.id,
                file_id,
                relative_path,
                size,
                remote_file_id,
                remote_version_id,
            )
        })
    }

    /// Đọc một tệp cùng binding của folder chứa nó trong MỘT truy vấn, để các bước sau (sao lưu
    /// bản cục bộ, kiểm lại binding trước khi ghi) dùng đúng binding tại thời điểm đọc.
    pub fn file_with_binding(
        &self,
        file_id: i64,
    ) -> AppResult<Option<(RemoteFileRow, FolderBinding)>> {
        let conn = self.conn.lock();
        let row = conn
            .query_row(
                "SELECT file.id, file.folder_id, file.relative_path, file.remote_file_id,
                        file.remote_version_id, file.last_synced_hash, file.suppress_hash,
                        file.status, folder.local_path, folder.remote_id
                 FROM sync_file AS file
                 JOIN sync_folder AS folder ON folder.id = file.folder_id
                 WHERE file.id = ?1",
                params![file_id],
                |row| {
                    Ok((
                        RemoteFileRow {
                            id: row.get(0)?,
                            folder_id: row.get(1)?,
                            relative_path: row.get(2)?,
                            remote_file_id: row.get(3)?,
                            remote_version_id: row.get(4)?,
                            last_synced_hash: row.get(5)?,
                            suppress_hash: row.get(6)?,
                            status: row.get(7)?,
                        },
                        FolderBinding {
                            id: row.get(1)?,
                            local_path: row.get(8)?,
                            remote_id: row.get(9)?,
                        },
                    ))
                },
            )
            .optional()?;
        Ok(row)
    }

    /// Chụp danh tính của job `job` mà task vừa claim: chỉ trả `Some` nếu job vẫn `running`, dòng
    /// tệp vẫn đúng đường dẫn (và đúng tệp remote với download), và folder còn đó. `None` nghĩa là
    /// thư mục đã bị gỡ (hoặc job/tệp đã đổi) trước khi task kịp bắt đầu.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    pub fn running_job(&self, job: &JobRow) -> AppResult<Option<RunningJob>> {
        let remote_file_id = if job.operation == "download" {
            let Some(remote_file_id) = job.remote_file_id else {
                return Ok(None);
            };
            Some(remote_file_id)
        } else {
            None
        };
        let conn = self.conn.lock();
        let binding = conn
            .query_row(
                "SELECT folder.id, folder.local_path, folder.remote_id
                 FROM sync_job AS job
                 JOIN sync_file AS file ON file.id = job.file_id
                 JOIN sync_folder AS folder ON folder.id = file.folder_id
                 WHERE job.id = ?1 AND job.file_id = ?2 AND job.folder_id = ?3
                   AND job.operation = ?4 AND job.status = 'running'
                   AND file.relative_path = ?5
                   AND (?6 IS NULL OR file.remote_file_id = ?6)",
                params![
                    job.id,
                    job.file_id,
                    job.folder_id,
                    job.operation,
                    job.relative_path,
                    remote_file_id
                ],
                |row| {
                    Ok(FolderBinding {
                        id: row.get(0)?,
                        local_path: row.get(1)?,
                        remote_id: row.get(2)?,
                    })
                },
            )
            .optional()?;
        Ok(binding.map(|binding| RunningJob {
            job_id: job.id,
            file_id: job.file_id,
            operation: job.operation.clone(),
            relative_path: job.relative_path.clone(),
            remote_file_id,
            binding,
        }))
    }

    /// Như `running_job` nhưng `unwrap`: test chụp danh tính của job vừa claim.
    #[cfg(test)]
    pub fn owned(&self, job: &JobRow) -> RunningJob {
        self.running_job(job).unwrap().expect("job is running")
    }

    /// Chạy `write` trong MỘT transaction, dưới cùng mutex với `delete_folder`, chỉ khi danh tính
    /// `owned` vẫn còn nguyên (`running_job_is_current`). Trả `None` (không ghi gì) nếu task đã mất
    /// quyền sở hữu — thư mục bị gỡ, hoặc rowid của job/tệp/folder đã được tái dùng cho binding
    /// khác, hoặc job đã bị tác nhân khác chuyển khỏi `running`.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    pub fn with_running_job<T>(
        &self,
        owned: &RunningJob,
        write: impl FnOnce(&Connection) -> AppResult<T>,
    ) -> AppResult<Option<T>> {
        let conn = self.conn.lock();
        let tx = conn.unchecked_transaction()?;
        if !running_job_is_current(&tx, owned)? {
            return Ok(None);
        }
        let value = write(&tx)?;
        tx.commit()?;
        Ok(Some(value))
    }

    /// Compare-and-set job của `owned` sang `status` chỉ khi task vẫn sở hữu nó (xem
    /// `with_running_job`); trả `false` và không ghi gì nếu không. Dùng cho mọi lượt chốt kết quả
    /// của worker (lỗi, tạm dừng, mất quyền, hết phiên, hoàn tất).
    #[allow(clippy::too_many_arguments)]
    pub fn transition_owned_job(
        &self,
        owned: &RunningJob,
        status: &str,
        error: Option<&str>,
        attempt: i64,
        retry_at: Option<i64>,
        remote_file_id: Option<i64>,
        remote_version_id: Option<i64>,
    ) -> AppResult<bool> {
        Ok(self
            .with_running_job(owned, |conn| {
                transition_running_job_on(
                    conn,
                    owned.job_id,
                    status,
                    error,
                    attempt,
                    retry_at,
                    remote_file_id,
                    remote_version_id,
                )
            })?
            .unwrap_or(false))
    }

    /// Tạo/cập nhật ánh xạ tệp remote → dòng `sync_file` của folder (qua `with_current_binding`);
    /// `None` nếu binding đã đổi. Dùng cho change feed và hydrate.
    pub fn ensure_remote_mapping_bound(
        &self,
        binding: &FolderBinding,
        relative_path: &str,
        remote_file_id: i64,
        remote_version_id: Option<i64>,
    ) -> AppResult<Option<i64>> {
        self.with_current_binding(binding, |conn| {
            ensure_remote_mapping_on(
                conn,
                binding.id,
                relative_path,
                remote_file_id,
                remote_version_id,
            )
        })
    }

    /// Đọc `(remote_file_id, remote_version_id)` đã biết của một tệp cục bộ.
    #[cfg(test)]
    pub fn file_remote_ids(&self, file_id: i64) -> AppResult<(Option<i64>, Option<i64>)> {
        let conn = self.conn.lock();
        Ok(conn.query_row(
            "SELECT remote_file_id, remote_version_id FROM sync_file WHERE id = ?1",
            params![file_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )?)
    }

    /// Tra một tệp cục bộ theo folder + đường dẫn tương đối.
    pub fn file_by_path(
        &self,
        folder_id: i64,
        relative_path: &str,
    ) -> AppResult<Option<RemoteFileRow>> {
        let conn = self.conn.lock();
        let row = conn
            .query_row(
                "SELECT id, folder_id, relative_path, remote_file_id, remote_version_id, last_synced_hash, suppress_hash, status
                 FROM sync_file WHERE folder_id = ?1 AND relative_path = ?2",
                params![folder_id, relative_path],
                |row| {
                    Ok(RemoteFileRow {
                        id: row.get(0)?,
                        folder_id: row.get(1)?,
                        relative_path: row.get(2)?,
                        remote_file_id: row.get(3)?,
                        remote_version_id: row.get(4)?,
                        last_synced_hash: row.get(5)?,
                        suppress_hash: row.get(6)?,
                        status: row.get(7)?,
                    })
                },
            )
            .optional()?;
        Ok(row)
    }

    /// Tra một tệp cục bộ theo id.
    pub fn file_by_id(&self, file_id: i64) -> AppResult<Option<RemoteFileRow>> {
        let conn = self.conn.lock();
        let row = conn
            .query_row(
                "SELECT id, folder_id, relative_path, remote_file_id, remote_version_id, last_synced_hash, suppress_hash, status
                 FROM sync_file WHERE id = ?1",
                params![file_id],
                |row| {
                    Ok(RemoteFileRow {
                        id: row.get(0)?,
                        folder_id: row.get(1)?,
                        relative_path: row.get(2)?,
                        remote_file_id: row.get(3)?,
                        remote_version_id: row.get(4)?,
                        last_synced_hash: row.get(5)?,
                        suppress_hash: row.get(6)?,
                        status: row.get(7)?,
                    })
                },
            )
            .optional()?;
        Ok(row)
    }

    /// Đọc cursor change-feed đã xử lý gần nhất của một folder trên server; 0 nếu chưa từng.
    pub fn change_cursor(&self, remote_folder_id: i64) -> AppResult<i64> {
        let key = format!("change_cursor:{remote_folder_id}");
        Ok(self
            .meta_get(&key)?
            .and_then(|value| value.parse().ok())
            .unwrap_or(0))
    }

    /// Lưu lại cursor change-feed đã xử lý gần nhất của một folder trên server.
    pub fn set_change_cursor(&self, remote_folder_id: i64, cursor: i64) -> AppResult<()> {
        self.meta_set(
            &format!("change_cursor:{remote_folder_id}"),
            &cursor.to_string(),
        )
    }

    /// Đảm bảo có một bản ghi tệp cục bộ ánh xạ tới `remote_file_id`/`remote_version_id` đã biết
    /// (dùng khi phát hiện tệp từ change feed/reconciliation, chưa có bản cục bộ trước đó).
    #[cfg(test)]
    pub fn ensure_remote_mapping(
        &self,
        folder_id: i64,
        relative_path: &str,
        remote_file_id: i64,
        remote_version_id: Option<i64>,
    ) -> AppResult<i64> {
        let conn = self.conn.lock();
        ensure_remote_mapping_on(
            &conn,
            folder_id,
            relative_path,
            remote_file_id,
            remote_version_id,
        )
    }

    /// Ghi nhận tệp cục bộ đã đồng bộ khớp với một version cụ thể trên server (sau tải lên hoặc
    /// tải xuống thành công).
    #[cfg(test)]
    pub fn apply_remote_base(
        &self,
        file_id: i64,
        remote_file_id: i64,
        remote_version_id: i64,
        hash: &str,
        size: i64,
    ) -> AppResult<()> {
        let conn = self.conn.lock();
        apply_remote_base_on(
            &conn,
            file_id,
            remote_file_id,
            remote_version_id,
            hash,
            size,
        )
    }

    /// Đánh dấu một tệp đang xung đột (bản cục bộ và bản server khác nhau), và chuyển mọi job
    /// đang chờ/chạy của nó sang `conflict`.
    #[cfg(test)]
    pub fn mark_file_conflict(
        &self,
        file_id: i64,
        remote_file_id: Option<i64>,
        remote_version_id: Option<i64>,
        message: &str,
    ) -> AppResult<()> {
        let conn = self.conn.lock();
        mark_file_conflict_on(&conn, file_id, remote_file_id, remote_version_id, message)
    }

    /// Xếp hàng (hoặc gộp vào job đang chờ) một lượt tải xuống cho một version cụ thể; job
    /// `failed` cũ được tái sử dụng và reset lại bộ đếm lỗi.
    #[allow(clippy::too_many_arguments)]
    #[cfg(test)]
    pub fn enqueue_download(
        &self,
        folder_id: i64,
        file_id: i64,
        relative_path: &str,
        size: i64,
        remote_file_id: i64,
        remote_version_id: i64,
        content_hash: &str,
        version_number: Option<i64>,
    ) -> AppResult<i64> {
        let conn = self.conn.lock();
        enqueue_download_on(
            &conn,
            folder_id,
            file_id,
            relative_path,
            size,
            remote_file_id,
            remote_version_id,
            content_hash,
            version_number,
        )
    }

    /// Chuyển mọi job tải lên đang chờ/chạy của một tệp sang `conflict` (server đã có version
    /// mới hơn trong lúc đó).
    #[cfg(test)]
    pub fn cancel_active_uploads(&self, file_id: i64) -> AppResult<()> {
        let conn = self.conn.lock();
        cancel_active_uploads_on(&conn, file_id)
    }

    /// Xóa cờ xung đột của một tệp sau khi chọn giữ bản cục bộ (đặt lại `synced` — bản conflict
    /// song song vẫn còn trên đĩa).
    pub fn dismiss_file_conflict(&self, file_id: i64) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute(
            "UPDATE sync_file SET status = 'synced' WHERE id = ?1",
            params![file_id],
        )?;
        conn.execute(
            "UPDATE sync_job SET status = 'completed', last_error = NULL
             WHERE file_id = ?1 AND status = 'conflict'",
            params![file_id],
        )?;
        Ok(())
    }

    /// Liệt kê các job tải xuống đang chờ/chạy của một folder (dùng để dọn tệp tạm mồ côi).
    pub fn list_download_temps(&self, folder_id: i64) -> AppResult<Vec<(i64, String)>> {
        let conn = self.conn.lock();
        let mut stmt = conn.prepare(
            "SELECT id, relative_path FROM sync_job
             WHERE folder_id = ?1 AND operation = 'download'
             AND status IN ('pending','running','retry_wait')",
        )?;
        let rows = stmt
            .query_map(params![folder_id], |row| Ok((row.get(0)?, row.get(1)?)))?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Liệt kê mọi tệp cục bộ đã có ánh xạ tới server, theo thứ tự đường dẫn.
    pub fn list_remote_files(&self) -> AppResult<Vec<RemoteFileRow>> {
        let conn = self.conn.lock();
        let mut stmt = conn.prepare(
            "SELECT id, folder_id, relative_path, remote_file_id, remote_version_id, last_synced_hash, suppress_hash, status
             FROM sync_file
             WHERE remote_file_id IS NOT NULL
             ORDER BY relative_path",
        )?;
        let rows = stmt
            .query_map([], |row| {
                Ok(RemoteFileRow {
                    id: row.get(0)?,
                    folder_id: row.get(1)?,
                    relative_path: row.get(2)?,
                    remote_file_id: row.get(3)?,
                    remote_version_id: row.get(4)?,
                    last_synced_hash: row.get(5)?,
                    suppress_hash: row.get(6)?,
                    status: row.get(7)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Xếp hàng (hoặc gộp vào job đang chờ) một lượt tải lên; job `failed` cũ được tái sử dụng
    /// và reset lại bộ đếm lỗi.
    #[cfg(test)]
    pub fn enqueue_upload(
        &self,
        folder_id: i64,
        file_id: i64,
        relative_path: &str,
        size: i64,
        remote_file_id: Option<i64>,
        remote_version_id: Option<i64>,
    ) -> AppResult<i64> {
        let conn = self.conn.lock();
        enqueue_upload_on(
            &conn,
            folder_id,
            file_id,
            relative_path,
            size,
            remote_file_id,
            remote_version_id,
        )
    }

    /// Claim job kế tiếp của mọi operation theo thứ tự FIFO (xem `claim_next_job`); chỉ cho test,
    /// app claim theo từng loại qua dispatcher.
    #[cfg(test)]
    pub fn next_job(&self) -> AppResult<Option<JobRow>> {
        self.claim_next_job(None, None)
    }

    /// Claim nguyên tử job kế tiếp sẵn sàng chạy (`pending`, hoặc `retry_wait` đã tới giờ) và
    /// chuyển nó sang `running` trong CÙNG một câu lệnh `UPDATE … RETURNING`, nên hai task (kể
    /// cả hai kết nối SQLite) không thể claim cùng một job. FIFO theo `id` trong phạm vi lọc:
    ///
    /// - `operation`: chỉ claim `upload` hoặc `download` (mỗi loại có slot riêng).
    /// - `max_bytes`: chỉ claim job có `bytes_total` không vượt ngưỡng (slot dành cho tệp nhỏ).
    /// - Bỏ qua tệp đang có BẤT KỲ job nào `running` (upload hay download): một `file_id` chỉ có
    ///   tối đa một transfer tại một thời điểm.
    /// - Job của folder đang `denied` bị bỏ qua nhưng KHÔNG bị xóa hay đánh lỗi: hàng đợi bền
    ///   được giữ nguyên và tự chạy lại khi folder về `ok`.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-work-with-a-mapped-folder
    pub fn claim_next_job(
        &self,
        operation: Option<&str>,
        max_bytes: Option<i64>,
    ) -> AppResult<Option<JobRow>> {
        let now = now_ts();
        let conn = self.conn.lock();
        let job = conn
            .query_row(
                "UPDATE sync_job SET status = 'running', updated_at = ?1
                 WHERE id = (
                   SELECT candidate.id FROM sync_job AS candidate
                   WHERE (candidate.status = 'pending'
                          OR (candidate.status = 'retry_wait'
                              AND (candidate.next_retry_at IS NULL OR candidate.next_retry_at <= ?1)))
                     AND (?2 IS NULL OR candidate.operation = ?2)
                     AND (?3 IS NULL OR candidate.bytes_total <= ?3)
                     AND NOT EXISTS (
                       SELECT 1 FROM sync_folder AS folder
                       WHERE folder.id = candidate.folder_id
                         AND COALESCE(folder.access_state, 'ok') = 'denied')
                     AND NOT EXISTS (
                       SELECT 1 FROM sync_job AS active
                       WHERE active.file_id = candidate.file_id AND active.status = 'running')
                   ORDER BY candidate.id LIMIT 1)
                 RETURNING id, folder_id, file_id, relative_path, operation, status, attempt_count, last_error, bytes_total, bytes_done, remote_file_id, remote_version_id, session_id, uploaded_parts, content_hash, target_version_number, part_size",
                params![now, operation, max_bytes],
                |row| {
                    Ok(JobRow {
                        id: row.get(0)?,
                        folder_id: row.get(1)?,
                        file_id: row.get(2)?,
                        relative_path: row.get(3)?,
                        operation: row.get(4)?,
                        status: row.get(5)?,
                        attempt_count: row.get(6)?,
                        last_error: row.get(7)?,
                        bytes_total: row.get(8)?,
                        bytes_done: row.get(9)?,
                        remote_file_id: row.get(10)?,
                        remote_version_id: row.get(11)?,
                        session_id: row.get(12)?,
                        uploaded_parts: row.get(13)?,
                        content_hash: row.get(14)?,
                        target_version_number: row.get(15)?,
                        part_size: row.get(16)?,
                    })
                },
            )
            .optional()?;
        Ok(job)
    }

    /// Cập nhật trạng thái một job bất kể trạng thái hiện tại; chỉ cho test dựng state, worker
    /// phải dùng `transition_running_job`. Khi `completed`, đồng bộ luôn tệp cục
    /// bộ sang `synced` với id/hash mới và dọn job `failed` cũ của cùng tệp+thao tác.
    #[cfg(test)]
    #[allow(clippy::too_many_arguments)]
    pub fn mark_job(
        &self,
        job_id: i64,
        status: &str,
        error: Option<&str>,
        attempt: i64,
        retry_at: Option<i64>,
        remote_file_id: Option<i64>,
        remote_version_id: Option<i64>,
    ) -> AppResult<()> {
        let conn = self.conn.lock();
        apply_job_transition(
            &conn,
            JobTransition {
                job_id,
                status,
                error,
                attempt,
                retry_at,
                remote_file_id,
                remote_version_id,
            },
            false,
        )?;
        Ok(())
    }

    /// Compare-and-set cho worker: chỉ ghi trạng thái mới nếu job VẪN đang `running`. Nếu tác
    /// nhân khác đã chuyển job đi (xung đột, hủy, khôi phục) thì không ghi đè và trả `false`.
    /// Job có cờ `rerun_requested` (có version/nội dung mới tới trong lúc chạy) được đưa lại
    /// `pending` ngay sau khi rời `running` với kết quả completed/failed/retry.
    #[cfg(test)]
    #[allow(clippy::too_many_arguments)]
    pub fn transition_running_job(
        &self,
        job_id: i64,
        status: &str,
        error: Option<&str>,
        attempt: i64,
        retry_at: Option<i64>,
        remote_file_id: Option<i64>,
        remote_version_id: Option<i64>,
    ) -> AppResult<bool> {
        let conn = self.conn.lock();
        apply_job_transition(
            &conn,
            JobTransition {
                job_id,
                status,
                error,
                attempt,
                retry_at,
                remote_file_id,
                remote_version_id,
            },
            true,
        )
    }

    /// Ghi finalize `conflict` của job upload `owned` trong MỘT transaction: compare-and-set job
    /// sang `conflict` và đánh dấu tệp xung đột cùng lúc. Chỉ ghi nếu task vẫn sở hữu job (xem
    /// `with_running_job`); nếu không — job/tệp đã bị xóa hoặc rowid đã được tái dùng — không ghi
    /// gì và trả `false`.
    ///
    /// Luật nghiệp vụ: docs/business/file-sync-governance.md#local-unbind-vs-remote-disable
    pub fn transition_running_job_with_conflict(
        &self,
        owned: &RunningJob,
        attempt: i64,
        remote_file_id: i64,
        remote_version_id: Option<i64>,
        conflict_version_id: Option<i64>,
        message: &str,
    ) -> AppResult<bool> {
        Ok(self
            .with_running_job(owned, |conn| {
                let changed = transition_running_job_on(
                    conn,
                    owned.job_id,
                    "conflict",
                    Some(message),
                    attempt,
                    None,
                    Some(remote_file_id),
                    remote_version_id,
                )?;
                if changed {
                    mark_file_conflict_on(
                        conn,
                        owned.file_id,
                        Some(remote_file_id),
                        conflict_version_id,
                        message,
                    )?;
                }
                Ok(changed)
            })?
            .unwrap_or(false))
    }

    /// True nếu folder đang bị server từ chối quyền (`access_state = 'denied'`).
    pub fn folder_access_denied(&self, folder_id: i64) -> AppResult<bool> {
        let conn = self.conn.lock();
        let state: Option<Option<String>> = conn
            .query_row(
                "SELECT access_state FROM sync_folder WHERE id = ?1",
                params![folder_id],
                |row| row.get(0),
            )
            .optional()?;
        Ok(state.flatten().as_deref() == Some("denied"))
    }

    /// Liệt kê tối đa 200 job gần nhất, mới nhất trước, cho UI trang Jobs.
    pub fn list_jobs(&self) -> AppResult<Vec<JobRow>> {
        let conn = self.conn.lock();
        let mut stmt = conn.prepare(
            "SELECT id, folder_id, file_id, relative_path, operation, status, attempt_count, last_error, bytes_total, bytes_done, remote_file_id, remote_version_id, target_version_number
             FROM sync_job ORDER BY id DESC LIMIT 200",
        )?;
        let rows = stmt
            .query_map([], |row| {
                Ok(JobRow {
                    id: row.get(0)?,
                    folder_id: row.get(1)?,
                    file_id: row.get(2)?,
                    relative_path: row.get(3)?,
                    operation: row.get(4)?,
                    status: row.get(5)?,
                    attempt_count: row.get(6)?,
                    last_error: row.get(7)?,
                    bytes_total: row.get(8)?,
                    bytes_done: row.get(9)?,
                    remote_file_id: row.get(10)?,
                    remote_version_id: row.get(11)?,
                    session_id: None,
                    uploaded_parts: None,
                    content_hash: None,
                    target_version_number: row.get(12)?,
                    part_size: None,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    }

    /// Đặt lại một job cụ thể về `pending` để thử lại ngay; lỗi nếu job không tồn tại.
    pub fn retry_job(&self, job_id: i64) -> AppResult<()> {
        let conn = self.conn.lock();
        let changed = conn.execute(
            "UPDATE sync_job SET status = 'pending', next_retry_at = NULL, attempt_count = 0,
                last_error = NULL
             WHERE id = ?1",
            params![job_id],
        )?;
        if changed == 0 {
            return Err(AppError::Message("Không tìm thấy công việc".into()));
        }
        Ok(())
    }

    /// Đặt lại mọi job `failed`/`retry_wait` của một folder về `pending` (dùng sau khi đăng ký
    /// lại folder bị tắt trước đó).
    pub fn retry_failed_jobs_for_folder(&self, folder_id: i64) -> AppResult<usize> {
        let conn = self.conn.lock();
        let changed = conn.execute(
            "UPDATE sync_job SET status = 'pending', next_retry_at = NULL, attempt_count = 0,
                last_error = NULL
             WHERE folder_id = ?1 AND status IN ('failed', 'retry_wait')",
            params![folder_id],
        )?;
        Ok(changed)
    }

    /// Đọc đường dẫn cục bộ của một folder theo id.
    #[cfg(test)]
    pub fn folder_path(&self, folder_id: i64) -> AppResult<PathBuf> {
        let conn = self.conn.lock();
        let path: String = conn.query_row(
            "SELECT local_path FROM sync_folder WHERE id = ?1",
            params![folder_id],
            |row| row.get(0),
        )?;
        Ok(PathBuf::from(path))
    }

    /// Đếm job theo nhóm trạng thái: `(pending, uploading, downloading, failed, conflict, done)`.
    pub fn counts(&self) -> AppResult<(i64, i64, i64, i64, i64, i64)> {
        let conn = self.conn.lock();
        let pending: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job WHERE status IN ('pending','retry_wait','running')",
            [],
            |r| r.get(0),
        )?;
        let uploading: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job WHERE status = 'running' AND operation = 'upload'",
            [],
            |r| r.get(0),
        )?;
        let downloading: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job WHERE status = 'running' AND operation = 'download'",
            [],
            |r| r.get(0),
        )?;
        let failed: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job j
             WHERE j.status = 'failed'
               AND j.id = (
                 SELECT MAX(id) FROM sync_job j2
                 WHERE j2.file_id = j.file_id AND j2.operation = j.operation
               )",
            [],
            |r| r.get(0),
        )?;
        let conflict: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job WHERE status = 'conflict'",
            [],
            |r| r.get(0),
        )?;
        let done: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sync_job WHERE status = 'completed'",
            [],
            |r| r.get(0),
        )?;
        Ok((pending, uploading, downloading, failed, conflict, done))
    }

    /// Lưu lại state phiên tải lên dở dang (session id, các phần đã tải, hash nội dung) để phục
    /// hồi sau khi khởi động lại.
    #[cfg(test)]
    pub fn save_job_session(
        &self,
        job_id: i64,
        session_id: i64,
        uploaded_parts: &str,
        content_hash: &str,
        part_size: Option<i64>,
    ) -> AppResult<()> {
        let conn = self.conn.lock();
        save_job_session_on(
            &conn,
            job_id,
            session_id,
            uploaded_parts,
            content_hash,
            part_size,
        )
    }

    /// Xóa state phiên tải lên dở dang đã lưu (dùng khi phiên đó không còn hợp lệ, phải bắt đầu
    /// lại từ đầu).
    #[cfg(test)]
    pub fn clear_job_session(&self, job_id: i64) -> AppResult<()> {
        let conn = self.conn.lock();
        clear_job_session_on(&conn, job_id)
    }

    /// Xóa toàn bộ folder/tệp/rule/job cục bộ và metadata gắn với tài khoản (dùng khi đăng nhập
    /// tài khoản khác); `client_uid` được giữ nguyên vì nó gắn với chính máy trạm.
    pub fn clear_account_local_state(&self) -> AppResult<()> {
        let conn = self.conn.lock();
        conn.execute("DELETE FROM sync_job", [])?;
        conn.execute("DELETE FROM sync_file", [])?;
        conn.execute("DELETE FROM sync_rule", [])?;
        conn.execute("DELETE FROM sync_folder", [])?;
        conn.execute(
            "DELETE FROM app_meta WHERE key IN ('device_id', 'user_name', 'user_login', 'user_id')
             OR key LIKE 'change_cursor:%'",
            [],
        )?;
        Ok(())
    }

    /// Đọc cấu hình đã lưu, hoặc mặc định nếu chưa từng lưu/parse lỗi.
    pub fn load_settings(&self) -> AppResult<crate::config::AppSettings> {
        let raw = self.meta_get("settings")?;
        if let Some(raw) = raw {
            let mut settings: crate::config::AppSettings =
                serde_json::from_str(&raw).unwrap_or_default();
            // URL đã lưu bị rỗng thì quay về mặc định của bản build (dev: localhost, release: production).
            if settings.odoo_url.trim().is_empty() {
                settings.odoo_url = crate::config::default_odoo_url();
            }
            Ok(settings)
        } else {
            Ok(crate::config::AppSettings::default())
        }
    }

    /// Lưu cấu hình mới.
    pub fn save_settings(&self, settings: &crate::config::AppSettings) -> AppResult<()> {
        self.meta_set("settings", &serde_json::to_string(settings)?)
    }
}

/// Tạo hoặc cập nhật bản ghi tệp cục bộ (kích thước, mtime, hash), đặt lại trạng thái
/// `pending` để được xét đồng bộ.
fn upsert_file_on(
    conn: &Connection,
    folder_id: i64,
    relative_path: &str,
    size: i64,
    mtime: i64,
    sha256: &str,
) -> AppResult<i64> {
    conn.execute(
        "INSERT INTO sync_file(folder_id, relative_path, size, mtime, sha256, status)
         VALUES(?1, ?2, ?3, ?4, ?5, 'pending')
         ON CONFLICT(folder_id, relative_path) DO UPDATE SET
            size = excluded.size,
            mtime = excluded.mtime,
            sha256 = excluded.sha256,
            status = 'pending'",
        params![folder_id, relative_path, size, mtime, sha256],
    )?;
    let id: i64 = conn.query_row(
        "SELECT id FROM sync_file WHERE folder_id = ?1 AND relative_path = ?2",
        params![folder_id, relative_path],
        |row| row.get(0),
    )?;
    Ok(id)
}

/// Xếp hàng (hoặc gộp vào job đang chờ) một lượt tải lên; job `failed` cũ được tái sử dụng
/// và reset lại bộ đếm lỗi.
fn enqueue_upload_on(
    conn: &Connection,
    folder_id: i64,
    file_id: i64,
    relative_path: &str,
    size: i64,
    remote_file_id: Option<i64>,
    remote_version_id: Option<i64>,
) -> AppResult<i64> {
    let existing = conn
        .query_row(
            "SELECT id, status FROM sync_job WHERE file_id = ?1 AND operation = 'upload'
             AND status IN ('pending','running','retry_wait')
             ORDER BY id DESC LIMIT 1",
            params![file_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()?;
    if let Some((id, status)) = existing {
        if status == "running" {
            // Tệp đổi trong lúc đang upload: chạy lại job sau lượt hiện tại để nội dung mới
            // không bị nuốt.
            conn.execute(
                "UPDATE sync_job SET rerun_requested = 1, updated_at = ?1 WHERE id = ?2",
                params![now_ts(), id],
            )?;
        }
        return Ok(id);
    }
    let now = now_ts();
    let failed = conn
        .query_row(
            "SELECT id FROM sync_job WHERE file_id = ?1 AND operation = 'upload'
             AND status = 'failed' ORDER BY id DESC LIMIT 1",
            params![file_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    if let Some(id) = failed {
        conn.execute(
            "UPDATE sync_job SET status = 'pending', last_error = NULL, next_retry_at = NULL,
                attempt_count = 0, bytes_done = 0, bytes_total = ?1, relative_path = ?2,
                remote_file_id = ?3, remote_version_id = ?4, updated_at = ?5
             WHERE id = ?6",
            params![
                size,
                relative_path,
                remote_file_id,
                remote_version_id,
                now,
                id
            ],
        )?;
        delete_failed_for_file(conn, file_id, "upload", Some(id))?;
        return Ok(id);
    }
    conn.execute(
        "INSERT INTO sync_job(folder_id, file_id, relative_path, operation, status, bytes_total, remote_file_id, remote_version_id, created_at, updated_at)
         VALUES(?1, ?2, ?3, 'upload', 'pending', ?4, ?5, ?6, ?7, ?7)",
        params![folder_id, file_id, relative_path, size, remote_file_id, remote_version_id, now],
    )?;
    Ok(conn.last_insert_rowid())
}

/// Xếp hàng (hoặc gộp vào job đang chờ) một lượt tải xuống cho một version cụ thể; job
/// `failed` cũ được tái sử dụng và reset lại bộ đếm lỗi.
#[allow(clippy::too_many_arguments)]
pub(crate) fn enqueue_download_on(
    conn: &Connection,
    folder_id: i64,
    file_id: i64,
    relative_path: &str,
    size: i64,
    remote_file_id: i64,
    remote_version_id: i64,
    content_hash: &str,
    version_number: Option<i64>,
) -> AppResult<i64> {
    let existing = conn
        .query_row(
            "SELECT id, status FROM sync_job WHERE file_id = ?1 AND operation = 'download'
             AND status IN ('pending','running','retry_wait')
             ORDER BY id DESC LIMIT 1",
            params![file_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()?;
    let now = now_ts();
    if let Some((id, status)) = existing {
        if status == "running" {
            // Không đổi target của job đang chạy (nó sẽ ghi base theo đúng byte nó tải); đánh
            // dấu chạy lại để version mới còn một lượt tải ngay khi job hiện tại kết thúc.
            conn.execute(
                "UPDATE sync_job SET rerun_requested = 1, updated_at = ?1 WHERE id = ?2",
                params![now, id],
            )?;
            return Ok(id);
        }
        conn.execute(
            "UPDATE sync_job SET remote_file_id = ?1, remote_version_id = ?2, content_hash = ?3,
                bytes_total = ?4, target_version_number = ?5, relative_path = ?6, updated_at = ?7,
                status = 'pending'
             WHERE id = ?8",
            params![
                remote_file_id,
                remote_version_id,
                content_hash,
                size,
                version_number,
                relative_path,
                now,
                id
            ],
        )?;
        return Ok(id);
    }
    let failed = conn
        .query_row(
            "SELECT id FROM sync_job WHERE file_id = ?1 AND operation = 'download'
             AND status = 'failed' ORDER BY id DESC LIMIT 1",
            params![file_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    if let Some(id) = failed {
        conn.execute(
            "UPDATE sync_job SET remote_file_id = ?1, remote_version_id = ?2, content_hash = ?3,
                bytes_total = ?4, target_version_number = ?5, relative_path = ?6, updated_at = ?7,
                status = 'pending', last_error = NULL, next_retry_at = NULL, attempt_count = 0,
                bytes_done = 0
             WHERE id = ?8",
            params![
                remote_file_id,
                remote_version_id,
                content_hash,
                size,
                version_number,
                relative_path,
                now,
                id
            ],
        )?;
        delete_failed_for_file(conn, file_id, "download", Some(id))?;
        return Ok(id);
    }
    conn.execute(
        "INSERT INTO sync_job(folder_id, file_id, relative_path, operation, status, bytes_total,
            remote_file_id, remote_version_id, content_hash, target_version_number, created_at, updated_at)
         VALUES(?1, ?2, ?3, 'download', 'pending', ?4, ?5, ?6, ?7, ?8, ?9, ?9)",
        params![
            folder_id,
            file_id,
            relative_path,
            size,
            remote_file_id,
            remote_version_id,
            content_hash,
            version_number,
            now
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

/// Ghi nhớ hash của một nội dung vừa tải xuống, để watcher tự bỏ qua sự kiện đổi tệp do chính
/// lượt tải đó gây ra.
pub(crate) fn set_suppress_hash_on(conn: &Connection, file_id: i64, hash: &str) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_file SET suppress_hash = ?1 WHERE id = ?2",
        params![hash, file_id],
    )?;
    Ok(())
}

/// Dấu vân tay nội dung đã lưu của một tệp (xem `Db::file_fingerprint`).
pub(crate) fn file_fingerprint_on(
    conn: &Connection,
    file_id: i64,
) -> AppResult<Option<FileFingerprint>> {
    Ok(conn
        .query_row(
            "SELECT size, mtime, sha256 FROM sync_file WHERE id = ?1",
            params![file_id],
            |row| {
                Ok(FileFingerprint {
                    size: row.get(0)?,
                    mtime: row.get(1)?,
                    sha256: row.get(2)?,
                })
            },
        )
        .optional()?)
}

/// Ghi đè dấu vân tay nội dung của một tệp sau khi hash lại; không đổi trạng thái đồng bộ.
pub(crate) fn set_file_fingerprint_on(
    conn: &Connection,
    file_id: i64,
    size: i64,
    mtime: i64,
    sha256: &str,
) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_file SET size = ?1, mtime = ?2, sha256 = ?3 WHERE id = ?4",
        params![size, mtime, sha256, file_id],
    )?;
    Ok(())
}

/// Ghi hash nội dung mà một job đã chứng minh được (xem `Db::set_job_content_hash`).
pub(crate) fn set_job_content_hash_on(
    conn: &Connection,
    job_id: i64,
    content_hash: &str,
) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_job SET content_hash = ?1, updated_at = ?2 WHERE id = ?3",
        params![content_hash, now_ts(), job_id],
    )?;
    Ok(())
}

/// Xóa state phiên truyền dở dang đã lưu của một job (xem `Db::clear_job_session`).
pub(crate) fn clear_job_session_on(conn: &Connection, job_id: i64) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_job SET session_id = NULL, uploaded_parts = NULL, content_hash = NULL,
            part_size = NULL, updated_at = ?1 WHERE id = ?2",
        params![now_ts(), job_id],
    )?;
    Ok(())
}

/// Ghi số byte đã truyền của một job.
pub(crate) fn set_progress_on(conn: &Connection, job_id: i64, done: i64) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_job SET bytes_done = ?1 WHERE id = ?2",
        params![done, job_id],
    )?;
    Ok(())
}

/// Hash nội dung đã đồng bộ gần nhất (base) của một tệp, `None` nếu chưa từng đồng bộ.
pub(crate) fn last_synced_hash_on(conn: &Connection, file_id: i64) -> AppResult<Option<String>> {
    Ok(conn
        .query_row(
            "SELECT last_synced_hash FROM sync_file WHERE id = ?1",
            params![file_id],
            |row| row.get(0),
        )
        .optional()?
        .flatten())
}

/// Lưu state phiên truyền dở dang của một job (session id, part đã xong, hash nội dung, part size).
pub(crate) fn save_job_session_on(
    conn: &Connection,
    job_id: i64,
    session_id: i64,
    uploaded_parts: &str,
    content_hash: &str,
    part_size: Option<i64>,
) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_job SET session_id = ?1, uploaded_parts = ?2, content_hash = ?3, part_size = ?4,
            updated_at = ?5 WHERE id = ?6",
        params![session_id, uploaded_parts, content_hash, part_size, now_ts(), job_id],
    )?;
    Ok(())
}

/// Ghi nhận tệp cục bộ đã đồng bộ khớp với một version cụ thể trên server (sau tải lên hoặc
/// tải xuống thành công).
pub(crate) fn apply_remote_base_on(
    conn: &Connection,
    file_id: i64,
    remote_file_id: i64,
    remote_version_id: i64,
    hash: &str,
    size: i64,
) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_file SET remote_file_id = ?1, remote_version_id = ?2, last_synced_hash = ?3,
            sha256 = ?3, size = ?4, status = 'synced', suppress_hash = NULL
         WHERE id = ?5",
        params![remote_file_id, remote_version_id, hash, size, file_id],
    )?;
    Ok(())
}

/// Chuyển mọi job tải lên đang chờ/chạy của một tệp sang `conflict` (server đã có version
/// mới hơn trong lúc đó).
pub(crate) fn cancel_active_uploads_on(conn: &Connection, file_id: i64) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_job SET status = 'conflict', last_error = 'Xung đột với phiên bản máy chủ',
            rerun_requested = 0
         WHERE file_id = ?1 AND operation = 'upload' AND status IN ('pending','running','retry_wait')",
        params![file_id],
    )?;
    Ok(())
}

/// Đánh dấu một tệp đang xung đột (bản cục bộ và bản server khác nhau), và chuyển mọi job
/// đang chờ/chạy của nó sang `conflict`.
pub(crate) fn mark_file_conflict_on(
    conn: &Connection,
    file_id: i64,
    remote_file_id: Option<i64>,
    remote_version_id: Option<i64>,
    message: &str,
) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_file SET status = 'conflict',
            remote_file_id = COALESCE(?1, remote_file_id),
            remote_version_id = COALESCE(?2, remote_version_id)
         WHERE id = ?3",
        params![remote_file_id, remote_version_id, file_id],
    )?;
    conn.execute(
        "UPDATE sync_job SET status = 'conflict', last_error = ?1, rerun_requested = 0
         WHERE file_id = ?2 AND status IN ('pending','running','retry_wait')",
        params![message, file_id],
    )?;
    Ok(())
}

/// Đảm bảo có một bản ghi tệp cục bộ ánh xạ tới `remote_file_id`/`remote_version_id` đã biết
/// (dùng khi phát hiện tệp từ change feed/reconciliation, chưa có bản cục bộ trước đó).
fn ensure_remote_mapping_on(
    conn: &Connection,
    folder_id: i64,
    relative_path: &str,
    remote_file_id: i64,
    remote_version_id: Option<i64>,
) -> AppResult<i64> {
    conn.execute(
        "INSERT INTO sync_file(folder_id, relative_path, size, mtime, status, remote_file_id, remote_version_id)
         VALUES(?1, ?2, 0, 0, 'pending', ?3, ?4)
         ON CONFLICT(folder_id, relative_path) DO UPDATE SET
            remote_file_id = excluded.remote_file_id,
            remote_version_id = COALESCE(excluded.remote_version_id, sync_file.remote_version_id)",
        params![folder_id, relative_path, remote_file_id, remote_version_id],
    )?;
    let id: i64 = conn.query_row(
        "SELECT id FROM sync_file WHERE folder_id = ?1 AND relative_path = ?2",
        params![folder_id, relative_path],
        |row| row.get(0),
    )?;
    Ok(id)
}

/// Xóa cờ xung đột của một tệp sau khi chọn giữ bản server (tệp đặt lại `pending`, job xung đột
/// thành `completed`).
pub(crate) fn clear_file_conflict_on(conn: &Connection, file_id: i64) -> AppResult<()> {
    conn.execute(
        "UPDATE sync_file SET status = 'pending' WHERE id = ?1",
        params![file_id],
    )?;
    conn.execute(
        "UPDATE sync_job SET status = 'completed', last_error = NULL
         WHERE file_id = ?1 AND status = 'conflict'",
        params![file_id],
    )?;
    Ok(())
}

/// True nếu dòng `sync_file` `file_id` vẫn là CÙNG tệp đã đọc (đường dẫn và tệp remote), chống
/// trường hợp id của nó đã được tái dùng cho tệp khác trong cùng binding.
pub(crate) fn file_row_matches(
    conn: &Connection,
    file_id: i64,
    relative_path: &str,
    remote_file_id: i64,
) -> AppResult<bool> {
    Ok(conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sync_file
                        WHERE id = ?1 AND relative_path = ?2 AND remote_file_id = ?3)",
        params![file_id, relative_path, remote_file_id],
        |row| row.get(0),
    )?)
}

/// True nếu folder `binding.id` vẫn còn với đúng `local_path` và `remote_id` đã đọc (so sánh
/// NULL-an-toàn cho `remote_id`).
fn binding_is_current(conn: &Connection, binding: &FolderBinding) -> AppResult<bool> {
    Ok(conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sync_folder
                        WHERE id = ?1 AND local_path = ?2 AND remote_id IS ?3)",
        params![binding.id, binding.local_path, binding.remote_id],
        |row| row.get(0),
    )?)
}

/// True nếu dòng `sync_file` `file_id` vẫn còn và thuộc folder `folder_id`.
fn file_in_folder(conn: &Connection, file_id: i64, folder_id: i64) -> AppResult<bool> {
    Ok(conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sync_file WHERE id = ?1 AND folder_id = ?2)",
        params![file_id, folder_id],
        |row| row.get(0),
    )?)
}

/// True nếu job `job_id` vẫn là CÙNG job task đã claim: cùng tệp, folder, loại, vẫn `running`,
/// và dòng tệp của nó vẫn thuộc folder đó với đúng đường dẫn — chống rowid job/tệp bị tái dùng
/// sau khi gỡ rồi gắn lại thư mục.
fn running_job_matches(
    conn: &Connection,
    job_id: i64,
    file_id: i64,
    folder_id: i64,
    operation: &str,
    relative_path: &str,
) -> AppResult<bool> {
    Ok(conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sync_job AS job
                        JOIN sync_file AS file ON file.id = job.file_id
                        WHERE job.id = ?1 AND job.file_id = ?2 AND job.folder_id = ?3
                          AND job.operation = ?4 AND job.status = 'running'
                          AND file.folder_id = ?3 AND file.relative_path = ?5)",
        params![job_id, file_id, folder_id, operation, relative_path],
        |row| row.get(0),
    )?)
}

/// True nếu task vẫn sở hữu `owned`: binding hiện hành, job cùng id/tệp/folder/loại vẫn `running`
/// với tệp cùng đường dẫn, và (với download) dòng tệp vẫn map đúng tệp remote.
fn running_job_is_current(conn: &Connection, owned: &RunningJob) -> AppResult<bool> {
    if !binding_is_current(conn, &owned.binding)? {
        return Ok(false);
    }
    if !running_job_matches(
        conn,
        owned.job_id,
        owned.file_id,
        owned.binding.id,
        &owned.operation,
        &owned.relative_path,
    )? {
        return Ok(false);
    }
    match owned.remote_file_id {
        Some(remote_file_id) => {
            file_row_matches(conn, owned.file_id, &owned.relative_path, remote_file_id)
        }
        None => Ok(true),
    }
}

/// Một lần chuyển trạng thái job (tham số của `apply_job_transition`).
struct JobTransition<'a> {
    job_id: i64,
    status: &'a str,
    error: Option<&'a str>,
    attempt: i64,
    retry_at: Option<i64>,
    remote_file_id: Option<i64>,
    remote_version_id: Option<i64>,
}

/// Compare-and-set một job `running` trên `conn` mà không tự mở transaction (xem
/// `Db::transition_running_job`), để ghép cùng lượt ghi khác trong transaction của caller.
#[allow(clippy::too_many_arguments)]
pub(crate) fn transition_running_job_on(
    conn: &Connection,
    job_id: i64,
    status: &str,
    error: Option<&str>,
    attempt: i64,
    retry_at: Option<i64>,
    remote_file_id: Option<i64>,
    remote_version_id: Option<i64>,
) -> AppResult<bool> {
    apply_job_transition_on(
        conn,
        JobTransition {
            job_id,
            status,
            error,
            attempt,
            retry_at,
            remote_file_id,
            remote_version_id,
        },
        true,
    )
}

/// Áp một lần chuyển trạng thái job trong một transaction riêng (xem `apply_job_transition_on`).
#[cfg(test)]
fn apply_job_transition(
    conn: &Connection,
    transition: JobTransition<'_>,
    require_running: bool,
) -> AppResult<bool> {
    let tx = conn.unchecked_transaction()?;
    let changed = apply_job_transition_on(&tx, transition, require_running)?;
    tx.commit()?;
    Ok(changed)
}

/// Áp một lần chuyển trạng thái job trên `conn` mà KHÔNG tự mở transaction, để ghép chung với
/// thao tác khác trong transaction của caller. `require_running` bật compare-and-set: job không
/// còn `running` thì không đổi gì và trả `false`. Khi `completed`, tệp cục bộ thành `synced` với
/// hash của job. Job vừa rời `running` mà có `rerun_requested` thì quay lại `pending` (lượt mới,
/// attempt 0) nếu kết quả là completed/failed/retry_wait; các kết quả khác chỉ xóa cờ.
fn apply_job_transition_on(
    conn: &Connection,
    transition: JobTransition<'_>,
    require_running: bool,
) -> AppResult<bool> {
    let JobTransition {
        job_id,
        status,
        error,
        attempt,
        retry_at,
        remote_file_id,
        remote_version_id,
    } = transition;
    let previous: Option<(String, i64)> = conn
        .query_row(
            "SELECT status, rerun_requested FROM sync_job WHERE id = ?1",
            params![job_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((previous_status, rerun_requested)) = previous else {
        return Ok(false);
    };
    if require_running && previous_status != "running" {
        return Ok(false);
    }
    conn.execute(
        "UPDATE sync_job SET status = ?1, last_error = ?2, attempt_count = ?3, next_retry_at = ?4,
            remote_file_id = COALESCE(?5, remote_file_id),
            remote_version_id = COALESCE(?6, remote_version_id),
            updated_at = ?7
         WHERE id = ?8",
        params![
            status,
            error,
            attempt,
            retry_at,
            remote_file_id,
            remote_version_id,
            now_ts(),
            job_id
        ],
    )?;
    if status == "completed" {
        conn.execute(
            "UPDATE sync_file SET remote_file_id = COALESCE(?1, remote_file_id),
                remote_version_id = COALESCE(?2, remote_version_id),
                last_synced_hash = COALESCE(
                    (SELECT content_hash FROM sync_job WHERE id = ?3),
                    last_synced_hash,
                    sha256
                ),
                suppress_hash = NULL,
                status = 'synced'
             WHERE id = (SELECT file_id FROM sync_job WHERE id = ?3)",
            params![remote_file_id, remote_version_id, job_id],
        )?;
        if let Ok((file_id, operation)) = conn.query_row(
            "SELECT file_id, operation FROM sync_job WHERE id = ?1",
            params![job_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
        ) {
            delete_failed_for_file(conn, file_id, &operation, Some(job_id))?;
        }
    }
    if previous_status == "running" && rerun_requested != 0 {
        if matches!(status, "completed" | "failed" | "retry_wait") {
            conn.execute(
                "UPDATE sync_job SET status = 'pending', last_error = NULL, next_retry_at = NULL,
                    attempt_count = 0, rerun_requested = 0
                 WHERE id = ?1",
                params![job_id],
            )?;
        } else {
            conn.execute(
                "UPDATE sync_job SET rerun_requested = 0 WHERE id = ?1",
                params![job_id],
            )?;
        }
    }
    Ok(true)
}

/// Xóa job `failed` cũ của cùng tệp+thao tác, giữ lại `keep_id` nếu có (job vừa được tái sử dụng).
fn delete_failed_for_file(
    conn: &rusqlite::Connection,
    file_id: i64,
    operation: &str,
    keep_id: Option<i64>,
) -> rusqlite::Result<usize> {
    if let Some(keep_id) = keep_id {
        conn.execute(
            "DELETE FROM sync_job WHERE file_id = ?1 AND operation = ?2 AND status = 'failed' AND id != ?3",
            params![file_id, operation, keep_id],
        )
    } else {
        conn.execute(
            "DELETE FROM sync_job WHERE file_id = ?1 AND operation = ?2 AND status = 'failed'",
            params![file_id, operation],
        )
    }
}

/// Xóa job `failed` mà cùng tệp+thao tác đã có một job mới hơn thành công/đang xử lý.
fn delete_resolved_failed_jobs(conn: &rusqlite::Connection) -> rusqlite::Result<usize> {
    conn.execute(
        "DELETE FROM sync_job
         WHERE status = 'failed'
           AND EXISTS (
             SELECT 1 FROM sync_job later
             WHERE later.file_id = sync_job.file_id
               AND later.operation = sync_job.operation
               AND later.id > sync_job.id
               AND later.status IN ('completed','pending','running','retry_wait')
           )",
        [],
    )
}

/// Thời điểm hiện tại tính bằng giây Unix epoch.
fn now_ts() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    /// Job còn `running` lúc khởi động phải được đưa về `pending`.
    #[test]
    fn recovers_running_jobs() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/a", "A", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        {
            let conn = db.conn.lock();
            conn.execute(
                "UPDATE sync_job SET status = 'running' WHERE id = ?1",
                params![job],
            )
            .unwrap();
        }
        db.recover_jobs().unwrap();
        let jobs = db.list_jobs().unwrap();
        assert_eq!(jobs[0].status, "pending");
    }

    /// Đặt lại job lỗi của một folder phải đưa nó về `pending` và cho `next_job` lấy lại được.
    /// Setting ẩn sống sót qua mọi đường lưu: lưu → đọc → sửa field hiển thị như payload IPC của
    /// form → lưu → đọc; và đường login chỉ sửa `odoo_url`.
    #[test]
    fn hidden_settings_survive_every_save_path() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let hidden = crate::config::AppSettings {
            upload_concurrency: 2,
            download_concurrency: 4,
            part_concurrency: 1,
            ..crate::config::AppSettings::default()
        };
        db.save_settings(&hidden).unwrap();
        // Form: frontend nhận đủ object từ get_settings, sửa field hiển thị, gửi nguyên object.
        let mut payload = serde_json::to_value(db.load_settings().unwrap()).unwrap();
        payload["debounce_ms"] = serde_json::json!(1500);
        payload["locale"] = serde_json::json!("en");
        let from_ipc: crate::config::AppSettings = serde_json::from_value(payload).unwrap();
        db.save_settings(&from_ipc).unwrap();
        let reloaded = db.load_settings().unwrap();
        assert_eq!(reloaded.debounce_ms, 1500);
        assert_eq!(reloaded.locale, "en");
        assert_eq!(
            (
                reloaded.upload_concurrency,
                reloaded.download_concurrency,
                reloaded.part_concurrency
            ),
            (2, 4, 1)
        );
        // Login: đọc settings đã lưu, đổi odoo_url, lưu lại.
        let mut login = db.load_settings().unwrap();
        login.odoo_url = "https://odoo.example.com".into();
        db.save_settings(&login).unwrap();
        let reloaded = db.load_settings().unwrap();
        assert_eq!(reloaded.odoo_url, "https://odoo.example.com");
        assert_eq!(
            (
                reloaded.upload_concurrency,
                reloaded.download_concurrency,
                reloaded.part_concurrency
            ),
            (2, 4, 1)
        );
    }

    /// Retry thủ công (một job hoặc cả folder) bắt đầu lại bộ đếm lần thử và xóa lỗi cũ, để job
    /// đã chạm trần retry không `failed` lại ngay sau một lần thử.
    #[test]
    fn manual_retry_resets_attempt_count_and_error() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/a", "A", None, true, &[]).unwrap();
        let file_a = db.upsert_file(folder, "A.xlsx", 1, 1, "aa").unwrap();
        let file_b = db.upsert_file(folder, "B.xlsx", 1, 1, "bb").unwrap();
        let job_a = db
            .enqueue_upload(folder, file_a, "A.xlsx", 1, None, None)
            .unwrap();
        let job_b = db
            .enqueue_upload(folder, file_b, "B.xlsx", 1, None, None)
            .unwrap();
        for job in [job_a, job_b] {
            db.mark_job(
                job,
                "failed",
                Some("Đã thử 20 lần: 503"),
                20,
                None,
                None,
                None,
            )
            .unwrap();
        }
        db.retry_job(job_a).unwrap();
        assert_eq!(db.retry_failed_jobs_for_folder(folder).unwrap(), 1);
        for row in db.list_jobs().unwrap() {
            assert_eq!(row.status, "pending");
            assert_eq!(row.attempt_count, 0, "job {}", row.id);
            assert_eq!(row.last_error, None, "job {}", row.id);
        }
    }

    #[test]
    fn retry_failed_jobs_for_folder_requeues() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/a", "A", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(job, "failed", Some("disabled"), 1, None, None, None)
            .unwrap();
        assert_eq!(db.retry_failed_jobs_for_folder(folder).unwrap(), 1);
        let next = db.next_job().unwrap().unwrap();
        assert_eq!(next.id, job);
        // Claim nguyên tử trả trạng thái SAU khi claim.
        assert_eq!(next.status, "running");
    }

    /// Xếp hàng tải lên hai lần cho cùng một tệp đang chờ phải trả về cùng một job, không tạo
    /// job thứ hai.
    #[test]
    fn prevents_duplicate_active_jobs() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/b", "B", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let first = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        let second = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        assert_eq!(first, second);
        assert_eq!(db.list_jobs().unwrap().len(), 1);
    }

    /// Phục hồi một job `running` phải giữ nguyên session id và các phần đã tải trước đó.
    #[test]
    fn recovered_job_keeps_uploaded_parts() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/c", "C", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.save_job_session(job, 42, r#"[[1,"etag-1"]]"#, "abc", Some(16))
            .unwrap();
        {
            let conn = db.conn.lock();
            conn.execute(
                "UPDATE sync_job SET status = 'running' WHERE id = ?1",
                params![job],
            )
            .unwrap();
        }
        db.recover_jobs().unwrap();
        let next = db.next_job().unwrap().unwrap();
        assert_eq!(next.session_id, Some(42));
        assert_eq!(next.uploaded_parts.as_deref(), Some(r#"[[1,"etag-1"]]"#));
    }

    /// Xóa một folder phải xóa theo cả rule và job của nó (CASCADE).
    #[test]
    fn delete_folder_removes_rules_and_jobs() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db
            .upsert_folder(
                "/tmp/d",
                "D",
                None,
                true,
                &[SyncRule {
                    kind: "glob".into(),
                    pattern: "ABC*".into(),
                    recursive: true,
                    enabled: true,
                }],
            )
            .unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        db.enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.delete_folder(folder).unwrap();
        assert!(db.list_folders().unwrap().is_empty());
        assert!(db.list_jobs().unwrap().is_empty());
        assert!(db.folder_rules(folder).unwrap().is_empty());
    }

    /// Hoàn tất một job phải cập nhật id/version từ xa và chuyển tệp cục bộ sang `synced`.
    #[test]
    fn completing_job_marks_file_synced() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/e", "E", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(job, "completed", None, 1, None, Some(9), Some(3))
            .unwrap();
        let conn = db.conn.lock();
        let (remote_file_id, remote_version_id, status): (Option<i64>, Option<i64>, String) = conn
            .query_row(
                "SELECT remote_file_id, remote_version_id, status FROM sync_file WHERE id = ?1",
                params![file],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(remote_file_id, Some(9));
        assert_eq!(remote_version_id, Some(3));
        assert_eq!(status, "synced");
        drop(conn);
        assert_eq!(
            db.file_status(folder, "ABC.xlsx").unwrap().as_deref(),
            Some("synced")
        );
    }

    /// Bỏ qua xung đột (giữ bản cục bộ) phải đưa tệp về `synced`, job về `completed`, và bộ đếm
    /// conflict về 0.
    #[test]
    fn dismiss_conflict_clears_job_and_file() {
        let dir = tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/c", "C", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(
            job,
            "conflict",
            Some("Phát hiện xung đột"),
            1,
            None,
            Some(9),
            Some(2),
        )
        .unwrap();
        db.mark_file_conflict(file, Some(9), Some(2), "Phát hiện xung đột")
            .unwrap();
        db.dismiss_file_conflict(file).unwrap();
        assert_eq!(
            db.file_status(folder, "ABC.xlsx").unwrap().as_deref(),
            Some("synced")
        );
        assert_eq!(db.list_jobs().unwrap()[0].status, "completed");
        let (_p, _u, _d, _f, conflict, _done) = db.counts().unwrap();
        assert_eq!(conflict, 0);
    }

    /// Xếp hàng tải lên mới phải giữ nguyên id/version từ xa đã biết của tệp.
    #[test]
    fn enqueue_copies_remote_ids_from_file() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/f", "F", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        db.mark_job(
            db.enqueue_upload(folder, file, "ABC.xlsx", 1, Some(20), Some(16))
                .unwrap(),
            "completed",
            None,
            1,
            None,
            Some(20),
            Some(16),
        )
        .unwrap();
        let (remote_file_id, remote_version_id) = db.file_remote_ids(file).unwrap();
        assert_eq!(remote_file_id, Some(20));
        assert_eq!(remote_version_id, Some(16));
        let job = db
            .enqueue_upload(
                folder,
                file,
                "ABC.xlsx",
                2,
                remote_file_id,
                remote_version_id,
            )
            .unwrap();
        let row = db.next_job().unwrap().unwrap();
        assert_eq!(row.id, job);
        assert_eq!(row.remote_file_id, Some(20));
        assert_eq!(row.remote_version_id, Some(16));
    }

    /// Binding folder và metadata phải còn nguyên sau khi đóng và mở lại DB.
    #[test]
    fn folder_binding_survives_reopen() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("t.db");
        {
            let db = Db::open(&path).unwrap();
            db.upsert_folder("/data/lab", "LabResults", Some(42), true, &[])
                .unwrap();
            db.meta_set("client_uid", "pc-1").unwrap();
        }
        let db = Db::open(&path).unwrap();
        let folders = db.list_folders().unwrap();
        assert_eq!(folders.len(), 1);
        assert_eq!(folders[0].remote_id, Some(42));
        assert_eq!(folders[0].logical_root, "LabResults");
        assert_eq!(folders[0].local_path, "/data/lab");
        assert_eq!(db.meta_get("client_uid").unwrap().as_deref(), Some("pc-1"));
    }

    /// Đổi tài khoản phải xóa hết folder/job/metadata tài khoản cũ nhưng giữ nguyên `client_uid`.
    #[test]
    fn account_switch_clears_folder_bindings_keeps_client_uid() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        db.meta_set("client_uid", "pc-1").unwrap();
        db.meta_set("user_login", "sync_user_a").unwrap();
        db.upsert_folder("/data/a", "LabResults", Some(7), true, &[])
            .unwrap();
        db.set_change_cursor(7, 99).unwrap();
        db.clear_account_local_state().unwrap();
        assert!(db.list_folders().unwrap().is_empty());
        assert!(db.list_jobs().unwrap().is_empty());
        assert!(db.meta_get("user_login").unwrap().is_none());
        assert!(db.meta_get("device_id").unwrap().is_none());
        assert!(db.meta_get("change_cursor:7").unwrap().is_none());
        assert_eq!(db.meta_get("client_uid").unwrap().as_deref(), Some("pc-1"));
    }

    /// Ngữ cảnh mẫu LIMS và trạng thái truy cập bị từ chối phải được lưu và đọc lại đúng, rồi bị
    /// xóa sạch khi đổi tài khoản.
    #[test]
    fn lab_context_and_access_denied_persist() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db
            .upsert_folder("/data/lab", "LabResults", Some(42), true, &[])
            .unwrap();
        db.apply_folder_lab_context(
            folder,
            &crate::api::FolderDto {
                id: 42,
                name: "LabResults".into(),
                logical_root: "LabResults".into(),
                sync_mode: "upload_only".into(),
                enabled: true,
                device_id: 1,
                user_id: 1,
                rules: vec![],
                sample_name: Some("Mẫu A".into()),
                sample_code: Some("HS.1".into()),
                category: Some("result".into()),
                workflow_status: Some("dang_thuc_hien".into()),
                nguon_thiet_bi: Some("Analyzer-X".into()),
                owner_name: None,
                my_role: None,
                can_manage_members: false,
            },
        )
        .unwrap();
        let row = &db.list_folders().unwrap()[0];
        assert_eq!(row.sample_name.as_deref(), Some("Mẫu A"));
        assert_eq!(row.category.as_deref(), Some("result"));
        assert_eq!(row.instrument_label.as_deref(), Some("Analyzer-X"));
        assert_eq!(row.access_state, "ok");
        db.set_folder_access_state(folder, "denied").unwrap();
        assert_eq!(db.list_folders().unwrap()[0].access_state, "denied");
        db.clear_account_local_state().unwrap();
        assert!(db.list_folders().unwrap().is_empty());
    }

    /// "Ngừng đồng bộ" (bỏ binding cục bộ) và mất quyền là hai chuyện khác nhau: bỏ binding xóa
    /// dòng folder + hàng đợi của nó trên máy này, không đụng tệp trên đĩa và không đụng binding
    /// khác; mất quyền thì folder VẪN nằm trong danh sách với `denied` và hàng đợi được giữ lại.
    #[test]
    fn local_unbind_differs_from_access_revocation() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let unbound_dir = dir.path().join("unbound");
        std::fs::create_dir_all(&unbound_dir).unwrap();
        let local_file = unbound_dir.join("ABC.xlsx");
        std::fs::write(&local_file, b"lab result").unwrap();

        let unbound = db
            .upsert_folder(unbound_dir.to_str().unwrap(), "R", Some(7), true, &[])
            .unwrap();
        let revoked = db
            .upsert_folder("/tmp/revoked", "S", Some(8), true, &[])
            .unwrap();
        let unbound_file = db.upsert_file(unbound, "ABC.xlsx", 10, 1, "aa").unwrap();
        let revoked_file = db.upsert_file(revoked, "ABC.xlsx", 10, 1, "bb").unwrap();
        db.enqueue_upload(unbound, unbound_file, "ABC.xlsx", 10, None, None)
            .unwrap();
        let revoked_job = db
            .enqueue_upload(revoked, revoked_file, "ABC.xlsx", 10, None, None)
            .unwrap();

        db.delete_folder(unbound).unwrap();
        db.set_folder_access_state(revoked, "denied").unwrap();

        let folders = db.list_folders().unwrap();
        assert_eq!(folders.len(), 1);
        assert_eq!(folders[0].id, revoked);
        assert_eq!(folders[0].remote_id, Some(8));
        assert_eq!(folders[0].access_state, "denied");
        let jobs = db.list_jobs().unwrap();
        assert_eq!(jobs.len(), 1);
        assert_eq!(jobs[0].id, revoked_job);
        assert_eq!(jobs[0].status, "pending");
        assert!(db.next_job().unwrap().is_none());
        assert_eq!(std::fs::read(&local_file).unwrap(), b"lab result");

        // Remote id 7 không còn gắn ở máy này nên lại gắn được (sang đường dẫn khác cũng được).
        let rebound = db
            .upsert_folder("/tmp/elsewhere", "R", Some(7), true, &[])
            .unwrap();
        assert_ne!(rebound, revoked);
    }

    /// Job đã `failed` trước khi mất quyền không tự chạy lại khi được cấp lại quyền; người dùng
    /// bấm Retry (chính sách hiện hành, giữ nguyên).
    #[test]
    fn failed_jobs_stay_manual_retry_after_regrant() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/f", "F", Some(9), true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(job, "failed", Some("boom"), 1, None, None, None)
            .unwrap();
        db.set_folder_access_state(folder, "denied").unwrap();
        db.set_folder_access_state(folder, "ok").unwrap();
        assert!(db.next_job().unwrap().is_none());
        db.retry_job(job).unwrap();
        assert_eq!(db.next_job().unwrap().unwrap().id, job);
    }

    /// Job của folder `denied` không được chọn chạy nhưng vẫn nằm nguyên trong hàng đợi; folder
    /// khác vẫn chạy bình thường; khi folder về `ok` thì job tự chạy lại.
    #[test]
    fn next_job_skips_denied_folder_and_resumes_on_regrant() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let denied = db
            .upsert_folder("/tmp/denied", "Denied", Some(7), true, &[])
            .unwrap();
        let allowed = db
            .upsert_folder("/tmp/allowed", "Allowed", Some(8), true, &[])
            .unwrap();
        let denied_file = db.upsert_file(denied, "ABC.xlsx", 1, 1, "aa").unwrap();
        let allowed_file = db.upsert_file(allowed, "ABC.xlsx", 1, 1, "bb").unwrap();
        let denied_job = db
            .enqueue_upload(denied, denied_file, "ABC.xlsx", 1, None, None)
            .unwrap();
        let allowed_job = db
            .enqueue_upload(allowed, allowed_file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.set_folder_access_state(denied, "denied").unwrap();

        assert_eq!(db.next_job().unwrap().unwrap().id, allowed_job);
        assert!(db.next_job().unwrap().is_none());
        let paused = db
            .list_jobs()
            .unwrap()
            .into_iter()
            .find(|job| job.id == denied_job)
            .unwrap();
        assert_eq!(paused.status, "pending");

        db.set_folder_access_state(denied, "ok").unwrap();
        assert_eq!(db.next_job().unwrap().unwrap().id, denied_job);
    }

    /// Cursor change-feed phải là 0 khi chưa từng đặt, và giữ đúng giá trị mới nhất sau khi đặt.
    #[test]
    fn change_cursor_persists_only_when_set() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        assert_eq!(db.change_cursor(3).unwrap(), 0);
        db.set_change_cursor(3, 110).unwrap();
        assert_eq!(db.change_cursor(3).unwrap(), 110);
        db.set_change_cursor(3, 125).unwrap();
        assert_eq!(db.change_cursor(3).unwrap(), 125);
    }

    /// Job tải xuống còn `running` lúc khởi động phải phục hồi đúng thao tác và version đích.
    #[test]
    fn download_job_recovers_from_running() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db
            .upsert_folder("/tmp/dl", "DL", Some(1), true, &[])
            .unwrap();
        let file = db
            .ensure_remote_mapping(folder, "ABC.xlsx", 9, Some(4))
            .unwrap();
        let job = db
            .enqueue_download(folder, file, "ABC.xlsx", 32, 9, 5, "abc", Some(5))
            .unwrap();
        {
            let conn = db.conn.lock();
            conn.execute(
                "UPDATE sync_job SET status = 'running' WHERE id = ?1",
                params![job],
            )
            .unwrap();
        }
        db.recover_jobs().unwrap();
        let next = db.next_job().unwrap().unwrap();
        assert_eq!(next.id, job);
        assert_eq!(next.operation, "download");
        assert_eq!(next.remote_version_id, Some(5));
    }

    /// Hai lượt tải xuống liên tiếp cho cùng tệp phải gộp thành một job, nhắm tới version mới
    /// nhất.
    #[test]
    fn pending_download_coalesces_to_latest_version() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db
            .upsert_folder("/tmp/coal", "COAL", Some(1), true, &[])
            .unwrap();
        let file = db
            .ensure_remote_mapping(folder, "ABC.xlsx", 9, Some(5))
            .unwrap();
        let first = db
            .enqueue_download(folder, file, "ABC.xlsx", 32, 9, 5, "hash5", Some(5))
            .unwrap();
        let second = db
            .enqueue_download(folder, file, "ABC.xlsx", 40, 9, 7, "hash7", Some(7))
            .unwrap();
        assert_eq!(first, second);
        let row = db.next_job().unwrap().unwrap();
        assert_eq!(row.remote_version_id, Some(7));
        assert_eq!(row.target_version_number, Some(7));
        assert_eq!(row.bytes_total, 40);
    }

    /// Đặt cursor nhiều lần liên tiếp phải giữ đúng giá trị cuối cùng.
    #[test]
    fn cursor_advances_only_after_each_processed_change() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        for id in [101_i64, 110] {
            db.set_change_cursor(4, id).unwrap();
        }
        assert_eq!(db.change_cursor(4).unwrap(), 110);
    }

    /// Xóa state phiên tải lên đã lưu phải làm job trống hẳn session/parts/hash cũ.
    #[test]
    fn clear_job_session_drops_stale_upload_state() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/g", "G", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.save_job_session(job, 99, r#"[[1,"etag"]]"#, "oldhash", Some(16))
            .unwrap();
        db.clear_job_session(job).unwrap();
        let next = db.next_job().unwrap().unwrap();
        assert_eq!(next.id, job);
        assert!(next.session_id.is_none());
        assert!(next.uploaded_parts.is_none());
        assert!(next.content_hash.is_none());
    }

    /// Số job đang ở trạng thái `failed`, để test khẳng định ngắn gọn hơn.
    fn counts_failed(db: &Db) -> i64 {
        db.counts().unwrap().3
    }

    /// Xếp hàng lại một tệp có job `failed` phải tái sử dụng job đó và xóa cờ lỗi.
    #[test]
    fn enqueue_reuses_failed_upload_and_clears_error_count() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/h", "H", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let job = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(job, "failed", Some("disabled"), 1, None, None, None)
            .unwrap();
        assert_eq!(counts_failed(&db), 1);
        let again = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        assert_eq!(again, job);
        assert_eq!(counts_failed(&db), 0);
        assert_eq!(db.list_jobs().unwrap()[0].status, "pending");
    }

    /// Một job `completed` mới hơn phải khiến `recover_jobs` dọn sạch job `failed` cũ của cùng
    /// tệp+thao tác.
    #[test]
    fn later_success_drops_stale_failed_count() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let folder = db.upsert_folder("/tmp/i", "I", None, true, &[]).unwrap();
        let file = db.upsert_file(folder, "ABC.xlsx", 1, 1, "aa").unwrap();
        let failed = db
            .enqueue_upload(folder, file, "ABC.xlsx", 1, None, None)
            .unwrap();
        db.mark_job(failed, "failed", Some("disabled"), 1, None, None, None)
            .unwrap();
        {
            let conn = db.conn.lock();
            conn.execute(
                "INSERT INTO sync_job(folder_id, file_id, relative_path, operation, status, bytes_total, created_at, updated_at)
                 VALUES(?1, ?2, 'ABC.xlsx', 'upload', 'completed', 1, 2, 2)",
                params![folder, file],
            )
            .unwrap();
        }
        assert_eq!(counts_failed(&db), 0);
        db.recover_jobs().unwrap();
        let statuses: Vec<_> = db
            .list_jobs()
            .unwrap()
            .into_iter()
            .map(|job| job.status)
            .collect();
        assert!(statuses.iter().all(|status| status != "failed"));
    }
}
