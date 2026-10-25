use crate::error::AppError;
use crate::storage::Db;

#[test]
fn installed_database_migration_preserves_files_queue_and_installation_identity() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("queue.sqlite");
    let local = dir.path().join("instrument");
    std::fs::create_dir(&local).unwrap();
    std::fs::write(local.join("result.docx"), b"queued instrument bytes").unwrap();
    let db = Db::open(&path).unwrap();
    db.meta_set("client_uid", "existing-installation").unwrap();
    db.meta_set("user_login", "tester").unwrap();
    let folder = db
        .upsert_folder(local.to_str().unwrap(), "Existing", Some(77), true, &[])
        .unwrap();
    let file = db
        .upsert_file(folder, "result.docx", 23, 1, "oldhash")
        .unwrap();
    db.enqueue_upload(folder, file, "result.docx", 23, Some(12), Some(8))
        .unwrap();
    let job = db.next_job().unwrap().unwrap();
    db.save_job_session(job.id, 9, r#"[[1,"etag"]]"#, "oldhash", Some(16))
        .unwrap();
    db.migrate_laboratory_api().unwrap();
    assert_eq!(
        db.meta_get("client_uid").unwrap().as_deref(),
        Some("existing-installation")
    );
    assert_eq!(
        db.meta_get("legacy_folder:1").unwrap().as_deref(),
        Some("77")
    );
    let binding = &db.list_folders().unwrap()[0];
    assert_eq!(binding.local_path, local.to_str().unwrap());
    assert_eq!(binding.remote_id, None);
    assert_eq!(binding.access_state, "unbound");
    assert!(
        db.next_job().unwrap().is_none(),
        "unbound queue must not be claimed"
    );
    assert_eq!(db.list_jobs().unwrap().len(), 1);
    assert_eq!(
        std::fs::read(local.join("result.docx")).unwrap(),
        b"queued instrument bytes"
    );
    db.upsert_folder(local.to_str().unwrap(), "New", Some(81), true, &[])
        .unwrap();
    db.set_folder_access_state(folder, "ok").unwrap();
    db.migrate_laboratory_api().unwrap();
    let next = db.next_job().unwrap().unwrap();
    assert_eq!(next.id, job.id);
    assert_eq!(next.session_id, None);
    assert_eq!(db.list_folders().unwrap()[0].remote_id, Some(81));
    drop(db);
    let reopened = Db::open(&path).unwrap();
    assert_eq!(reopened.list_folders().unwrap()[0].remote_id, Some(81));
}

#[test]
fn retry_after_is_respected_and_pending_verification_does_not_become_an_auth_failure() {
    let error = AppError::Api {
        status: 429,
        code: "too_many_attempts".into(),
        message: "wait".into(),
        retry_after: Some(61),
    };
    let retry = crate::sync::retry::next_status(&error, 1, true, 1000);
    assert_eq!(retry.retry_at, Some(1061));
    assert!(!crate::error::is_odoo_auth_failure(
        &AppError::UploadPending
    ));
}

#[test]
fn manual_update_refusal_preserves_the_gateway_download_message() {
    let body = r#"{"error":{"code":"client_update_required","message":"Install https://lims.example/download/sync"}}"#;
    let error = crate::api::map_http_error(410, body);
    assert!(matches!(error, AppError::ClientUpdateRequired(_)));
    assert!(error
        .to_string()
        .contains("https://lims.example/download/sync"));
    assert!(!crate::api::is_retryable(&error));
    assert!(!crate::error::is_odoo_auth_failure(&error));
}

#[tokio::test]
async fn upload_only_mode_preserves_local_bytes_and_blocks_download_claims() {
    let dir = tempfile::tempdir().unwrap();
    let db = Db::open(&dir.path().join("q.sqlite")).unwrap();
    let local = dir.path().join("instrument");
    std::fs::create_dir(&local).unwrap();
    std::fs::write(local.join("same.txt"), "instrument evidence").unwrap();
    let id = db
        .upsert_folder(local.to_str().unwrap(), "Instrument", Some(9), true, &[])
        .unwrap();
    let folder = db.list_folders().unwrap().remove(0);
    db.meta_set(&format!("folder_mode:{id}"), "upload_only")
        .unwrap();
    let change = crate::api::FolderChangeDto {
        id: 1,
        change_type: "CANONICAL_VERSION".into(),
        folder_id: 9,
        file_id: 99,
        logical_path: "same.txt".into(),
        current_version_id: Some(100),
        version_number: Some(1),
        content_hash: Some("a".repeat(64)),
        size: 10,
        source: Some("synced".into()),
        changed_at: None,
        changed_by_device_id: None,
    };
    let result = crate::sync::engine::plan_remote_change(&db, &folder, &change)
        .await
        .unwrap();
    assert_eq!(result, crate::sync::engine::RemoteOutcome::Skipped);
    assert!(db.list_jobs().unwrap().is_empty());
    assert_eq!(
        std::fs::read_to_string(local.join("same.txt")).unwrap(),
        "instrument evidence"
    );
    let file = db
        .ensure_remote_mapping(id, "other.txt", 99, Some(100))
        .unwrap();
    db.enqueue_download(id, file, "other.txt", 10, 99, 100, &"a".repeat(64), Some(1))
        .unwrap();
    assert!(db.next_job().unwrap().is_none());
    db.meta_set(&format!("folder_mode:{id}"), "two_way")
        .unwrap();
    assert!(db.next_job().unwrap().is_some());
}

