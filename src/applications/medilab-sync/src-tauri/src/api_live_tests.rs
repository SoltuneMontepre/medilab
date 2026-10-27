use crate::api::{ApiClient, RuleDto};
use crate::error::AppError;
use sha2::{Digest, Sha256};

#[tokio::test]
#[ignore = "requires the owned released-page fixture and MEDILAB_E2E_EDITOR_* variables"]
async fn live_editor_save_is_visible_to_desktop_client() {
    let base = std::env::var("MEDILAB_E2E_URL").unwrap();
    let folder = std::env::var("MEDILAB_E2E_EDITOR_FOLDER")
        .unwrap()
        .parse()
        .unwrap();
    let file = std::env::var("MEDILAB_E2E_EDITOR_FILE")
        .unwrap()
        .parse()
        .unwrap();
    let expected = std::env::var("MEDILAB_E2E_EDITOR_SHA256").unwrap();
    let signed = ApiClient::login(
        &base,
        &std::env::var("MEDILAB_E2E_LOGIN").unwrap(),
        &std::env::var("MEDILAB_E2E_PASSWORD").unwrap(),
        "editor-acceptance",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uuid::Uuid::new_v4().to_string(),
    )
    .await
    .unwrap();
    let client = ApiClient::new(&base, &signed.api_key, signed.device_id).unwrap();
    let current = client
        .get_file(folder, file)
        .await
        .unwrap()
        .current_version
        .unwrap();
    assert_eq!(current.content_hash, expected);
    assert_eq!(current.source, "edited_online");
    let versions = client.get_file_versions(folder, file, 20, 0).await.unwrap();
    assert_eq!(versions.total, 2);
    assert_eq!(
        versions
            .items
            .iter()
            .filter(|v| v.content_hash == expected)
            .count(),
        1
    );
    let download = client
        .authorize_download(folder, file, current.id)
        .await
        .unwrap();
    let mut transport = reqwest::Client::builder().redirect(reqwest::redirect::Policy::none());
    if let Ok(path) = std::env::var("MEDILAB_E2E_EDITOR_CA") {
        let url = reqwest::Url::parse(&download.url).unwrap();
        assert_eq!(url.scheme(), "https");
        assert_eq!(url.host_str(), Some("localhost"));
        assert_eq!(url.port(), Some(3900));
        let certificate = reqwest::Certificate::from_pem(&std::fs::read(path).unwrap()).unwrap();
        transport = transport.add_root_certificate(certificate);
    }
    let bytes = transport
        .build()
        .unwrap()
        .get(download.url)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .bytes()
        .await
        .unwrap();
    assert_eq!(hex::encode(Sha256::digest(&bytes)), expected);
    client.revoke_device(signed.device_id).await.unwrap();
}

async fn finish(client: &ApiClient, folder: i64, upload: i64) -> crate::api::FinalizeResponse {
    for _ in 0..8 {
        match client.finalize(folder, upload, &[]).await {
            Ok(result) => return result,
            Err(AppError::UploadPending) => {}
            Err(err) => panic!("upload failed: {err}"),
        }
    }
    panic!("verification did not finish within the live-test budget");
}

