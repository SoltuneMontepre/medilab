use crate::server_url::endpoint;
use tauri_plugin_opener::OpenerExt;

pub fn open_editor<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    base: &str,
    file_id: i64,
) -> Result<(), String> {
    open_editor_with(base, file_id, |url| {
        app.opener()
            .open_url(url, None::<&str>)
            .map_err(|_| "Không mở được trình duyệt. Vui lòng thử lại.".to_string())
    })
}

pub fn open_editor_with(
    base: &str,
    file_id: i64,
    open: impl FnOnce(&str) -> Result<(), String>,
) -> Result<(), String> {
    if file_id <= 0 {
        return Err("Thiếu mã tệp trên máy chủ".into());
    }
    let url = endpoint(base, &format!("medilab/laboratory-files/{file_id}/edit"))?;
    open(url.as_str())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_browser_handoff_preserves_base_path_and_has_no_credentials() {
        for (base, expected) in [
            (
                "https://lims.example",
                "https://lims.example/medilab/laboratory-files/42/edit",
            ),
            (
                "http://localhost:8069/odoo/",
                "http://localhost:8069/odoo/medilab/laboratory-files/42/edit",
            ),
        ] {
            open_editor_with(base, 42, |url| {
                assert_eq!(url, expected);
                Ok(())
            })
            .unwrap();
        }
    }

    #[test]
    fn refuses_unsafe_origins_and_file_ids_before_launch() {
        for base in [
            "file:///tmp",
            "javascript:alert(1)",
            "https://user:key@lims.example",
            "https://@lims.example",
            "https://lims.example/%0a",
            "https://lims.example/%3fkey=secret",
            "https://lims.example?key=secret",
            "https://lims.example/#jwt",
            "//lims.example",
            "https://lims.example/../other",
            "https://lims.example/%2e%2e/other",
            "https://lims.example/a%2fb",
            "https://lims.example/a\\b",
            "https://lims.example/\n",
        ] {
            assert!(
                open_editor_with(base, 1, |_| panic!("must not launch")).is_err(),
                "{base}"
            );
        }
        for id in [0, -1, i64::MIN] {
            assert!(
                open_editor_with("https://lims.example", id, |_| panic!("must not launch"))
                    .is_err()
            );
        }
    }

    #[test]
    fn launch_failure_is_visible_and_can_be_retried() {
        assert_eq!(
            open_editor_with("https://lims.example", 1, |_| Err("launch failed".into())),
            Err("launch failed".into())
        );
        open_editor_with("https://lims.example", 1, |_| Ok(())).unwrap();
    }
}
