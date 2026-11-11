//! Test-signed updater transport and isolated executable fixtures, not published installers.
#![cfg(target_os = "linux")]
use base64::Engine;
use std::io::Cursor;
use tauri_plugin_updater::UpdaterExt;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

async fn server(
    response: impl Fn(&str) -> (u16, Vec<u8>) + Send + 'static,
    requests: usize,
) -> (String, tokio::task::JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move {
        for _ in 0..requests {
            let (socket, _) = listener.accept().await.unwrap();
            let mut socket = BufReader::new(socket);
            let mut request = String::new();
            socket.read_line(&mut request).await.unwrap();
            let mut headers = String::new();
            loop {
                let mut line = String::new();
                socket.read_line(&mut line).await.unwrap();
                if line == "\r\n" {
                    break;
                }
                headers.push_str(&line.to_ascii_lowercase());
            }
            assert!(!headers.contains("authorization:"));
            assert!(!headers.contains("x-sync-device-id:"));
            assert!(headers.contains(concat!(
                "user-agent: medilab-sync/",
                env!("CARGO_PKG_VERSION")
            )));
            let path = request.split_whitespace().nth(1).unwrap();
            let (status, body) = response(path);
            socket.get_mut().write_all(format!("HTTP/1.1 {status} Fixture\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\nContent-Length: {}\r\n\r\n", body.len()).as_bytes()).await.unwrap();
            socket.get_mut().write_all(&body).await.unwrap();
        }
    });
    (base, task)
}

