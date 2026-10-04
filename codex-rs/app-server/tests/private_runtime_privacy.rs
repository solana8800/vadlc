//! Acceptance of the production private entrypoint, not environment opt-out toggles.
use codex_features::{Feature, Features};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

#[test]
fn private_policy_is_immutable_and_features_cannot_override_it() {
    codex_http_client::initialize_private_runtime(&[]).unwrap();
    assert!(
        codex_http_client::initialize_private_runtime(&["https://company.test/v1".into()]).is_err()
    );
    let mut features = Features::with_defaults();
    for feature in [
        Feature::Apps,
        Feature::Plugins,
        Feature::RemoteControl,
        Feature::RuntimeMetrics,
        Feature::PluginSharing,
        Feature::RemoteModels,
        Feature::RealtimeConversation,
    ] {
        features.enable(feature);
        assert!(!features.enabled(feature));
    }
    assert!(
        codex_http_client::check_private_model_destination(
            &url::Url::parse("https://api.openai.com/v1/responses").unwrap()
        )
        .is_err()
    );
}

#[test]
fn private_entrypoint_rejects_remote_control_and_public_provider() {
    for arguments in [
        vec!["--remote-control"],
        vec!["--private-model-endpoint", "https://api.openai.com/v1"],
        vec!["--listen", "ws://127.0.0.1:9012"],
    ] {
        let result = Command::new(env!("CARGO_BIN_EXE_v-adlc-agent-server"))
            .args(arguments)
            .output()
            .unwrap();
        assert!(!result.status.success());
    }
}

#[test]
fn private_rpc_disables_login_and_feedback_even_when_config_enables_them() {
    let home = tempfile::tempdir().unwrap();
    std::fs::write(
        home.path().join("config.toml"),
        r#"
model = "synthetic"
model_provider = "private"
feedback.enabled = true
analytics.enabled = true
[model_providers.private]
name = "Company"
base_url = "http://127.0.0.1:8123/v1"
wire_api = "responses"
requires_openai_auth = false
"#,
    )
    .unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_v-adlc-agent-server"))
        .args([
            "--listen",
            "stdio://",
            "--strict-config",
            "--private-model-endpoint",
            "http://127.0.0.1:8123/v1",
        ])
        .env("CODEX_HOME", home.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let stdout = child.stdout.take().unwrap();
    let (send, receive) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(value) = serde_json::from_str::<Value>(&line) {
                let _ = send.send(value);
            }
        }
    });
    let mut input = child.stdin.take().unwrap();
    let mut request = |id: u64, method: &str, params: Value| {
        writeln!(
            input,
            "{}",
            json!({"id": id, "method": method, "params": params})
        )
        .unwrap();
        input.flush().unwrap();
        loop {
            let message = receive
                .recv_timeout(Duration::from_secs(20))
                .expect("RPC deadline");
            if message["id"] == id {
                break message;
            }
        }
    };
    let initialized = request(
        1,
        "initialize",
        json!({"clientInfo":{"name":"privacy-test","version":"1"},"capabilities":{"experimentalApi":true}}),
    );
    let login = request(2, "account/login/start", json!({"type":"chatgpt"}));
    let feedback = request(
        3,
        "feedback/upload",
        json!({"classification":"bug","includeLogs":true,"extraLogFiles":["/nonexistent/company-secret"]}),
    );
    let thread = request(
        4,
        "thread/start",
        json!({"cwd":home.path(),"model":"synthetic","modelProvider":"private","sandbox":"read-only","approvalPolicy":"never"}),
    );
    child.kill().unwrap();
    child.wait().unwrap();
    drop(input);
    reader.join().unwrap();
    assert!(
        initialized["result"]["userAgent"]
            .as_str()
            .unwrap()
            .starts_with("V-ADLC Agent Server/")
    );
    assert!(
        login["error"]["message"]
            .as_str()
            .unwrap()
            .contains("unavailable")
    );
    assert!(
        feedback["error"]["message"]
            .as_str()
            .unwrap()
            .contains("disabled")
    );
    assert!(thread.get("result").is_some());
}