#[tokio::test]
#[ignore = "requires an isolated Odoo/Garage stack and MEDILAB_E2E_* variables"]
async fn live_api_auth_members_history_restore_conflict_and_revocation() {
    let base = std::env::var("MEDILAB_E2E_URL").unwrap();
    let login = std::env::var("MEDILAB_E2E_LOGIN").unwrap();
    let password = std::env::var("MEDILAB_E2E_PASSWORD").unwrap();
    let uid = uuid::Uuid::new_v4().to_string();
    let signed = ApiClient::login(
        &base,
        &login,
        &password,
        "api-contract-test",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uid,
    )
    .await
    .unwrap();
    let client = ApiClient::new(&base, &signed.api_key, signed.device_id).unwrap();
    client.me().await.unwrap();
    assert!(client
        .devices()
        .await
        .unwrap()
        .iter()
        .any(|d| d.id == signed.device_id && d.current));
    let root = format!("api-contract-{}", uuid::Uuid::new_v4());
    let folder = client
        .create_folder(
            &root,
            &root,
            &[RuleDto {
                id: None,
                r#type: "extension".into(),
                pattern: "txt".into(),
                recursive: true,
                enabled: true,
            }],
        )
        .await
        .unwrap();
    assert_eq!(folder.logical_root, root);
    assert_eq!(folder.rules[0].r#type, "extension");
    let members = client.list_members(folder.id).await.unwrap();
    assert_eq!(members.my_role, "owner");
    let candidates = client
        .search_member_candidates(folder.id, "tester")
        .await
        .unwrap();
    let candidate = candidates
        .first()
        .expect("isolated demo needs another tester");
    let member = client.add_member(folder.id, candidate.id).await.unwrap();
    assert_eq!(member.role, "member");
    client.remove_member(folder.id, member.id).await.unwrap();
    let digest = hex::encode(Sha256::digest(b""));
    let key = uuid::Uuid::new_v4().to_string();
    let first = client
        .prepare(folder.id, "Empty.txt", 0, &digest, 0, &key)
        .await
        .unwrap();
    let repeated = client
        .prepare(folder.id, "Empty.txt", 0, &digest, 0, &key)
        .await
        .unwrap();
    assert_eq!(first.id, repeated.id);
    let stored = finish(&client, folder.id, first.id).await;
    let repeated = finish(&client, folder.id, first.id).await;
    assert_eq!(stored.version_id, repeated.version_id);
    let file = client.get_file(folder.id, stored.file_id).await.unwrap();
    let initial = file.current_version.unwrap();
    let history = client
        .get_file_versions(folder.id, file.id, 20, 0)
        .await
        .unwrap();
    assert_eq!(history.total, 1);
    let restored = client
        .restore_file_version(folder.id, file.id, initial.id)
        .await
        .unwrap();
    assert!(restored.version_number > initial.version_number);
    let detail = client
        .get_file_version(folder.id, file.id, initial.id)
        .await
        .unwrap();
    assert!(!detail.is_canonical);
    assert!(detail.can_restore);
    let download = client
        .authorize_download(folder.id, file.id, restored.id)
        .await
        .unwrap();
    assert_eq!(download.content_hash, digest);
    assert!(reqwest::get(download.url)
        .await
        .unwrap()
        .bytes()
        .await
        .unwrap()
        .is_empty());
    let content = bytes::Bytes::from_static(b"competing bytes");
    let hash = hex::encode(Sha256::digest(&content));
    let upload = client
        .prepare(
            folder.id,
            "empty.TXT",
            content.len() as i64,
            &hash,
            initial.id,
            &uuid::Uuid::new_v4().to_string(),
        )
        .await
        .unwrap();
    let part = client
        .presign(folder.id, upload.id, &[1])
        .await
        .unwrap()
        .remove(0);
    ApiClient::put_part(&part.url, content).await.unwrap();
    let conflict = finish(&client, folder.id, upload.id).await;
    assert_eq!(conflict.status, "conflict");
    assert_eq!(conflict.server_version_id, Some(restored.id));
    let history = client
        .get_file_versions(folder.id, file.id, 20, 0)
        .await
        .unwrap();
    assert_eq!(history.total, 3);
    assert!(history
        .items
        .iter()
        .any(|v| v.source == "conflict" && !v.is_canonical));
    let changes = client.folder_changes(folder.id, 0, 100).await.unwrap();
    assert!(changes.changes.len() >= 2);
    client.revoke_device(signed.device_id).await.unwrap();
    assert!(matches!(client.me().await, Err(AppError::Unauthenticated)));
    let revoked = ApiClient::login(
        &base,
        &login,
        &password,
        "api-contract-test",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uid,
    )
    .await;
    assert!(matches!(revoked, Err(AppError::Unauthenticated)));
    let second = ApiClient::login(
        &base,
        &login,
        &password,
        "api-contract-logout",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uuid::Uuid::new_v4().to_string(),
    )
    .await
    .unwrap();
    let second = ApiClient::new(&base, &second.api_key, second.device_id).unwrap();
    second.logout().await.unwrap();
    second.logout().await.unwrap();
}
