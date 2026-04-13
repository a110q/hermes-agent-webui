from __future__ import annotations

import json
import os
import socket
import time
from urllib.parse import quote


class DockerComposeRuntime:
    def __init__(self, socket_path: str = "/var/run/docker.sock"):
        self.socket_path = socket_path

    @staticmethod
    def _decode_chunked_body(body: bytes) -> bytes:
        cursor = 0
        decoded = bytearray()
        total = len(body)

        while cursor < total:
            line_end = body.find(b"\r\n", cursor)
            if line_end == -1:
                break

            size_line = body[cursor:line_end].decode("utf-8", errors="replace").strip()
            if not size_line:
                cursor = line_end + 2
                continue

            try:
                chunk_size = int(size_line.split(";", 1)[0], 16)
            except ValueError:
                return body

            cursor = line_end + 2
            if chunk_size == 0:
                break

            decoded.extend(body[cursor:cursor + chunk_size])
            cursor += chunk_size + 2

        return bytes(decoded)

    def _request_json(self, method: str, path: str):
        request = (
            f"{method} {path} HTTP/1.1\r\n"
            "Host: docker\r\n"
            "Connection: close\r\n"
            "Accept: application/json\r\n"
            "\r\n"
        ).encode("utf-8")

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(self.socket_path)
        try:
            client.sendall(request)
            response = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                response += chunk
        finally:
            client.close()

        header_bytes, _, body = response.partition(b"\r\n\r\n")
        header_lines = header_bytes.decode("utf-8", errors="replace").splitlines() if header_bytes else []
        headers: dict[str, str] = {}
        for line in header_lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        status_line = header_lines[0] if header_lines else ""
        try:
            status_code = int(status_line.split()[1])
        except Exception as exc:
            raise RuntimeError(f"Malformed Docker API response for {method} {path}") from exc

        if status_code >= 400:
            raise RuntimeError(f"Docker API request failed: {method} {path} -> {status_code}")
        if status_code == 204 or not body:
            return {}

        if headers.get("transfer-encoding", "").lower() == "chunked":
            body = self._decode_chunked_body(body)

        body_text = body.decode("utf-8", errors="replace").strip()
        if not body_text or body_text == "0":
            return {}
        if not body_text.startswith(("{", "[")):
            return {}
        return json.loads(body_text)

    def discover_services(self) -> dict[str, str]:
        container_id = os.getenv("HOSTNAME", "").strip()
        if not container_id:
            raise RuntimeError("HOSTNAME is required to discover compose services")

        current_container = self._request_json("GET", f"/containers/{container_id}/json")
        labels = ((current_container.get("Config") or {}).get("Labels") or {})
        project_name = labels.get("com.docker.compose.project")
        if not project_name:
            raise RuntimeError("Current container is missing com.docker.compose.project label")

        filters = quote(json.dumps({"label": [f"com.docker.compose.project={project_name}"]}))
        containers = self._request_json("GET", f"/containers/json?all=1&filters={filters}")

        services: dict[str, str] = {}
        for container in containers:
            service_name = ((container.get("Labels") or {}).get("com.docker.compose.service") or "").strip()
            names = container.get("Names") or []
            if service_name and names:
                services[service_name] = names[0].lstrip("/")
        return services

    def inspect_service(self, service_name: str) -> dict:
        services = self.discover_services()
        container_name = services[service_name]
        return self._request_json("GET", f"/containers/{container_name}/json")

    def restart_service(self, service_name: str) -> None:
        services = self.discover_services()
        container_name = services[service_name]
        self._request_json("POST", f"/containers/{container_name}/restart?t=2")

    def wait_for_service(
        self,
        service_name: str,
        *,
        timeout_seconds: float = 90,
        poll_interval: float = 1.0,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        last_health = ""
        last_status = ""

        while True:
            payload = self.inspect_service(service_name)
            state = payload.get("State") or {}
            health = str(((state.get("Health") or {}).get("Status") or "")).strip().lower()
            status = str(state.get("Status") or "").strip().lower()
            last_health = health or last_health
            last_status = status or last_status

            if health == "healthy":
                return payload
            if not health and status == "running":
                return payload
            if health == "unhealthy" or status in {"dead", "exited"}:
                raise RuntimeError(
                    f"Service {service_name} became unavailable (status={status or 'unknown'}, health={health or 'n/a'})"
                )
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timed out waiting for {service_name} (status={last_status or 'unknown'}, health={last_health or 'n/a'})"
                )
            time.sleep(poll_interval)
