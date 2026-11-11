#![cfg(target_os = "linux")]
use std::process::Command;

#[test]
#[ignore = "invoked by the launcher test in an isolated subprocess"]
fn default_browser_plugin_worker() {
    let app = tauri::test::mock_builder()
        .plugin(tauri_plugin_opener::init())
        .build(tauri::test::mock_context(tauri::test::noop_assets()))
        .unwrap();
    let result = crate::browser::open_editor(app.handle(), "https://lims.example/odoo", 42);
    assert_eq!(
        result.is_err(),
        std::env::var_os("MEDILAB_OPENER_EXPECT_FAILURE").is_some()
    );
}

#[test]
fn linux_default_launcher_receives_only_the_editor_url_and_missing_launcher_is_reported() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let launcher = dir.path().join("xdg-open");
    let captured = dir.path().join("arguments");
    std::fs::write(
        &launcher,
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$MEDILAB_OPENER_OUTPUT\"\n",
    )
    .unwrap();
    std::fs::set_permissions(&launcher, std::fs::Permissions::from_mode(0o755)).unwrap();
    for failure in [false, true, false] {
        if failure {
            std::fs::remove_file(&launcher).unwrap();
        } else if !launcher.exists() {
            std::fs::write(
                &launcher,
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$MEDILAB_OPENER_OUTPUT\"\n",
            )
            .unwrap();
            std::fs::set_permissions(&launcher, std::fs::Permissions::from_mode(0o755)).unwrap();
        }
        let mut child = Command::new(std::env::current_exe().unwrap());
        child
            .args([
                "--ignored",
                "--exact",
                "browser_linux_tests::default_browser_plugin_worker",
            ])
            .env("PATH", dir.path())
            .env("MEDILAB_OPENER_OUTPUT", &captured);
        if failure {
            child.env("MEDILAB_OPENER_EXPECT_FAILURE", "1");
        } else {
            child.env_remove("MEDILAB_OPENER_EXPECT_FAILURE");
        }
        let output = child.output().unwrap();
        assert!(
            output.status.success(),
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        if !failure {
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
            while !captured.exists() && std::time::Instant::now() < deadline {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
            assert_eq!(
                std::fs::read_to_string(&captured).unwrap(),
                "https://lims.example/odoo/medilab/laboratory-files/42/edit\n"
            );
            std::fs::remove_file(&captured).unwrap();
        }
    }
}
