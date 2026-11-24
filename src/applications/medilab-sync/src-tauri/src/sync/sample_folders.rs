use crate::api::FolderDto;
use crate::error::AppResult;
use crate::storage::Db;
use crate::sync::rules::SyncRule;
use std::path::{Path, PathBuf};

/// Tên thư mục trên máy của từng loại folder mẫu. Chỉ dùng ký tự ASCII: phần mềm của máy đo cũ
/// không ghi được vào đường dẫn có dấu.
fn category_dir(category: &str) -> Option<&'static str> {
    match category {
        "raw" => Some("Raw Data"),
        "working" => Some("Working Documents"),
        "result" => Some("Results"),
        "report" => Some("Reports"),
        _ => None,
    }
}

/// Đổi một mã do server gửi thành tên một thư mục: ký tự hệ tệp cấm thành `_`, bỏ dấu chấm và
/// khoảng trắng ở hai đầu; `None` nếu không còn gì.
fn dir_name(code: &str) -> Option<String> {
    let name: String = code
        .chars()
        .map(|ch| match ch {
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            ch if ch.is_control() => '_',
            ch => ch,
        })
        .collect();
    let name = name.trim_matches(|ch: char| ch == '.' || ch.is_whitespace());
    (!name.is_empty()).then(|| name.to_string())
}

/// Thư mục trên máy của một folder mẫu dưới thư mục chính: `<thư mục chính>/<mã PTN>/<loại>`.
/// `None` cho folder không thuộc mẫu nào.
pub fn sample_folder_dir(home: &Path, remote: &FolderDto) -> Option<PathBuf> {
    let code = dir_name(remote.sample_code.as_deref()?)?;
    let category = category_dir(remote.category.as_deref()?)?;
    Some(home.join(code).join(category))
}

/// Gắn một folder mẫu vào thư mục của nó dưới thư mục chính, tạo thư mục nếu chưa có; thư mục còn
/// dòng mất liên kết (đổi máy chủ, tài khoản) được gắn lại vào dòng đó. `false` khi không gắn: mẫu
/// đã xong, folder đã gắn, người dùng đã ngừng đồng bộ nó, hoặc thư mục đã gắn với folder khác.
fn bind_sample_folder(db: &Db, home: &Path, remote: &FolderDto) -> AppResult<bool> {
    if !remote.sample_open || db.auto_bind_skipped(remote.id)? {
        return Ok(false);
    }
    let Some(dir) = sample_folder_dir(home, remote) else {
        return Ok(false);
    };
    let folders = db.list_folders()?;
    if folders
        .iter()
        .any(|folder| folder.remote_id == Some(remote.id))
    {
        return Ok(false);
    }
    std::fs::create_dir_all(&dir)?;
    let local_path = dir.canonicalize()?.to_string_lossy().into_owned();
    if folders
        .iter()
        .any(|folder| folder.local_path == local_path && folder.remote_id.is_some())
    {
        return Ok(false);
    }
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
    let folder_id = db.upsert_folder(
        &local_path,
        &remote.logical_root,
        Some(remote.id),
        true,
        &rules,
    )?;
    db.apply_folder_lab_context(folder_id, remote)?;
    db.set_needs_hydration(folder_id, true)?;
    Ok(true)
}

