use std::ffi::OsString;
use std::io::{Error, ErrorKind, Result};
use std::path::{Path, PathBuf};

/// Tên chưa có trong `dest`: giữ nguyên tên, hoặc thêm ` (2)`, ` (3)`... trước phần mở rộng như
/// trình quản lý tệp, để không ghi đè tệp đang đồng bộ.
fn free_name(dest: &Path, source: &Path) -> Option<PathBuf> {
    let name = source.file_name()?;
    if !dest.join(name).exists() {
        return Some(dest.join(name));
    }
    let stem = source.file_stem().unwrap_or(name).to_string_lossy();
    let ext = source
        .extension()
        .map(|ext| format!(".{}", ext.to_string_lossy()))
        .unwrap_or_default();
    (2..)
        .map(|n| dest.join(OsString::from(format!("{stem} ({n}){ext}"))))
        .find(|candidate| !candidate.exists())
}

/// Chép một tệp, hoặc cả cây thư mục, sang `target`. Bỏ qua liên kết tượng trưng.
fn copy_tree(source: &Path, target: &Path) -> Result<()> {
    let kind = std::fs::symlink_metadata(source)?.file_type();
    if kind.is_dir() {
        std::fs::create_dir(target)?;
        for entry in std::fs::read_dir(source)? {
            let entry = entry?;
            copy_tree(&entry.path(), &target.join(entry.file_name()))?;
        }
    } else if kind.is_file() {
        std::fs::copy(source, target)?;
    }
    Ok(())
}

/// Chép các tệp và thư mục được kéo-thả vào thư mục đồng bộ `dest`, trả về số mục đã chép. Từ chối
/// chép một thư mục vào chính nó hoặc vào thư mục con của nó.
pub fn copy_into(dest: &Path, sources: &[PathBuf]) -> Result<usize> {
    let dest = dest.canonicalize()?;
    for source in sources {
        if dest.starts_with(source.canonicalize()?) {
            return Err(Error::new(
                ErrorKind::InvalidInput,
                "Không chép được một thư mục vào chính nó",
            ));
        }
    }
    let mut copied = 0;
    for source in sources {
        let Some(target) = free_name(&dest, source) else {
            continue;
        };
        copy_tree(source, &target)?;
        copied += 1;
    }
    Ok(copied)
}

#[cfg(test)]
mod tests {
    use super::copy_into;
    use std::fs;

    #[test]
    fn copies_files_and_folders_without_overwriting() {
        let root = tempfile::tempdir().unwrap();
        let dest = root.path().join("Results");
        let src = root.path().join("src");
        fs::create_dir_all(src.join("run/sub")).unwrap();
        fs::create_dir(&dest).unwrap();
        fs::write(src.join("a.csv"), "new").unwrap();
        fs::write(src.join("run/sub/b.txt"), "b").unwrap();
        fs::write(dest.join("a.csv"), "old").unwrap();

        let copied = copy_into(&dest, &[src.join("a.csv"), src.join("run")]).unwrap();

        assert_eq!(copied, 2);
        assert_eq!(fs::read_to_string(dest.join("a.csv")).unwrap(), "old");
        assert_eq!(fs::read_to_string(dest.join("a (2).csv")).unwrap(), "new");
        assert_eq!(fs::read_to_string(dest.join("run/sub/b.txt")).unwrap(), "b");
    }

    #[test]
    fn refuses_to_copy_a_folder_into_itself() {
        let root = tempfile::tempdir().unwrap();
        let dest = root.path().join("Results");
        fs::create_dir(&dest).unwrap();
        assert!(copy_into(&dest, &[root.path().to_path_buf()]).is_err());
        assert!(fs::read_dir(&dest).unwrap().next().is_none());
    }
}
