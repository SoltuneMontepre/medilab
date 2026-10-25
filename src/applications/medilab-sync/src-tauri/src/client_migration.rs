use crate::error::{AppError, AppResult};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, OnceLock};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MigrationRequired {
    pub message: String,
    pub download_url: Option<String>,
}

impl std::fmt::Display for MigrationRequired {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

static NOTICES: OnceLock<parking_lot::Mutex<HashMap<String, MigrationRequired>>> = OnceLock::new();
static NOTIFY: OnceLock<Arc<dyn Fn() + Send + Sync>> = OnceLock::new();

fn server_key(base: &str) -> String {
    url::Url::parse(base)
        .map(|url| url.to_string())
        .unwrap_or_else(|_| base.into())
        .trim_end_matches('/')
        .to_string()
}

pub fn set_notifier(notify: impl Fn() + Send + Sync + 'static) {
    let _ = NOTIFY.set(Arc::new(notify));
}

pub fn required(base: &str) -> Option<MigrationRequired> {
    NOTICES
        .get_or_init(Default::default)
        .lock()
        .get(&server_key(base))
        .cloned()
}

pub fn record(base: &str, notice: MigrationRequired) {
    let changed = NOTICES
        .get_or_init(Default::default)
        .lock()
        .insert(server_key(base), notice.clone())
        .as_ref()
        != Some(&notice);
    if changed {
        if let Some(notify) = NOTIFY.get() {
            notify();
        }
    }
}

pub fn clear(base: &str) {
    let removed = NOTICES
        .get_or_init(Default::default)
        .lock()
        .remove(&server_key(base))
        .is_some();
    if removed {
        if let Some(notify) = NOTIFY.get() {
            notify();
        }
    }
}

pub fn safe_download_url(value: &str) -> Option<String> {
    crate::server_url::endpoint(value, "").ok()?;
    let url = url::Url::parse(value).ok()?;
    let local = url.host_str().is_some_and(|host| {
        host == "localhost"
            || host
                .parse::<std::net::IpAddr>()
                .is_ok_and(|address| address.is_loopback())
    });
    if url.scheme() != "https" && !local {
        return None;
    }
    Some(url.into())
}

pub fn refusal(status: u16, body: &str) -> Option<MigrationRequired> {
    #[derive(Deserialize)]
    struct Envelope {
        error: Refusal,
    }
    #[derive(Deserialize)]
    struct Refusal {
        code: String,
        message: String,
        #[serde(default)]
        download_url: Option<String>,
    }
    if status != 410 {
        return None;
    }
    let wire: Envelope = serde_json::from_str(body).ok()?;
    if wire.error.code != "client_update_required" {
        return None;
    }
    Some(MigrationRequired {
        message: crate::error::redact_url_queries(&wire.error.message),
        download_url: wire
            .error
            .download_url
            .as_deref()
            .and_then(safe_download_url),
    })
}

/// Observe the migration refusal before handing normal manifests to Tauri's signature verifier.
pub async fn updater_requirement(
    base: &str,
    endpoint: &str,
) -> AppResult<Option<MigrationRequired>> {
    let response = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(15))
        .user_agent(concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")))
        .build()?
        .get(endpoint)
        .send()
        .await?;
    let status = response.status().as_u16();
    if status == 410 {
        let body = response.text().await?;
        let notice = refusal(status, &body)
            .ok_or_else(|| AppError::Message("Invalid client migration response".into()))?;
        record(base, notice.clone());
        return Ok(Some(notice));
    }
    Ok(None)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manual_downloads_allow_https_and_local_test_http_without_credentials_or_redirect_syntax() {
        for value in [
            "https://example.com/releases/sync.deb",
            "http://127.0.0.1:1234/sync.deb",
        ] {
            assert_eq!(safe_download_url(value).as_deref(), Some(value));
        }
        for value in [
            "http://example.com/download",
            "javascript:alert(1)",
            "file:///tmp/x",
            "https://user:secret@example.com/x",
            "https://example.com/x?token=secret",
            "https://example.com/x#fragment",
            "https://example.com/%0a",
            "//evil.example/x",
        ] {
            assert!(safe_download_url(value).is_none(), "{value}");
        }
    }

    #[test]
    fn migration_notices_are_typed_safe_and_scoped_to_the_server() {
        let body = r#"{"error":{"code":"client_update_required","message":"Install the current release","download_url":"https://example.com/releases/sync.deb"}}"#;
        let notice = refusal(410, body).unwrap();
        assert!(refusal(403, body).is_none());
        let base = format!("https://{}.example", uuid::Uuid::new_v4());
        record(&base, notice.clone());
        assert_eq!(required(&base), Some(notice));
        assert!(required("https://another.example").is_none());
        clear(&base);
        assert!(required(&base).is_none());
        let unsafe_body = body.replace(
            "https://example.com/releases/sync.deb",
            "https://user:key@example.com/x",
        );
        assert!(refusal(410, &unsafe_body).unwrap().download_url.is_none());
    }

    #[test]
    fn notices_match_normalized_origins_and_keep_installation_paths_distinct() {
        let base = format!("https://{}.example", uuid::Uuid::new_v4());
        let notice = MigrationRequired {
            message: "Update required".into(),
            download_url: None,
        };
        record(&format!("{base}:443/base/"), notice.clone());
        assert_eq!(required(&format!("{base}/base")), Some(notice));
        assert!(required(&base).is_none());
        clear(&format!("{base}/base"));
    }
}