/// Gắn mọi folder của mẫu đang thử mà máy này chưa gắn vào thư mục chính, và trả về số folder vừa
/// gắn. Một folder lỗi (không tạo được thư mục...) chỉ được log, không chặn các folder còn lại.
pub fn bind_sample_folders(db: &Db, home: &Path, remotes: &[FolderDto]) -> AppResult<usize> {
    let mut bound = 0;
    for remote in remotes {
        match bind_sample_folder(db, home, remote) {
            Ok(true) => bound += 1,
            Ok(false) => {}
            Err(err) => {
                tracing::warn!(remote_id = remote.id, "could not bind sample folder: {err}")
            }
        }
    }
    Ok(bound)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Một folder trên server như `GET /folders` trả về; `sample` là (mã PTN, loại) nếu là folder mẫu.
    fn remote(id: i64, sample: Option<(&str, &str)>) -> FolderDto {
        serde_json::from_value(serde_json::json!({
            "id": id,
            "name": format!("Folder {id}"),
            "logical_root": format!("root-{id}"),
            "sync_mode": "upload_only",
            "enabled": true,
            "rules": [],
            "sample_code": sample.map(|(code, _)| code),
            "category": sample.map(|(_, category)| category),
        }))
        .unwrap()
    }

    /// Thư mục của một folder mẫu là `<thư mục chính>/<mã PTN>/<loại>`; folder không thuộc mẫu, loại
    /// lạ, hoặc mã không làm tên thư mục được thì không có chỗ.
    #[test]
    fn sample_folder_dir_is_the_lab_code_then_the_category() {
        let home = Path::new("/home/lab/MediLab");
        assert_eq!(
            sample_folder_dir(home, &remote(1, Some(("PTN.26.11.0001", "raw")))),
            Some(home.join("PTN.26.11.0001").join("Raw Data"))
        );
        assert_eq!(
            sample_folder_dir(home, &remote(2, Some(("PTN.26.11.0001", "result")))),
            Some(home.join("PTN.26.11.0001").join("Results"))
        );
        assert_eq!(
            sample_folder_dir(home, &remote(3, Some(("PTN/26:11", "raw")))),
            Some(home.join("PTN_26_11").join("Raw Data"))
        );
        assert_eq!(sample_folder_dir(home, &remote(4, None)), None);
        assert_eq!(
            sample_folder_dir(home, &remote(5, Some(("PTN.1", "unknown")))),
            None
        );
        assert_eq!(
            sample_folder_dir(home, &remote(6, Some(("..", "raw")))),
            None
        );
    }

    /// Folder của mẫu đang thử được gắn dưới thư mục chính, mỗi folder một lần; folder thường thì
    /// người dùng tự gắn.
    #[test]
    fn open_sample_folders_are_bound_under_the_home_folder_once() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let home = dir.path().join("MediLab");
        std::fs::create_dir(&home).unwrap();
        let remotes = vec![
            remote(1, Some(("PTN.26.11.0001", "raw"))),
            remote(2, Some(("PTN.26.11.0001", "result"))),
            remote(3, None),
        ];

        assert_eq!(bind_sample_folders(&db, &home, &remotes).unwrap(), 2);

        let folders = db.list_folders().unwrap();
        let raw = folders
            .iter()
            .find(|folder| folder.remote_id == Some(1))
            .unwrap();
        let expected = home.join("PTN.26.11.0001").join("Raw Data");
        assert!(expected.is_dir());
        assert_eq!(
            Path::new(&raw.local_path),
            expected.canonicalize().unwrap().as_path()
        );
        assert_eq!(raw.sample_code.as_deref(), Some("PTN.26.11.0001"));
        assert!(db.needs_hydration(raw.id).unwrap());
        assert_eq!(folders.len(), 2);
        assert_eq!(bind_sample_folders(&db, &home, &remotes).unwrap(), 0);
        assert_eq!(db.list_folders().unwrap().len(), 2);
    }

    /// Folder mất liên kết vì đổi máy chủ hoặc tài khoản được gắn lại tại chỗ, giữ nguyên dòng cũ.
    #[test]
    fn a_folder_unbound_by_a_server_change_is_bound_again_in_place() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let home = dir.path().join("MediLab");
        let raw = remote(1, Some(("PTN.26.11.0001", "raw")));
        let local = sample_folder_dir(&home, &raw).unwrap();
        std::fs::create_dir_all(&local).unwrap();
        let local = local.canonicalize().unwrap();
        let old = db
            .upsert_folder(local.to_str().unwrap(), "old", Some(7), true, &[])
            .unwrap();
        db.migrate_laboratory_api().unwrap();
        assert_eq!(db.list_folders().unwrap()[0].access_state, "unbound");

        assert_eq!(bind_sample_folders(&db, &home, &[raw]).unwrap(), 1);

        let folders = db.list_folders().unwrap();
        assert_eq!(folders.len(), 1);
        assert_eq!(folders[0].id, old);
        assert_eq!(folders[0].remote_id, Some(1));
        assert_eq!(folders[0].access_state, "ok");
    }

    /// Mẫu đã xong và folder người dùng đã ngừng đồng bộ không được tự gắn, cũng không tạo thư mục.
    #[test]
    fn closed_samples_and_stopped_folders_are_left_alone() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("t.db")).unwrap();
        let home = dir.path().join("MediLab");
        std::fs::create_dir(&home).unwrap();
        let mut closed = remote(1, Some(("PTN.26.10.0007", "raw")));
        closed.sample_open = false;
        let stopped = remote(2, Some(("PTN.26.11.0002", "raw")));
        db.set_auto_bind_skipped(2, true).unwrap();

        assert_eq!(
            bind_sample_folders(&db, &home, &[closed, stopped]).unwrap(),
            0
        );

        assert!(db.list_folders().unwrap().is_empty());
        assert_eq!(std::fs::read_dir(&home).unwrap().count(), 0);
    }
}
