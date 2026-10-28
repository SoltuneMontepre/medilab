use crate::api::ApiClient;
use std::time::{Duration, Instant};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};

#[tokio::test]
async fn sign_in_retries_typed_transient_refusals_with_retry_after_and_identical_payload() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move {
        let mut requests = Vec::new();
        for attempt in 0..3 {
            let (socket, _) = listener.accept().await.unwrap();
            let mut reader = BufReader::new(socket);
            let mut first = String::new();
            reader.read_line(&mut first).await.unwrap();
            assert!(first.starts_with("POST /medilab/api/v1/sign-in "));
            let mut length = 0;
            loop {
                let mut line = String::new();
                reader.read_line(&mut line).await.unwrap();
                if line == "\r\n" {
                    break;
                }
                if let Some((name, value)) = line.split_once(':') {
                    if name.eq_ignore_ascii_case("content-length") {
                        length = value.trim().parse::<usize>().unwrap();
                    }
                }
            }
            let mut body = vec![0; length];
            reader.read_exact(&mut body).await.unwrap();
            requests.push(body);
            let (status, body) = match attempt {
                0 => (
                    "429 Too Many Requests",
                    serde_json::json!({"error":{"code":"too_many_attempts","message":"dịch vụ chờ"}}),
                ),
                1 => (
                    "503 Service Unavailable",
                    serde_json::json!({"error":{"code":"try_again","message":"任意"}}),
                ),
                _ => (
                    "200 OK",
                    serde_json::json!({"key":"test-device-key","device":{"id":1,"name":"test","platform":"linux","status":"signed_in","last_seen_at":null,"revoked_at":null,"current":true}}),
                ),
            };
            let body = body.to_string();
            let reply=format!("HTTP/1.1 {status}\r\nContent-Type: application/json\r\nRetry-After: 1\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{body}",body.len());
            reader.get_mut().write_all(reply.as_bytes()).await.unwrap();
        }
        assert!(requests.windows(2).all(|pair| pair[0] == pair[1]));
        let body: serde_json::Value = serde_json::from_slice(&requests[0]).unwrap();
        assert_eq!(body["platform"], "linux");
        assert!(body.get("device").is_none());
    });
    let start = Instant::now();
    let result = ApiClient::login(
        &base,
        "tester",
        "test-password",
        "test",
        "linux",
        env!("CARGO_PKG_VERSION"),
        "installation",
    )
    .await
    .unwrap();
    assert_eq!(result.device_id, 1);
    assert!(start.elapsed() >= Duration::from_secs(3));
    task.await.unwrap();
}