#[test]
fn verification_wait_preserves_retry_budget_and_manual_failed_upload_retry_changes_identity() {
    let dir = tempfile::tempdir().unwrap();
    let db = Db::open(&dir.path().join("q.sqlite")).unwrap();
    let folder = db
        .upsert_folder(dir.path().to_str().unwrap(), "R", Some(1), true, &[])
        .unwrap();
    let file = db.upsert_file(folder, "a.txt", 1, 1, "hash").unwrap();
    db.enqueue_upload(folder, file, "a.txt", 1, None, None)
        .unwrap();
    let job = db.next_job().unwrap().unwrap();
    let owned = db.running_job(&job).unwrap().unwrap();
    let key = db
        .with_running_job(&owned, |conn| {
            crate::storage::prepare_key_on(conn, job.id, "fingerprint")
        })
        .unwrap()
        .unwrap();
    let decision =
        crate::sync::engine::record_job_failure(&db, &job, &owned, &AppError::UploadPending)
            .unwrap()
            .unwrap();
    assert_eq!(decision.status, "retry_wait");
    assert_eq!(db.list_jobs().unwrap()[0].attempt_count, 0);
    db.mark_job(
        job.id,
        "failed",
        Some("verification failed"),
        20,
        None,
        None,
        None,
    )
    .unwrap();
    db.save_job_session(job.id, 7, "[]", "hash", Some(16))
        .unwrap();
    db.retry_job(job.id).unwrap();
    let retried = db.next_job().unwrap().unwrap();
    assert_eq!(retried.session_id, None);
    let owned = db.running_job(&retried).unwrap().unwrap();
    let next = db
        .with_running_job(&owned, |conn| {
            crate::storage::prepare_key_on(conn, job.id, "fingerprint")
        })
        .unwrap()
        .unwrap();
    assert_ne!(next, key);
}

