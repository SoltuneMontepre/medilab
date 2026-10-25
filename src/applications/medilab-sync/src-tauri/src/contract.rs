use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::OnceLock;

fn document() -> &'static Value {
    static DOC: OnceLock<Value> = OnceLock::new();
    DOC.get_or_init(|| {
        serde_yaml::from_str(include_str!(
            "../../../../core/modules/sol_laboratory/api/openapi.yaml"
        ))
        .unwrap()
    })
}

fn updater_document() -> &'static Value {
    static DOC: OnceLock<Value> = OnceLock::new();
    DOC.get_or_init(|| {
        serde_yaml::from_str(include_str!(
            "../../../../core/modules/sol_laboratory/api/sync-updates.openapi.yaml"
        ))
        .unwrap()
    })
}

pub async fn updater_fetch(
    client: &reqwest::Client,
    builder: reqwest::RequestBuilder,
) -> reqwest::Result<reqwest::Response> {
    let request = builder.build()?;
    let url = request.url().clone();
    let headers = request
        .headers()
        .iter()
        .map(|(name, value)| (name.to_string(), value.to_str().unwrap().into()))
        .collect();
    assert!(!request.headers().contains_key("authorization"));
    let contract = Contract {
        document: updater_document(),
        strip_api_prefix: false,
    };
    contract.request("GET", &url, &headers, b"");
    let response = client.execute(request).await?;
    let status = response.status();
    let headers = response.headers().clone();
    let body = response.bytes().await?;
    let values = headers
        .iter()
        .map(|(name, value)| (name.to_string(), value.to_str().unwrap().into()))
        .collect();
    contract.response("GET", url.path(), status.as_u16(), &values, &body);
    let mut restored = http::Response::builder().status(status);
    *restored.headers_mut().unwrap() = headers;
    Ok(reqwest::Response::from(restored.body(body).unwrap()))
}

struct Contract<'a> {
    document: &'a Value,
    strip_api_prefix: bool,
}

