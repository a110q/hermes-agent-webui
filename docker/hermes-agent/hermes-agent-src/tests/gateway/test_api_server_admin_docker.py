import pytest

from gateway.platforms.api_server_admin_docker import DockerComposeRuntime


def test_discover_services_uses_compose_labels(monkeypatch):
    runtime = DockerComposeRuntime(socket_path="/var/run/docker.sock")

    def fake_request(method, path):
        if path == "/containers/self-id/json":
            return {
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": "hermes_agent",
                    }
                }
            }
        if path.startswith("/containers/json"):
            return [
                {
                    "Names": ["/hermes_agent-hermes-agent-1"],
                    "Labels": {"com.docker.compose.service": "hermes-agent"},
                },
                {
                    "Names": ["/hermes_agent-open-webui-1"],
                    "Labels": {"com.docker.compose.service": "open-webui"},
                },
            ]
        raise AssertionError(path)

    monkeypatch.setattr(runtime, "_request_json", fake_request)
    monkeypatch.setenv("HOSTNAME", "self-id")

    services = runtime.discover_services()

    assert services == {
        "hermes-agent": "hermes_agent-hermes-agent-1",
        "open-webui": "hermes_agent-open-webui-1",
    }


def test_decode_chunked_body_returns_plain_payload():
    payload = b'{"ok": true}'
    chunked = f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"

    decoded = DockerComposeRuntime._decode_chunked_body(chunked)

    assert decoded == payload


def test_wait_for_service_polls_until_healthy(monkeypatch):
    runtime = DockerComposeRuntime(socket_path="/var/run/docker.sock")
    states = iter([
        {"State": {"Status": "running", "Health": {"Status": "starting"}}},
        {"State": {"Status": "running", "Health": {"Status": "healthy"}}},
    ])

    monkeypatch.setattr(runtime, "inspect_service", lambda service_name: next(states))
    monkeypatch.setattr("gateway.platforms.api_server_admin_docker.time.sleep", lambda _: None)

    payload = runtime.wait_for_service("open-webui", timeout_seconds=5, poll_interval=0)

    assert payload["State"]["Health"]["Status"] == "healthy"


def test_restart_service_posts_restart_request(monkeypatch):
    runtime = DockerComposeRuntime(socket_path="/var/run/docker.sock")
    calls = []

    monkeypatch.setattr(
        runtime,
        "discover_services",
        lambda: {"open-webui": "hermes_agent-open-webui-1"},
    )

    def fake_request(method, path):
        calls.append((method, path))
        return {}

    monkeypatch.setattr(runtime, "_request_json", fake_request)

    runtime.restart_service("open-webui")

    assert calls == [("POST", "/containers/hermes_agent-open-webui-1/restart?t=2")]