pub(crate) fn legacy_database(root: &std::path::Path) -> std::path::PathBuf {
    let path = root.join("sync.sqlite");
    let conn = rusqlite::Connection::open(&path).unwrap();
    conn.execute_batch(include_str!("../fixtures/legacy-schema.sql.fixture"))
        .unwrap();
    conn.execute("INSERT INTO sync_folder(id,local_path,remote_id,logical_root) VALUES(7,?1,77,'Instrument')",[root.to_str().unwrap()]).unwrap();
    conn.execute_batch("INSERT INTO sync_file(id,folder_id,relative_path,size,mtime,sha256,remote_file_id,remote_version_id) VALUES(11,7,'result.docx',6,1,'oldhash',9,8);
        INSERT INTO sync_job(id,folder_id,file_id,relative_path,status,attempt_count,bytes_total,session_id,uploaded_parts) VALUES(13,7,11,'result.docx','running',4,6,55,'[[1,\"etag\"]]');
        INSERT INTO app_meta(key,value) VALUES('client_uid','installed-legacy-uid');").unwrap();
    path
}

#[test]
fn reinstall_reopens_legacy_schema_preserves_queue_and_does_not_discard_valid_new_bindings() {
    let dir = tempfile::tempdir().unwrap();
    let local = dir.path().join("result.docx");
    std::fs::write(&local, b"queued").unwrap();
    let path = legacy_database(dir.path());
    {
        let db = Db::open(&path).unwrap();
        db.recover_jobs().unwrap();
        let pending = crate::sign_in_state::PendingSignIn::save(
            &db,
            "https://lims.example/base",
            "tester",
            1,
            "test-key",
        )
        .unwrap();
        pending.commit(&db).unwrap();
        assert_eq!(
            db.meta_get("client_uid").unwrap().as_deref(),
            Some("installed-legacy-uid")
        );
        assert!(db.next_job().unwrap().is_none());
        let job = &db.list_jobs().unwrap()[0];
        assert_eq!((job.id, job.attempt_count, job.session_id), (13, 4, None));
        assert_eq!(db.list_folders().unwrap()[0].access_state, "unbound");
        db.upsert_folder(
            dir.path().to_str().unwrap(),
            "New folder",
            Some(88),
            true,
            &[],
        )
        .unwrap();
        db.set_folder_access_state(7, "ok").unwrap();
    }
    // Reinstall/startup and reauthentication to the same account retain an approved new binding.
    let db = Db::open(&path).unwrap();
    crate::sign_in_state::PendingSignIn::save(
        &db,
        "https://LIMS.example:443/base/",
        "tester",
        2,
        "next-test-key",
    )
    .unwrap()
    .commit(&db)
    .unwrap();
    assert_eq!(db.list_folders().unwrap()[0].remote_id, Some(88));
    assert_eq!(db.next_job().unwrap().unwrap().id, 13);
    assert_eq!(std::fs::read(&local).unwrap(), b"queued");
}

#[test]
fn interrupted_migration_rolls_back_and_resumes_without_partial_rebinding_or_job_loss() {
    let dir = tempfile::tempdir().unwrap();
    let path = legacy_database(dir.path());
    let db = Db::open(&path).unwrap();
    let conn = rusqlite::Connection::open(&path).unwrap();
    conn.execute_batch("CREATE TRIGGER interrupt_migration BEFORE UPDATE ON sync_job BEGIN SELECT RAISE(ABORT,'fixture interruption'); END;").unwrap();
    assert!(db.migrate_laboratory_api().is_err());
    assert_eq!(db.list_folders().unwrap()[0].remote_id, Some(77));
    let session: Option<i64> = conn
        .query_row("SELECT session_id FROM sync_job WHERE id=13", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(session, Some(55));
    assert!(db.meta_get("laboratory_api_version").unwrap().is_none());
    assert!(db.meta_get("legacy_folder:7").unwrap().is_none());
    drop(db);
    conn.execute_batch("DROP TRIGGER interrupt_migration")
        .unwrap();
    let db = Db::open(&path).unwrap();
    db.migrate_laboratory_api().unwrap();
    assert_eq!(db.list_folders().unwrap()[0].remote_id, None);
    assert_eq!(db.list_jobs().unwrap().len(), 1);
    assert!(db.next_job().unwrap().is_none());
}

#[tokio::test]
#[ignore = "requires an isolated Odoo/Garage stack and MEDILAB_E2E_* variables"]
async fn live_reinstalled_legacy_state_reauthenticates_rebinds_and_uploads_preserved_bytes() {
    use crate::api::ApiClient;
    let base = std::env::var("MEDILAB_E2E_URL").unwrap();
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("result.docx"), b"queued").unwrap();
    let path = legacy_database(dir.path());
    let db = Db::open(&path).unwrap();
    let old = ApiClient::new(&base, "unissued-legacy-fixture-key", 55).unwrap();
    assert!(matches!(old.me().await, Err(AppError::Unauthenticated)));
    assert_eq!(db.list_jobs().unwrap().len(), 1);
    let login = std::env::var("MEDILAB_E2E_LOGIN").unwrap();
    let password = std::env::var("MEDILAB_E2E_PASSWORD").unwrap();
    let signed = ApiClient::login(
        &base,
        &login,
        &password,
        "migration-fixture",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uuid::Uuid::new_v4().to_string(),
    )
    .await
    .unwrap();
    crate::sign_in_state::PendingSignIn::save(
        &db,
        &base,
        &login,
        signed.device_id,
        &signed.api_key,
    )
    .unwrap()
    .commit(&db)
    .unwrap();
    assert!(db.next_job().unwrap().is_none());
    let client = ApiClient::new(&base, &signed.api_key, signed.device_id).unwrap();
    let root = format!("migration-fixture-{}", uuid::Uuid::new_v4());
    let folder = client.create_folder(&root, &root, &[]).await.unwrap();
    db.upsert_folder(
        dir.path().to_str().unwrap(),
        &root,
        Some(folder.id),
        true,
        &[],
    )
    .unwrap();
    db.set_folder_access_state(7, "ok").unwrap();
    let job = db.next_job().unwrap().unwrap();
    let report =
        crate::sync::engine::run_upload_job(&client, &db, &job, |_, _| {}, || false, |_| {})
            .await
            .unwrap();
    let crate::sync::engine::UploadOutcome::Finalized(finalized) = report.outcome else {
        panic!("expected a finalized upload");
    };
    assert_eq!(finalized.status, "completed");
    let download = client
        .authorize_download(folder.id, finalized.file_id, finalized.version_id.unwrap())
        .await
        .unwrap();
    assert_eq!(
        reqwest::get(download.url)
            .await
            .unwrap()
            .bytes()
            .await
            .unwrap()
            .as_ref(),
        b"queued"
    );
    assert_eq!(
        std::fs::read(dir.path().join("result.docx")).unwrap(),
        b"queued"
    );
    client.logout().await.unwrap();
}

#[tokio::test]
#[ignore = "requires an isolated Odoo/Garage stack and MEDILAB_E2E_* variables"]
async fn live_lost_prepare_reply_and_restart_create_one_upload_and_one_version() {
    use crate::api::ApiClient;
    use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
    let base = std::env::var("MEDILAB_E2E_URL").unwrap();
    let signed = ApiClient::login(
        &base,
        &std::env::var("MEDILAB_E2E_LOGIN").unwrap(),
        &std::env::var("MEDILAB_E2E_PASSWORD").unwrap(),
        "lost-answer-fixture",
        "linux",
        env!("CARGO_PKG_VERSION"),
        &uuid::Uuid::new_v4().to_string(),
    )
    .await
    .unwrap();
    let direct = ApiClient::new(&base, &signed.api_key, signed.device_id).unwrap();
    let root = format!("lost-answer-fixture-{}", uuid::Uuid::new_v4());
    let folder = direct.create_folder(&root, &root, &[]).await.unwrap();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let proxy_base = format!("http://{}", listener.local_addr().unwrap());
    let prepares = std::sync::Arc::new(parking_lot::Mutex::new(Vec::new()));
    let observed = prepares.clone();
    let proxy = tokio::spawn(async move {
        let upstream = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap();
        loop {
            let (socket, _) = listener.accept().await.unwrap();
            let mut socket = BufReader::new(socket);
            let mut request = String::new();
            socket.read_line(&mut request).await.unwrap();
            let words: Vec<_> = request.split_whitespace().collect();
            let (method, path) = (words[0], words[1]);
            let mut headers = reqwest::header::HeaderMap::new();
            let mut length = 0;
            loop {
                let mut line = String::new();
                socket.read_line(&mut line).await.unwrap();
                if line == "\r\n" {
                    break;
                }
                let (name, value) = line.split_once(':').unwrap();
                let name = name.to_ascii_lowercase();
                if name == "content-length" {
                    length = value.trim().parse::<usize>().unwrap();
                }
                if !matches!(name.as_str(), "host" | "connection" | "content-length") {
                    headers.insert(
                        reqwest::header::HeaderName::from_bytes(name.as_bytes()).unwrap(),
                        reqwest::header::HeaderValue::from_str(value.trim()).unwrap(),
                    );
                }
            }
            let mut body = vec![0; length];
            socket.read_exact(&mut body).await.unwrap();
            let key = headers
                .get("idempotency-key")
                .map(|value| value.to_str().unwrap().to_string());
            let response = upstream
                .request(
                    method.parse::<reqwest::Method>().unwrap(),
                    format!("{base}{path}"),
                )
                .headers(headers)
                .body(body)
                .send()
                .await
                .unwrap();
            let status = response.status();
            let body = response.bytes().await.unwrap();
            if method == "POST" && path.ends_with("/uploads") && status.is_success() {
                let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
                let mut seen = observed.lock();
                seen.push((key, json["upload"]["id"].clone()));
                if seen.len() == 1 {
                    continue;
                }
            }
            socket.get_mut().write_all(format!("HTTP/1.1 {} Fixture\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n",status.as_u16(),body.len()).as_bytes()).await.unwrap();
            socket.get_mut().write_all(&body).await.unwrap();
        }
    });
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("result.docx"), b"queued").unwrap();
    let path = legacy_database(dir.path());
    let db = Db::open(&path).unwrap();
    db.migrate_laboratory_api().unwrap();
    db.upsert_folder(
        dir.path().to_str().unwrap(),
        &root,
        Some(folder.id),
        true,
        &[],
    )
    .unwrap();
    db.set_folder_access_state(7, "ok").unwrap();
    let client = ApiClient::new(&proxy_base, &signed.api_key, signed.device_id).unwrap();
    let job = db.next_job().unwrap().unwrap();
    assert!(
        crate::sync::engine::run_upload_job(&client, &db, &job, |_, _| {}, || false, |_| {})
            .await
            .is_err()
    );
    drop(db);
    let db = Db::open(&path).unwrap();
    db.recover_jobs().unwrap();
    let job = db.next_job().unwrap().unwrap();
    let report =
        crate::sync::engine::run_upload_job(&client, &db, &job, |_, _| {}, || false, |_| {})
            .await
            .unwrap();
    let crate::sync::engine::UploadOutcome::Finalized(finalized) = report.outcome else {
        panic!("expected a finalized upload");
    };
    assert_eq!(
        direct
            .get_file_versions(folder.id, finalized.file_id, 20, 0)
            .await
            .unwrap()
            .total,
        1
    );
    {
        let seen = prepares.lock();
        assert_eq!(seen.len(), 2);
        assert!(seen[0].0.is_some());
        assert!(!seen[0].1.is_null());
        assert_eq!(seen[0], seen[1]);
    }
    assert_eq!(
        std::fs::read(dir.path().join("result.docx")).unwrap(),
        b"queued"
    );
    proxy.abort();
    direct.logout().await.unwrap();
}