#[tokio::test]
async fn unavailable_signing_key_refusal_exposes_safe_manual_download_without_touching_files() {
    let dir = tempfile::tempdir().unwrap();
    let data = dir.path().join("queued.docx");
    std::fs::write(&data, b"pending instrument result").unwrap();
    let (base, task) = server(|path| {
        assert_eq!(path, "/api/sync/v1/updates/linux/x86_64/0.1.0");
        (410, br#"{"error":{"code":"client_update_required","message":"Install the current release","download_url":"https://lims.example/download/sync.deb"}}"#.to_vec())
    }, 1).await;
    let notice = crate::client_migration::updater_requirement(
        &base,
        &format!("{base}/api/sync/v1/updates/linux/x86_64/0.1.0"),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(
        notice.download_url.as_deref(),
        Some("https://lims.example/download/sync.deb")
    );
    assert_eq!(crate::client_migration::required(&base), Some(notice));
    assert_eq!(std::fs::read(&data).unwrap(), b"pending instrument result");
    task.await.unwrap();
    crate::client_migration::clear(&base);
}

async fn signed_download(
    trusted_key: &minisign::PublicKey,
    signer: &minisign::KeyPair,
    corrupt: bool,
    executable: &std::path::Path,
) -> Result<tauri_plugin_updater::Update, tauri_plugin_updater::Error> {
    let payload = b"#!/bin/sh\nprintf 'fixture-new-version'\n";
    let signature = minisign::sign(
        Some(&signer.pk),
        &signer.sk,
        Cursor::new(payload),
        Some("fixture only"),
        None,
    )
    .unwrap()
    .to_string();
    let pubkey =
        base64::engine::general_purpose::STANDARD.encode(trusted_key.to_box().unwrap().to_string());
    let signature = base64::engine::general_purpose::STANDARD.encode(signature);
    let download_base = std::sync::Arc::new(parking_lot::Mutex::new(String::new()));
    let response_base = download_base.clone();
    let (base, task) = server(move |path| {
        match path {
            "/api/sync/v1/updates/linux/x86_64/0.1.0" => (200, serde_json::to_vec(&serde_json::json!({"version":"0.2.0","url":format!("{}/package",response_base.lock()),"signature":signature,"notes":"test signed fixture"})).unwrap()),
            "/package" => (200, if corrupt { b"tampered fixture".to_vec() } else {payload.to_vec()}),
            _=>panic!("unexpected fixture request {path}"),
        }
    }, 3).await;
    *download_base.lock() = base.clone();
    let mut context = tauri::test::mock_context(tauri::test::noop_assets());
    context
        .config_mut()
        .plugins
        .0
        .insert("updater".into(), serde_json::json!({"pubkey":pubkey}));
    let app = tauri::test::mock_builder()
        .plugin(tauri_plugin_updater::Builder::new().pubkey(pubkey).build())
        .build(context)
        .unwrap();
    let updater = app
        .updater_builder()
        .executable_path(executable)
        .no_proxy()
        .header(
            "User-Agent",
            concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")),
        )
        .unwrap()
        .endpoints(vec![format!(
            "{base}/api/sync/v1/updates/linux/x86_64/0.1.0"
        )
        .parse()
        .unwrap()])
        .unwrap()
        .build()
        .unwrap();
    assert!(crate::client_migration::updater_requirement(
        &base,
        &format!("{base}/api/sync/v1/updates/linux/x86_64/0.1.0")
    )
    .await
    .unwrap()
    .is_none());
    let update = updater.check().await.unwrap().unwrap();
    let bytes = update.download(|_, _| {}, || {}).await;
    task.await.unwrap();
    let bytes = bytes?;
    update.install(bytes)?;
    Ok(update)
}

#[tokio::test]
async fn existing_test_signing_key_installs_and_wrong_key_or_tampering_preserves_the_fixture() {
    use std::os::unix::fs::PermissionsExt;
    let signer = minisign::KeyPair::generate_unencrypted_keypair().unwrap();
    let other = minisign::KeyPair::generate_unencrypted_keypair().unwrap();
    for (key, corrupt, success) in [
        (&signer.pk, false, true),
        (&other.pk, false, false),
        (&signer.pk, true, false),
    ] {
        let dir = tempfile::tempdir().unwrap();
        let executable = dir.path().join("Sync.AppImage");
        let local = dir.path().join("result.docx");
        std::fs::write(&local, b"queued").unwrap();
        let database = crate::migration_tests::legacy_database(dir.path());
        let original_database = std::fs::read(&database).unwrap();
        std::fs::write(&executable, b"legacy fixture executable").unwrap();
        std::fs::set_permissions(&executable, std::fs::Permissions::from_mode(0o755)).unwrap();
        let result = signed_download(key, &signer, corrupt, &executable).await;
        assert_eq!(result.is_ok(), success);
        assert_eq!(std::fs::read(&local).unwrap(), b"queued");
        assert_eq!(std::fs::read(&database).unwrap(), original_database);
        if success {
            let output = tokio::process::Command::new(&executable)
                .output()
                .await
                .unwrap();
            assert!(output.status.success());
            assert_eq!(output.stdout, b"fixture-new-version");
            let db = crate::storage::Db::open(&database).unwrap();
            db.migrate_laboratory_api().unwrap();
            assert_eq!(db.list_jobs().unwrap().len(), 1);
            assert!(db.next_job().unwrap().is_none());
            assert_eq!(
                db.meta_get("client_uid").unwrap().as_deref(),
                Some("installed-legacy-uid")
            );
        } else {
            assert_eq!(
                std::fs::read(&executable).unwrap(),
                b"legacy fixture executable"
            );
        }
    }
}

#[tokio::test]
#[ignore = "requires owned Odoo release catalog and MEDILAB_E2E_RELEASES_FILE"]
async fn live_odoo_catalog_and_tauri_verifier_preserve_state_on_bad_downloads() {
    use std::os::unix::fs::PermissionsExt;
    let base = std::env::var("MEDILAB_E2E_URL").unwrap();
    let catalog = std::env::var("MEDILAB_E2E_RELEASES_FILE").unwrap();
    let signer = minisign::KeyPair::generate_unencrypted_keypair().unwrap();
    let other = minisign::KeyPair::generate_unencrypted_keypair().unwrap();
    let payload = b"#!/bin/sh\nprintf 'verified-live-fixture'\n";
    let signature = minisign::sign(
        Some(&signer.pk),
        &signer.sk,
        Cursor::new(payload),
        Some("isolated fixture"),
        None,
    )
    .unwrap()
    .to_string();
    let signature = base64::engine::general_purpose::STANDARD.encode(signature);
    let mode = std::sync::Arc::new(std::sync::atomic::AtomicU8::new(0));
    let serving_mode = mode.clone();
    let (artifact, server) = server(
        move |path| {
            assert_eq!(path, "/package");
            match serving_mode.load(std::sync::atomic::Ordering::SeqCst) {
                1 => (200, b"tampered bytes".to_vec()),
                2 => (404, b"unavailable".to_vec()),
                _ => (200, payload.to_vec()),
            }
        },
        4,
    )
    .await;
    let releases: Vec<_> = ["current", "legacy"]
        .into_iter()
        .map(|trust| {
            serde_json::json!({
                "target":"linux", "arch":"x86_64", "channel":"stable", "trust":trust,
                "version":"0.2.0", "url":format!("{artifact}/package"), "signature":signature,
            })
        })
        .collect();
    std::fs::write(
        &catalog,
        serde_json::to_vec(&serde_json::json!({"releases":releases})).unwrap(),
    )
    .unwrap();
    for (key, mode_value, success) in [
        (&signer.pk, 0, true),
        (&other.pk, 0, false),
        (&signer.pk, 1, false),
        (&signer.pk, 2, false),
    ] {
        mode.store(mode_value, std::sync::atomic::Ordering::SeqCst);
        let dir = tempfile::tempdir().unwrap();
        let executable = dir.path().join("Sync.AppImage");
        let local = dir.path().join("queued.docx");
        std::fs::write(&executable, b"old fixture executable").unwrap();
        std::fs::set_permissions(&executable, std::fs::Permissions::from_mode(0o755)).unwrap();
        std::fs::write(&local, b"preserved pending bytes").unwrap();
        let database = crate::migration_tests::legacy_database(dir.path());
        let original_database = std::fs::read(&database).unwrap();
        let pubkey =
            base64::engine::general_purpose::STANDARD.encode(key.to_box().unwrap().to_string());
        let mut context = tauri::test::mock_context(tauri::test::noop_assets());
        context
            .config_mut()
            .plugins
            .0
            .insert("updater".into(), serde_json::json!({"pubkey":pubkey}));
        let app = tauri::test::mock_builder()
            .plugin(tauri_plugin_updater::Builder::new().pubkey(pubkey).build())
            .build(context)
            .unwrap();
        let prefix = if success {
            "medilab/api/v1"
        } else {
            "api/sync/v1"
        };
        let endpoint = format!("{base}/{prefix}/updates/linux/x86_64/0.1.0");
        assert!(
            crate::client_migration::updater_requirement(&base, &endpoint)
                .await
                .unwrap()
                .is_none()
        );
        let updater = app
            .updater_builder()
            .executable_path(&executable)
            .no_proxy()
            .header(
                "User-Agent",
                concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")),
            )
            .unwrap()
            .endpoints(vec![endpoint.parse().unwrap()])
            .unwrap()
            .build()
            .unwrap();
        let update = updater.check().await.unwrap().unwrap();
        let result = match update.download(|_, _| {}, || {}).await {
            Ok(bytes) => update.install(bytes),
            Err(error) => Err(error),
        };
        assert_eq!(result.is_ok(), success);
        assert_eq!(std::fs::read(&database).unwrap(), original_database);
        assert_eq!(std::fs::read(&local).unwrap(), b"preserved pending bytes");
        if success {
            assert_eq!(
                tokio::process::Command::new(&executable)
                    .output()
                    .await
                    .unwrap()
                    .stdout,
                b"verified-live-fixture"
            );
        } else {
            assert_eq!(
                std::fs::read(&executable).unwrap(),
                b"old fixture executable"
            );
        }
    }
    server.await.unwrap();
    let notice =
        crate::client_migration::updater_requirement(&base, &format!("{base}/api/sync/v1/folders"))
            .await
            .unwrap()
            .unwrap();
    assert!(notice.download_url.is_some());
    crate::client_migration::clear(&base);
    std::fs::write(catalog, br#"{"releases":[]}"#).unwrap();
}
