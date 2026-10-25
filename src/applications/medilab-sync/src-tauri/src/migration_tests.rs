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
