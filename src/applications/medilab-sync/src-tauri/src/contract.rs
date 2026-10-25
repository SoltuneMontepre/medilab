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

fn resolved(value: &Value) -> &Value {
    value
        .get("$ref")
        .and_then(Value::as_str)
        .map(|r| document().pointer(&r[1..]).unwrap())
        .unwrap_or(value)
}

fn validate(schema: &Value, value: &Value) {
    let mut schema = schema.clone();
    schema
        .as_object_mut()
        .unwrap()
        .insert("components".into(), document()["components"].clone());
    let validator = jsonschema::validator_for(&schema).unwrap();
    if let Err(error) = validator.validate(value) {
        panic!("OpenAPI schema violation: {error}");
    }
}

fn operation(method: &str, path: &str) -> (&'static Value, &'static Value) {
    let actual: Vec<_> = path.trim_matches('/').split('/').collect();
    for (template, item) in document()["paths"].as_object().unwrap() {
        let pattern: Vec<_> = template.trim_matches('/').split('/').collect();
        if pattern.len() == actual.len()
            && pattern
                .iter()
                .zip(&actual)
                .all(|(p, a)| p.starts_with('{') || p == a)
        {
            let op = &item[method.to_ascii_lowercase()];
            assert!(!op.is_null(), "Undocumented method {method} {template}");
            return (item, op);
        }
    }
    panic!("Undocumented API path {path}");
}

pub fn request(method: &str, url: &url::Url, headers: &HashMap<String, String>, body: &[u8]) {
    let path = url.path().split_once("/medilab/api/v1").unwrap().1;
    let (item, op) = operation(method, path);
    assert!(headers
        .get("user-agent")
        .is_some_and(|ua| ua == concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION"))));
    assert!(!headers.contains_key("x-sync-device-id"));
    if path != "/sign-in" {
        assert!(headers
            .get("authorization")
            .is_some_and(|v| v.starts_with("Bearer ")));
    }
    let params: Vec<_> = item["parameters"]
        .as_array()
        .into_iter()
        .flatten()
        .chain(op["parameters"].as_array().into_iter().flatten())
        .map(resolved)
        .collect();
    for p in &params {
        if p["in"] == "header" {
            let name = p["name"].as_str().unwrap().to_ascii_lowercase();
            if let Some(value) = headers.get(&name) {
                validate(&p["schema"], &json!(value));
            } else {
                assert!(p["required"] != true, "missing required header {name}");
            }
        }
    }
    for (name, value) in url.query_pairs() {
        let param = params
            .iter()
            .find(|p| p["in"] == "query" && p["name"] == name.as_ref())
            .unwrap_or_else(|| panic!("Undocumented query parameter {name}"));
        validate(&param["schema"], &json!(value));
    }
    if op.get("requestBody").is_some() {
        assert!(headers
            .get("content-type")
            .is_some_and(|v| v.starts_with("application/json")));
        validate(
            &op["requestBody"]["content"]["application/json"]["schema"],
            &serde_json::from_slice::<Value>(body).unwrap(),
        );
    } else {
        assert!(
            body.is_empty(),
            "Undocumented request body for {method} {path}"
        );
    }
}

pub fn response(
    method: &str,
    path: &str,
    status: u16,
    headers: &HashMap<String, String>,
    body: &[u8],
) {
    let path = path.split_once("/medilab/api/v1").unwrap().1;
    let (_, op) = operation(method, path);
    let response = &op["responses"][status.to_string()];
    assert!(
        !response.is_null(),
        "Undocumented response HTTP {status} for {method} {path}"
    );
    let response = resolved(response);
    if let Some(required) = response["headers"].as_object() {
        for (name, schema) in required {
            let schema = resolved(schema);
            if schema["required"] == true {
                let value = headers
                    .get(&name.to_ascii_lowercase())
                    .unwrap_or_else(|| panic!("Missing response header {name}"));
                let value = if schema["schema"]["type"] == "integer" {
                    json!(value.parse::<i64>().expect("integer response header"))
                } else {
                    json!(value)
                };
                validate(&schema["schema"], &value);
            }
        }
    }
    if let Some(schema) = response.pointer("/content/application~1json/schema") {
        validate(schema, &serde_json::from_slice::<Value>(body).unwrap());
    } else {
        assert!(body.is_empty());
    }
}

#[test]
#[should_panic(expected = "Undocumented request body")]
fn rejects_legacy_finalize_body() {
    request(
        "POST",
        &url::Url::parse("http://localhost/medilab/api/v1/folders/1/uploads/1/finalize").unwrap(),
        &HashMap::from([
            (
                "user-agent".into(),
                concat!("MediLab-Sync/", env!("CARGO_PKG_VERSION")).into(),
            ),
            ("authorization".into(), "Bearer test".into()),
        ]),
        b"{}",
    );
}
