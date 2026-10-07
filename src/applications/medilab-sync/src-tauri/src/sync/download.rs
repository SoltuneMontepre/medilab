use crate::api::ApiClient;
use crate::error::{AppError, AppResult};
use crate::sync::hash::sha256_file;
use chrono::Local;
use futures_util::StreamExt;
use std::fs::{self, OpenOptions};
use std::path::{Path, PathBuf};
use tokio::io::AsyncWriteExt;

/// True nếu đường dẫn là tệp tạm tải xuống hoặc bản sao xung đột của chính app — watcher phải
/// bỏ qua, không coi là thay đổi của người dùng.
pub fn is_internal_path(relative: &str) -> bool {
    let name = Path::new(relative)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or(relative);
    name.contains(".medilab-download-") || name.contains(" (conflict - ")
}

/// Đường dẫn tệp tạm để tải xuống vào, cùng thư mục với đích, gắn `job_id` để không đụng job khác.
pub fn download_temp_path(dest: &Path, job_id: i64) -> PathBuf {
    let name = dest
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("download");
    dest.with_file_name(format!("{name}.medilab-download-{job_id}.tmp"))
}

/// Đường dẫn bản sao xung đột: `<tên> (conflict - <thiết bị> - <giờ>)<phần mở rộng>`, cùng thư
/// mục với bản gốc.
pub fn conflict_copy_path(dest: &Path, device_label: &str) -> PathBuf {
    let stem = dest
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("file");
    let ext = dest
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .unwrap_or_default();
    let stamp = Local::now().format("%Y%m%d-%H%M%S");
    let safe_device: String = device_label
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' })
        .collect();
    dest.with_file_name(format!("{stem} (conflict - {safe_device} - {stamp}){ext}"))
}

/// Ép hệ điều hành flush nội dung tệp xuống đĩa (fsync) trước khi thay thế nguyên tử.
pub fn fsync_path(path: &Path) -> AppResult<()> {
    let file = OpenOptions::new().read(true).write(true).open(path)?;
    file.sync_all()?;
    Ok(())
}

/// Thay thế `dest` bằng `temp` một cách nguyên tử (fsync rồi rename); trên Windows tự xóa đích
/// đang tồn tại nếu rename bị chặn.
#[tracing::instrument(level = "debug", name = "sync.atomic_replace", skip_all)]
pub fn atomic_replace(temp: &Path, dest: &Path) -> AppResult<()> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    fsync_path(temp)?;
    match fs::rename(temp, dest) {
        Ok(()) => Ok(()),
        #[cfg(windows)]
        Err(_) if dest.exists() => {
            fs::remove_file(dest)?;
            fs::rename(temp, dest)?;
            Ok(())
        }
        #[cfg(not(windows))]
        Err(err) if dest.exists() => Err(err.into()),
        Err(err) => Err(err.into()),
    }
}

/// Kiểm tệp vừa tải xuống đúng kích thước và SHA-256 đã cam kết trước khi được phép thay thế
/// bản đích.
#[tracing::instrument(
    level = "debug",
    name = "sync.verify_download",
    skip_all,
    fields(
        expected_byte_count = expected_size,
        actual_byte_count = tracing::field::Empty
    )
)]
pub fn verify_download(path: &Path, expected_size: i64, expected_hash: &str) -> AppResult<()> {
    let meta = fs::metadata(path)?;
    let size = meta.len() as i64;
    tracing::Span::current().record("actual_byte_count", size);
    if size != expected_size {
        return Err(AppError::Message(format!(
            "Toàn vẹn tải xuống thất bại: kích thước {size} ≠ {expected_size}"
        )));
    }
    let digest = sha256_file(path)?;
    if digest != expected_hash {
        return Err(AppError::Message(
            "Toàn vẹn tải xuống thất bại: SHA-256 không khớp".into(),
        ));
    }
    Ok(())
}

