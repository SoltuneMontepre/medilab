use crate::config::AppSettings;
use crate::error::AppResult;
use crate::storage::Db;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const PENDING: &str = "pending_sign_in";

#[derive(Deserialize, Serialize)]
pub struct PendingSignIn {
    key_fingerprint: String,
    base: String,
    login: String,
    device_id: i64,
}

impl PendingSignIn {
    pub fn save(db: &Db, base: &str, login: &str, device_id: i64, key: &str) -> AppResult<Self> {
        crate::server_url::endpoint(base, "medilab/api/v1")?;
        let pending = Self {
            key_fingerprint: hex::encode(Sha256::digest(key.as_bytes())),
            base: base.into(),
            login: login.into(),
            device_id,
        };
        db.meta_set(PENDING, &serde_json::to_string(&pending)?)?;
        Ok(pending)
    }

    pub fn commit(&self, db: &Db) -> AppResult<AppSettings> {
        let mut settings = db.load_settings()?;
        let previous_login = db.meta_get("user_login")?;
        if previous_login
            .as_deref()
            .is_some_and(|old| old != self.login)
            || settings.odoo_url.trim_end_matches('/') != self.base.trim_end_matches('/')
        {
            db.meta_set("laboratory_api_version", "rebind")?;
        }
        db.migrate_laboratory_api()?;
        db.meta_set("device_id", &self.device_id.to_string())?;
        db.meta_set("user_login", &self.login)?;
        db.meta_set("user_name", &self.login)?;
        settings.odoo_url = self.base.clone();
        db.meta_set("credential_origin", &self.base)?;
        db.save_settings(&settings)?;
        db.meta_set(PENDING, "")?;
        Ok(settings)
    }
}

/// Pair a key recovered after a crash with its own server before making any request.
pub fn recover(db: &Db, key: &str) -> AppResult<Option<AppSettings>> {
    let Some(raw) = db.meta_get(PENDING)?.filter(|raw| !raw.is_empty()) else {
        return validate_origin(db).map(|_| None);
    };
    let pending: PendingSignIn = serde_json::from_str(&raw)?;
    if pending.key_fingerprint != hex::encode(Sha256::digest(key.as_bytes())) {
        return validate_origin(db).map(|_| None);
    }
    Ok(Some(pending.commit(db)?))
}

fn validate_origin(db: &Db) -> AppResult<()> {
    let settings = db.load_settings()?;
    if db.meta_get("credential_origin")?.is_some_and(|origin| {
        origin.trim_end_matches('/') != settings.odoo_url.trim_end_matches('/')
    }) {
        return Err(crate::error::AppError::NotLoggedIn);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crash_between_keyring_write_and_settings_commit_never_uses_the_old_server() {
        let dir = tempfile::tempdir().unwrap();
        let db = Db::open(&dir.path().join("q.sqlite")).unwrap();
        let mut settings = db.load_settings().unwrap();
        settings.odoo_url = "https://old.example".into();
        db.save_settings(&settings).unwrap();
        let folder = db
            .upsert_folder(dir.path().to_str().unwrap(), "R", Some(7), true, &[])
            .unwrap();
        PendingSignIn::save(
            &db,
            "https://new.example/base",
            "tester",
            9,
            "new-device-secret",
        )
        .unwrap();
        let raw = db.meta_get(PENDING).unwrap().unwrap();
        assert!(!raw.contains("new-device-secret"));
        assert!(recover(&db, "old-device-secret").unwrap().is_none());
        assert_eq!(db.load_settings().unwrap().odoo_url, "https://old.example");
        let recovered = recover(&db, "new-device-secret").unwrap().unwrap();
        assert_eq!(recovered.odoo_url, "https://new.example/base");
        assert_eq!(db.meta_get("device_id").unwrap().as_deref(), Some("9"));
        assert_eq!(db.list_folders().unwrap()[0].id, folder);
        assert_eq!(db.list_folders().unwrap()[0].remote_id, None);
        assert!(recover(&db, "new-device-secret").unwrap().is_none());
        let mut changed = db.load_settings().unwrap();
        changed.odoo_url = "https://unrelated.example".into();
        db.save_settings(&changed).unwrap();
        assert!(matches!(
            recover(&db, "new-device-secret"),
            Err(crate::error::AppError::NotLoggedIn)
        ));
    }
}
