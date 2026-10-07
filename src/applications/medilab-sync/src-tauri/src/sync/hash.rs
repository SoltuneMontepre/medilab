use crate::error::AppResult;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::time::{Duration, SystemTime};

/// Hash SHA-256 (hex) của toàn bộ nội dung tệp, đọc theo khối 1 MiB.
#[tracing::instrument(
    level = "debug",
    name = "sync.sha256_file",
    skip_all,
    fields(byte_count = tracing::field::Empty)
)]
pub fn sha256_file(path: &Path) -> AppResult<String> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    let mut byte_count = 0_u64;
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        byte_count += n as u64;
        hasher.update(&buf[..n]);
    }
    tracing::Span::current().record("byte_count", byte_count);
    Ok(hex::encode(hasher.finalize()))
}

/// True nếu kích thước/mtime của tệp không đổi qua một lượt chờ `wait`, để tránh đọc một tệp
/// đang được ghi dở.
pub fn is_stable(path: &Path, wait: Duration) -> bool {
    let Ok(first) = std::fs::metadata(path) else {
        return false;
    };
    std::thread::sleep(wait);
    let Ok(second) = std::fs::metadata(path) else {
        return false;
    };
    first.len() == second.len()
        && first.modified().ok() == second.modified().ok()
        && second
            .modified()
            .ok()
            .and_then(|t| t.elapsed().ok())
            .unwrap_or(Duration::ZERO)
            >= wait
}

/// Thời điểm sửa đổi cuối của tệp, tính bằng giây Unix epoch; 0 nếu không đọc được.
pub fn unix_mtime(path: &Path) -> i64 {
    std::fs::metadata(path)
        .ok()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{self, Write};
    use std::sync::{Arc, Mutex};
    use tempfile::{tempdir, NamedTempFile};
    use tracing_subscriber::fmt::format::FmtSpan;
    use tracing_subscriber::fmt::MakeWriter;

    /// Buffer chia sẻ để thu output của tracing subscriber trong test.
    #[derive(Clone)]
    struct SharedBuffer {
        bytes: Arc<Mutex<Vec<u8>>>,
    }

    /// Writer theo lượt mà tracing subscriber dùng để ghi vào buffer chia sẻ.
    struct SharedBufferGuard {
        bytes: Arc<Mutex<Vec<u8>>>,
    }

    impl Write for SharedBufferGuard {
        /// Ghi toàn bộ bytes tracing vào buffer dùng chung.
        fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
            self.bytes.lock().unwrap().extend_from_slice(buffer);
            Ok(buffer.len())
        }

        /// Không cần flush vì buffer nằm hoàn toàn trong bộ nhớ.
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl<'writer> MakeWriter<'writer> for SharedBuffer {
        type Writer = SharedBufferGuard;

        /// Tạo writer mới cùng trỏ vào buffer tracing của test.
        fn make_writer(&'writer self) -> Self::Writer {
            SharedBufferGuard {
                bytes: self.bytes.clone(),
            }
        }
    }

    /// Nội dung cố định phải cho đúng digest SHA-256 đã biết trước.
    #[test]
    fn hashes_known_content() {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all(b"medilab").unwrap();
        file.flush().unwrap();
        let digest = sha256_file(file.path()).unwrap();
        assert_eq!(
            digest,
            "8e90ca372e4826b2fb9d1cf50abce258b6c0e0e2656f429db8adf6e64af95240"
        );
    }

    /// Span hash chỉ được chứa số byte, không được làm lộ tên tệp hay nội dung tệp.
    #[test]
    fn hash_span_records_only_safe_file_metadata() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("private-patient-result.bin");
        std::fs::write(&path, b"sensitive-file-content").unwrap();
        let bytes = Arc::new(Mutex::new(Vec::new()));
        let writer = SharedBuffer {
            bytes: bytes.clone(),
        };
        let subscriber = tracing_subscriber::fmt()
            .with_ansi(false)
            .with_max_level(tracing::Level::TRACE)
            .with_span_events(FmtSpan::NEW | FmtSpan::CLOSE)
            .with_writer(writer)
            .finish();

        // Dùng subscriber toàn cục để callsite không bị vô hiệu hóa bởi test hash chạy song song.
        tracing::subscriber::set_global_default(subscriber).unwrap();
        sha256_file(&path).unwrap();

        let output = String::from_utf8(bytes.lock().unwrap().clone()).unwrap();
        assert!(output.contains("sync.sha256_file"));
        assert!(output.contains("byte_count=22"));
        assert!(!output.contains("private-patient-result.bin"));
        assert!(!output.contains("sensitive-file-content"));
    }

    /// Tệp không đổi trong lúc chờ ngắn phải được coi là ổn định.
    #[test]
    fn stable_file_after_short_wait() {
        let mut file = NamedTempFile::new().unwrap();
        file.write_all(b"stable").unwrap();
        file.flush().unwrap();
        assert!(is_stable(file.path(), Duration::from_millis(20)));
    }
}