/// Trước khi ghi đè bản cục bộ đang xung đột, sao nó sang một tên có nhãn thiết bị + giờ để giữ
/// lại cả hai bản.
pub fn preserve_local_copy(dest: &Path, device_label: &str) -> AppResult<Option<PathBuf>> {
    if !dest.is_file() {
        return Ok(None);
    }
    let copy = conflict_copy_path(dest, device_label);
    fs::copy(dest, &copy)?;
    Ok(Some(copy))
}

/// Ghi bytes cho trước vào một tệp (tạo/ghi đè, flush + fsync), dùng để dựng fixture cho test.
#[cfg(test)]
fn write_temp_bytes(path: &Path, bytes: &[u8]) -> AppResult<()> {
    use std::io::Write;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(path)?;
    file.write_all(bytes)?;
    file.flush()?;
    file.sync_all()?;
    Ok(())
}

/// Kết quả ghi một object xuống tệp tạm.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DownloadedObject {
    /// Tổng số byte của tệp tạm sau lượt này.
    pub written: i64,
    /// Số byte đã có sẵn và được tiếp tục bằng Range (206); 0 nếu tải lại từ đầu.
    pub resumed_from: i64,
}

/// Tải nội dung từ `url` vào `temp`, tiếp tục từ byte đã có (Range) nếu tệp tạm dở dang còn hợp
/// lệ; server không hỗ trợ resume (416/không phải 206) thì tải lại từ đầu. `is_paused` được hỏi
/// sau mỗi chunk: đang tạm dừng thì ghi xuống đĩa phần đã nhận và trả `AppError::Paused`, tệp
/// tạm được giữ để lần sau tiếp tục bằng Range.
#[tracing::instrument(
    level = "debug",
    name = "sync.download_object",
    skip_all,
    fields(
        expected_byte_count = expected_size,
        resumed_byte_count = tracing::field::Empty,
        byte_count = tracing::field::Empty
    )
)]
pub async fn download_object(
    url: &str,
    temp: &Path,
    expected_size: i64,
    is_paused: impl Fn() -> bool,
) -> AppResult<DownloadedObject> {
    let existing = fs::metadata(temp)
        .ok()
        .map(|meta| meta.len() as i64)
        .unwrap_or(0);
    tracing::Span::current().record("resumed_byte_count", existing);
    let resume = existing > 0 && existing < expected_size;
    if existing > expected_size {
        let _ = fs::remove_file(temp);
    }
    if let Some(parent) = temp.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut request = crate::api::storage_download_http()?.get(url);
    if resume {
        request = request.header("Range", format!("bytes={existing}-"));
    }
    let response = request.send().await?;
    let status = response.status();
    if status.as_u16() == 416 {
        let _ = fs::remove_file(temp);
        return Err(AppError::Message("Tải xuống cần bắt đầu lại".into()));
    }
    if !status.is_success() {
        return Err(AppError::Message(format!(
            "Tải xuống thất bại ({status}) {}",
            ApiClient::sanitize_url(url)
        )));
    }
    let restart = !resume || status.as_u16() != 206;
    let mut file = if restart {
        tokio::fs::File::create(temp).await?
    } else {
        tokio::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(temp)
            .await?
    };
    let mut written = if restart { 0_i64 } else { existing };
    let mut stream = response.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let bytes = chunk?;
        file.write_all(&bytes).await?;
        written += bytes.len() as i64;
        if is_paused() {
            // Giữ phần đã nhận trên đĩa để lần tiếp tục chỉ tải phần còn thiếu.
            file.flush().await?;
            file.sync_all().await?;
            return Err(AppError::Paused);
        }
    }
    file.flush().await?;
    file.sync_all().await?;
    tracing::Span::current().record("byte_count", written);
    Ok(DownloadedObject {
        written,
        resumed_from: if restart { 0 } else { existing },
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    /// Tệp tạm tải xuống và bản sao xung đột phải được nhận diện là đường dẫn nội bộ; tệp thường
    /// thì không.
    #[test]
    fn ignores_download_temps_and_conflict_copies() {
        assert!(is_internal_path("ABC.xlsx.medilab-download-9.tmp"));
        assert!(is_internal_path(
            "ABC (conflict - lab-1 - 20260827-010203).xlsx"
        ));
        assert!(!is_internal_path("ABC.xlsx"));
    }

    /// Thay thế nguyên tử phải để lại đúng nội dung mới và không còn sót tệp tạm.
    #[test]
    fn atomic_replace_does_not_leave_partial_dest() {
        let dir = tempdir().unwrap();
        let dest = dir.path().join("report.xlsx");
        std::fs::write(&dest, b"old").unwrap();
        let temp = download_temp_path(&dest, 7);
        write_temp_bytes(&temp, b"new-bytes").unwrap();
        atomic_replace(&temp, &dest).unwrap();
        assert_eq!(std::fs::read(&dest).unwrap(), b"new-bytes");
        assert!(!temp.exists());
    }

    /// Toàn vẹn kích thước sai phải báo lỗi và giữ nguyên bản đích, không thay thế.
    #[test]
    fn integrity_mismatch_keeps_original() {
        let dir = tempdir().unwrap();
        let dest = dir.path().join("report.xlsx");
        std::fs::write(&dest, b"keep-me").unwrap();
        let temp = download_temp_path(&dest, 3);
        write_temp_bytes(&temp, b"wrong").unwrap();
        let err = verify_download(&temp, 5, "deadbeef").unwrap_err();
        assert!(err.to_string().contains("Toàn vẹn"));
        assert_eq!(std::fs::read(&dest).unwrap(), b"keep-me");
    }

    /// Cả kích thước và hash phải khớp; sai kích thước dù đúng hash vẫn phải báo lỗi.
    #[test]
    fn hash_and_size_must_both_match() {
        let dir = tempdir().unwrap();
        let temp = dir.path().join("x.tmp");
        write_temp_bytes(&temp, b"medilab").unwrap();
        let digest = sha256_file(&temp).unwrap();
        verify_download(&temp, 7, &digest).unwrap();
        assert!(verify_download(&temp, 8, &digest).is_err());
    }

    /// Giữ bản sao xung đột phải để nguyên bản gốc, tạo một bản sao mới có tên khác chứa nội
    /// dung giống hệt.
    #[test]
    fn conflict_copy_preserves_original() {
        let dir = tempdir().unwrap();
        let dest = dir.path().join("report.xlsx");
        std::fs::write(&dest, b"local-a").unwrap();
        let copy = preserve_local_copy(&dest, "LAB PC").unwrap().unwrap();
        assert_ne!(copy, dest);
        assert!(copy
            .file_name()
            .unwrap()
            .to_string_lossy()
            .contains("conflict"));
        assert_eq!(std::fs::read(&copy).unwrap(), b"local-a");
        assert_eq!(std::fs::read(&dest).unwrap(), b"local-a");
    }

    #[cfg(windows)]
    /// Trên Windows, thay thế một tệp đích đang bị khóa (mở độc quyền) phải báo lỗi rõ ràng và
    /// giữ nguyên nội dung cũ.
    #[test]
    fn atomic_replace_fails_when_dest_is_locked() {
        use std::os::windows::fs::OpenOptionsExt;

        let dir = tempdir().unwrap();
        let dest = dir.path().join("locked.xlsx");
        std::fs::write(&dest, b"old").unwrap();
        let temp = download_temp_path(&dest, 1);
        write_temp_bytes(&temp, b"new-bytes").unwrap();
        let lock = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .share_mode(0)
            .open(&dest)
            .unwrap();
        let err = atomic_replace(&temp, &dest).unwrap_err();
        let text = err.to_string().to_ascii_lowercase();
        assert!(
            text.contains("os error 32")
                || text.contains("denied")
                || text.contains("being used")
                || text.contains("cannot access"),
            "unexpected error: {err}"
        );
        drop(lock);
        assert_eq!(std::fs::read(&dest).unwrap(), b"old");
    }
}
