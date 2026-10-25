use crate::error::{AppError, AppResult};
use url::Url;

pub fn endpoint(base: &str, path: &str) -> AppResult<Url> {
    let invalid = || AppError::Message("Địa chỉ máy chủ HTTP(S) không hợp lệ".into());
    if base
        .chars()
        .any(|ch| ch.is_whitespace() || ch.is_control() || ch == '\\')
    {
        return Err(invalid());
    }
    let lower = base.to_ascii_lowercase();
    if ["%2f", "%5c", "%2e", "%00"]
        .iter()
        .any(|part| lower.contains(part))
        || base.split('/').any(|part| part == "." || part == "..")
    {
        return Err(invalid());
    }
    let mut url = Url::parse(base).map_err(|_| invalid())?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err(invalid());
    }
    url.set_path(&format!(
        "{}/{}",
        url.path().trim_end_matches('/'),
        path.trim_start_matches('/')
    ));
    Ok(url)
}
