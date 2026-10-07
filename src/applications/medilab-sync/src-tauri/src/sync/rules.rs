use serde::{Deserialize, Serialize};
use std::path::{Component, Path};

/// Một rule đặt tên/lọc tệp áp cho một folder, cấu hình trong Odoo (khớp phần mở rộng, tiền
/// tố, hoặc glob).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncRule {
    pub kind: String,
    pub pattern: String,
    pub recursive: bool,
    pub enabled: bool,
}

/// True nếu tệp là tệp tạm/lock của ứng dụng văn phòng (`~$`, `.tmp`, `.sbx`, `.~`), không bao
/// giờ đồng bộ.
pub fn is_ignored(relative: &str) -> bool {
    let name = Path::new(relative)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(relative);
    name.starts_with("~$")
        || name.ends_with(".tmp")
        || name.ends_with(".sbx")
        || name.starts_with(".~")
}

/// Kiểm một đường dẫn tương đối có khớp rule đặt tên/lọc của folder hay không (bỏ qua tệp tạm,
/// tôn trọng cờ đệ quy; không rule nào bật thì khớp mặc định).
///
/// Luật nghiệp vụ: docs/business/file-sync-governance.md#what-a-file-belongs-to
pub fn matches_rules(relative: &str, recursive: bool, rules: &[SyncRule]) -> bool {
    if is_ignored(relative) {
        return false;
    }
    let path = Path::new(relative);
    if !recursive && path.components().count() > 1 {
        return false;
    }
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(relative);
    let enabled: Vec<_> = rules.iter().filter(|rule| rule.enabled).collect();
    if enabled.is_empty() {
        return true;
    }
    enabled.iter().any(|rule| match rule.kind.as_str() {
        "prefix" => name.starts_with(&rule.pattern),
        "extension" => {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let expected = rule.pattern.trim_start_matches('.');
            ext.eq_ignore_ascii_case(expected)
        }
        "glob" => glob::Pattern::new(&rule.pattern)
            .map(|pattern| pattern.matches(name) || pattern.matches(relative))
            .unwrap_or(false),
        _ => false,
    })
}

/// Đường dẫn tương đối (dùng `/`) của `file` so với `root`; `None` nếu không nằm dưới root hoặc
/// chứa `..` (traversal).
pub fn relative_path(root: &Path, file: &Path) -> Option<String> {
    let rel = file.strip_prefix(root).ok()?;
    if rel.components().any(|c| matches!(c, Component::ParentDir)) {
        return None;
    }
    Some(rel.to_string_lossy().replace('\\', "/"))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Dựng nhanh một rule đã bật, đệ quy, cho test.
    fn rule(kind: &str, pattern: &str) -> SyncRule {
        SyncRule {
            kind: kind.into(),
            pattern: pattern.into(),
            recursive: true,
            enabled: true,
        }
    }

    /// Rule glob phải khớp đúng mẫu và không bao giờ khớp tệp tạm/lock.
    #[test]
    fn glob_prefix_and_ignore() {
        let rules = vec![rule("glob", "ABC*")];
        assert!(matches_rules("ABC_001.xlsx", true, &rules));
        assert!(matches_rules("ABC_RESULT.pdf", true, &rules));
        assert!(!matches_rules("XYZ_001.xlsx", true, &rules));
        assert!(!matches_rules("~$ABC.xlsx", true, &rules));
    }

    /// Nhiều rule bật cùng lúc phải khớp theo kiểu OR (khớp bất kỳ rule nào là đủ).
    #[test]
    fn extension_and_prefix() {
        let rules = vec![rule("extension", "xlsx"), rule("prefix", "ABC")];
        assert!(matches_rules("ABC_001.xlsx", true, &rules));
        assert!(matches_rules("ABC_001.docx", true, &rules));
        assert!(matches_rules("other.xlsx", true, &rules));
        assert!(!matches_rules("other.docx", true, &rules));
    }
}