impl<'a> Contract<'a> {
    fn operation_path<'b>(&self, path: &'b str) -> &'b str {
        let prefix = "/medilab/api/v1";
        path.rfind(prefix)
            .map(|index| {
                &path[index
                    + if self.strip_api_prefix {
                        prefix.len()
                    } else {
                        0
                    }..]
            })
            .unwrap_or(path)
    }

    fn resolved<'b>(&'b self, value: &'b Value) -> &'b Value {
        value
            .get("$ref")
            .and_then(Value::as_str)
            .map(|reference| {
                self.document
                    .pointer(&reference[1..])
                    .expect("internal OpenAPI reference")
            })
            .unwrap_or(value)
    }

    fn validate(&self, schema: &Value, value: &Value) {
        let mut schema = schema.clone();
        schema
            .as_object_mut()
            .unwrap()
            .insert("components".into(), self.document["components"].clone());
        let validator = jsonschema::validator_for(&schema).unwrap();
        if let Err(error) = validator.validate(value) {
            panic!(
                "OpenAPI schema violation at {} (schema {})",
                error.instance_path, error.schema_path
            );
        }
    }

    fn operation(&self, method: &str, path: &str) -> (&Value, &Value, HashMap<String, String>) {
        let actual: Vec<_> = path.trim_matches('/').split('/').collect();
        for (template, item) in self.document["paths"].as_object().unwrap() {
            let pattern: Vec<_> = template.trim_matches('/').split('/').collect();
            if pattern.len() == actual.len()
                && pattern
                    .iter()
                    .zip(&actual)
                    .all(|(p, a)| p.starts_with('{') || p == a)
            {
                let operation = &item[method.to_ascii_lowercase()];
                assert!(
                    !operation.is_null(),
                    "Undocumented method {method} {template}"
                );
                let captured = pattern
                    .iter()
                    .zip(&actual)
                    .filter(|(part, _)| part.starts_with('{'))
                    .map(|(part, value)| {
                        (part.trim_matches(['{', '}']).to_string(), value.to_string())
                    })
                    .collect();
                return (item, operation, captured);
            }
        }
        panic!("Undocumented API path {path}");
    }

    fn scalar(&self, schema: &Value, text: &str) -> Value {
        match self.resolved(schema)["type"].as_str() {
            Some("integer") => json!(text.parse::<i64>().expect("integer HTTP parameter")),
            Some("number") => json!(text.parse::<f64>().expect("numeric HTTP parameter")),
            Some("boolean") => json!(text.parse::<bool>().expect("boolean HTTP parameter")),
            _ => json!(text),
        }
    }

    fn request(
        &self,
        method: &str,
        url: &url::Url,
        headers: &HashMap<String, String>,
        body: &[u8],
    ) {
        let path = self.operation_path(url.path());
        let (item, op, captured) = self.operation(method, path);
        assert_eq!(
            headers.get("user-agent").map(String::as_str),
            Some(concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")))
        );
        assert!(!headers.contains_key("x-sync-device-id"));
        let security = op.get("security").unwrap_or(&self.document["security"]);
        if security
            .as_array()
            .is_some_and(|requirements| !requirements.is_empty())
        {
            assert!(headers
                .get("authorization")
                .is_some_and(|value| value.starts_with("Bearer ") && value.len() > 7));
        }
        let mut parameters = HashMap::new();
        for parameter in item["parameters"]
            .as_array()
            .into_iter()
            .flatten()
            .chain(op["parameters"].as_array().into_iter().flatten())
        {
            let parameter = self.resolved(parameter);
            parameters.insert(
                (
                    parameter["in"].as_str().unwrap(),
                    parameter["name"].as_str().unwrap(),
                ),
                parameter,
            );
        }
        let mut query = HashMap::new();
        for (name, value) in url.query_pairs() {
            assert!(
                parameters.contains_key(&("query", name.as_ref())),
                "Undocumented query parameter {name}"
            );
            assert!(
                query.insert(name.to_string(), value.to_string()).is_none(),
                "Repeated query parameter"
            );
        }
        for ((location, name), parameter) in parameters {
            let lower = name.to_ascii_lowercase();
            let value = match location {
                "header" => headers.get(&lower),
                "query" => query.get(name),
                "path" => captured.get(name),
                _ => panic!("Unsupported parameter location"),
            };
            if let Some(value) = value {
                self.validate(
                    &parameter["schema"],
                    &self.scalar(&parameter["schema"], value),
                );
            } else {
                assert!(
                    parameter["required"] != true,
                    "Missing required {location} parameter {name}"
                );
            }
        }
        if let Some(request) = op.get("requestBody") {
            let request = self.resolved(request);
            if body.is_empty() {
                assert!(request["required"] != true, "Missing required request body");
                return;
            }
            assert!(headers
                .get("content-type")
                .is_some_and(|value| value.split(';').next() == Some("application/json")));
            self.validate(
                &request["content"]["application/json"]["schema"],
                &serde_json::from_slice::<Value>(body).expect("JSON request"),
            );
        } else {
            assert!(
                body.is_empty(),
                "Undocumented request body for {method} {path}"
            );
        }
    }

    fn response(
        &self,
        method: &str,
        path: &str,
        status: u16,
        headers: &HashMap<String, String>,
        body: &[u8],
    ) {
        let path = self.operation_path(path);
        let (_, op, _) = self.operation(method, path);
        let response = &op["responses"][status.to_string()];
        assert!(
            !response.is_null(),
            "Undocumented response HTTP {status} for {method} {path}"
        );
        let response = self.resolved(response);
        if let Some(declared) = response["headers"].as_object() {
            for (name, schema) in declared {
                let schema = self.resolved(schema);
                if let Some(value) = headers.get(&name.to_ascii_lowercase()) {
                    self.validate(&schema["schema"], &self.scalar(&schema["schema"], value));
                } else {
                    assert!(
                        schema["required"] != true,
                        "Missing required response header {name}"
                    );
                }
            }
        }
        if let Some(schema) = response.pointer("/content/application~1json/schema") {
            assert!(
                headers
                    .get("content-type")
                    .is_some_and(|value| value.split(';').next() == Some("application/json")),
                "JSON response Content-Type"
            );
            self.validate(
                schema,
                &serde_json::from_slice::<Value>(body).expect("JSON response"),
            );
        } else {
            assert!(body.is_empty(), "Undocumented response body");
        }
    }
}

pub fn request(method: &str, url: &url::Url, headers: &HashMap<String, String>, body: &[u8]) {
    Contract {
        document: document(),
        strip_api_prefix: true,
    }
    .request(method, url, headers, body);
}
pub fn response(
    method: &str,
    path: &str,
    status: u16,
    headers: &HashMap<String, String>,
    body: &[u8],
) {
    Contract {
        document: document(),
        strip_api_prefix: true,
    }
    .response(method, path, status, headers, body);
}

#[cfg(test)]
mod tests {
    use super::*;
    fn headers() -> HashMap<String, String> {
        HashMap::from([
            (
                "user-agent".into(),
                concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")).into(),
            ),
            ("authorization".into(), "Bearer test".into()),
            ("content-type".into(), "application/json".into()),
        ])
    }

    #[test]
    fn updater_uses_the_separate_shared_contract_and_detects_drift() {
        let mut headers = headers();
        headers.remove("authorization");
        headers.insert("cache-control".into(), "no-store".into());
        headers.insert("x-content-type-options".into(), "nosniff".into());
        let url =
            url::Url::parse("http://localhost/tenant/medilab/api/v1/updates/linux/x86_64/0.1.0")
                .unwrap();
        let contract = Contract {
            document: updater_document(),
            strip_api_prefix: false,
        };
        let body = br#"{"version":"0.2.0","url":"https://downloads.example/sync.tar.gz","signature":"Zml4dHVyZQ=="}"#;
        contract.request("GET", &url, &headers, b"");
        contract.response("GET", url.path(), 200, &headers, body);
        let mut changed = updater_document().clone();
        changed["components"]["schemas"]["Manifest"]["required"]
            .as_array_mut()
            .unwrap()
            .push(json!("pub_date"));
        assert!(std::panic::catch_unwind(|| Contract {
            document: &changed,
            strip_api_prefix: false
        }
        .response("GET", url.path(), 200, &headers, body))
        .is_err());
        headers.remove("cache-control");
        assert!(std::panic::catch_unwind(|| contract.response(
            "GET",
            url.path(),
            200,
            &headers,
            body
        ))
        .is_err());
    }

    #[test]
    #[should_panic(expected = "Undocumented request body")]
    fn rejects_legacy_finalize_body() {
        request(
            "POST",
            &url::Url::parse("http://localhost/medilab/api/v1/folders/1/uploads/1/finalize")
                .unwrap(),
            &headers(),
            b"{}",
        );
    }

    #[test]
    #[should_panic(expected = "integer HTTP parameter")]
    fn path_parameters_are_validated() {
        request(
            "GET",
            &url::Url::parse("http://localhost/medilab/api/v1/folders/not-an-id/files").unwrap(),
            &headers(),
            b"",
        );
    }

    #[test]
    fn configured_base_paths_are_outside_the_operation_path() {
        let url = url::Url::parse("http://localhost/medilab/api/v1/tenant/medilab/api/v1/devices")
            .unwrap();
        request("GET", &url, &headers(), b"");
        response("GET", url.path(), 200, &headers(), br#"{"devices":[]}"#);
    }

    #[test]
    fn schema_drift_changes_request_and_response_validation() {
        let mut changed = document().clone();
        changed["components"]["schemas"]["SignIn"]["required"]
            .as_array_mut()
            .unwrap()
            .push(json!("tenant"));
        changed["components"]["schemas"]["SignIn"]["properties"]["tenant"] =
            json!({"type":"string"});
        let body=br#"{"login":"tester","password":"fixture","client_uid":"pc","name":"PC","platform":"linux"}"#;
        let url = url::Url::parse("http://localhost/medilab/api/v1/sign-in").unwrap();
        request("POST", &url, &headers(), body);
        assert!(std::panic::catch_unwind(|| Contract {
            document: &changed,
            strip_api_prefix: true
        }
        .request("POST", &url, &headers(), body))
        .is_err());
        changed = document().clone();
        changed["paths"]["/devices"]["get"]["parameters"] =
            json!([{"in":"query","name":"revision","required":true,"schema":{"type":"string"}}]);
        let url = url::Url::parse("http://localhost/medilab/api/v1/devices").unwrap();
        assert!(std::panic::catch_unwind(|| Contract {
            document: &changed,
            strip_api_prefix: true
        }
        .request("GET", &url, &headers(), b""))
        .is_err());
        changed = document().clone();
        changed["paths"]["/devices"]["get"]["responses"]["200"]["headers"] =
            json!({"X-Quota":{"schema":{"type":"integer"}}});
        let mut invalid = headers();
        invalid.insert("x-quota".into(), "not-an-integer".into());
        assert!(std::panic::catch_unwind(|| Contract {
            document: &changed,
            strip_api_prefix: true
        }
        .response(
            "GET",
            "/medilab/api/v1/devices",
            200,
            &invalid,
            br#"{"devices":[]}"#
        ))
        .is_err());
        changed = document().clone();
        changed["components"]["schemas"]["DeviceList"]["properties"]["devices"]["minItems"] =
            json!(1);
        assert!(std::panic::catch_unwind(|| Contract {
            document: &changed,
            strip_api_prefix: true
        }
        .response(
            "GET",
            "/medilab/api/v1/devices",
            200,
            &headers(),
            br#"{"devices":[]}"#
        ))
        .is_err());
    }
}
