import errno
import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack

import httpx
import pytest

from bookmark_organization import app as app_module
from bookmark_organization import server as server_module
from bookmark_organization.app import create_app
from bookmark_organization.server import (
    AlreadyRunning,
    StartupError,
    bind_listener,
    running_server,
)


async def test_shutdown_is_csrf_protected_and_blocks_later_mutations(tmp_path):
    app = create_app(tmp_path)
    callbacks = []

    async def request_exit():
        callbacks.append("exit")

    app.state.shutdown_callback = request_exit
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/")
        headers = {"X-CSRF-Token": client.cookies["csrf"]}
        assert (await client.get("/api/server/shutdown")).status_code == 405
        assert (await client.post("/api/server/shutdown")).status_code == 403
        assert (
            await client.post(
                "/api/server/shutdown",
                headers={**headers, "Origin": "https://evil.example"},
            )
        ).status_code == 403
        assert not callbacks and not app.state.worker.stopping
        result = await client.post("/api/server/shutdown", headers=headers)
        assert result.status_code == 200
        assert result.json() == {"status": "stopped"}
        assert callbacks == ["exit"]
        assert app.state.worker.stopping
        assert (
            await client.post(
                "/api/language", headers=headers, json={"preference": "ja"}
            )
        ).json() == {"code": "server_stopping"}
        assert (
            await client.post("/api/server/shutdown", headers=headers)
        ).status_code == 200


async def test_embedded_app_never_signals_an_unmanaged_host_process(tmp_path):
    app = create_app(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/")
        result = await client.post(
            "/api/server/shutdown", headers={"X-CSRF-Token": client.cookies["csrf"]}
        )
        assert result.status_code == 503
        assert result.json() == {"code": "server_shutdown_unavailable"}
        assert not app.state.worker.stopping


def test_fallback_reserves_next_port_and_keeps_occupied_listeners(monkeypatch):
    with ExitStack() as stack:
        occupied = [stack.enter_context(bind_listener(0)) for _ in range(2)]
        ports = [listener.getsockname()[1] for listener in occupied]
        monkeypatch.setattr(server_module, "DEFAULT_PORTS", [*ports, 0])
        with bind_listener(None) as selected:
            selected_port = selected.getsockname()[1]
            assert selected_port not in ports
            with pytest.raises(StartupError, match="No available port"):
                bind_listener(selected_port)
        for port in ports:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass
        # The selected socket is released when its owner exits.
        with bind_listener(selected_port):
            pass


def test_all_candidates_busy_and_explicit_port_never_falls_back(monkeypatch):
    with ExitStack() as stack:
        occupied = [stack.enter_context(bind_listener(0)) for _ in range(5)]
        ports = [listener.getsockname()[1] for listener in occupied]
        monkeypatch.setattr(server_module, "DEFAULT_PORTS", ports)
        with pytest.raises(StartupError, match="BOOKMARK_PORT"):
            bind_listener(None)
        with pytest.raises(StartupError, match="No available port"):
            bind_listener(ports[0])


def test_other_binding_failures_do_not_try_next_port(monkeypatch):
    calls = []

    class DeniedSocket:
        def setsockopt(self, *args):
            pass

        def bind(self, address):
            calls.append(address)
            raise PermissionError(errno.EACCES, "denied")

        def close(self):
            pass

    monkeypatch.setattr(server_module.socket, "socket", lambda *args: DeniedSocket())
    with pytest.raises(StartupError, match="Cannot listen"):
        bind_listener(None)
    assert calls == [("127.0.0.1", 8765)]


@pytest.mark.parametrize("port", [-1, 65536])
def test_invalid_port_rejected(port):
    with pytest.raises(StartupError, match="between 0 and 65535"):
        bind_listener(port)


def test_directory_lock_covers_aliases_and_stale_metadata(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    lock = directory / "server.lock"
    lock.write_text("99999")
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with running_server(directory, 0) as listener:
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        with pytest.raises(AlreadyRunning) as duplicate:
            with running_server(alias, 0):
                pytest.fail("duplicate server acquired the directory")
        assert duplicate.value.url == url
    assert lock.read_text() == ""
    with running_server(directory, 0):
        pass


def test_port_exhaustion_releases_directory_before_app_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKMARK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BOOKMARK_PORT", raising=False)
    monkeypatch.setattr(
        app_module, "create_app", lambda *args: pytest.fail("created app")
    )
    with bind_listener(0) as occupied:
        monkeypatch.setattr(server_module, "DEFAULT_PORTS", [occupied.getsockname()[1]])
        with pytest.raises(SystemExit, match="No available port"):
            app_module.main()
    assert not (tmp_path / "bookmarks.sqlite3").exists()
    with running_server(tmp_path, 0):
        pass


@pytest.mark.parametrize("value", ["invalid", "-1", "65536"])
def test_invalid_environment_port_fails_cleanly(tmp_path, monkeypatch, value):
    monkeypatch.setenv("BOOKMARK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOOKMARK_PORT", value)
    with pytest.raises(SystemExit, match="65535"):
        app_module.main()
    assert not (tmp_path / "bookmarks.sqlite3").exists()


def test_console_startup_duplicate_shutdown_and_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("BOOKMARK_PORT", raising=False)
    with bind_listener(0) as occupied:
        busy_port = occupied.getsockname()[1]
        environment = dict(os.environ, BOOKMARK_DATA_DIR=str(tmp_path))
        # Exercise automatic fallback with real sockets without using user ports.
        command = [
            sys.executable,
            "-c",
            "from bookmark_organization import server; "
            f"server.DEFAULT_PORTS = [{busy_port}, 0]; "
            "from bookmark_organization.app import main; main()",
        ]
        for _ in range(2):
            process = subprocess.Popen(
                command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            try:
                deadline = time.monotonic() + 10
                with httpx.Client(timeout=0.2, trust_env=False) as client:
                    while time.monotonic() < deadline:
                        assert process.poll() is None
                        saved = tmp_path / "server.lock"
                        port = saved.read_text().strip() if saved.exists() else ""
                        if port:
                            base = f"http://127.0.0.1:{port}"
                            try:
                                if client.get(base + "/health").status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                        time.sleep(0.05)
                    else:
                        pytest.fail("server startup timed out")
                    assert int(port) != busy_port
                    before = (tmp_path / "settings.json").read_bytes()
                    duplicate = subprocess.run(
                        command,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    assert duplicate.returncode == 0, duplicate.stderr
                    assert f"already running: {base}" in duplicate.stdout
                    assert (tmp_path / "settings.json").read_bytes() == before
                    assert client.get(base + "/health").status_code == 200
                    assert client.get(base + "/").status_code == 200
                    response = client.post(
                        base + "/api/server/shutdown",
                        headers={"X-CSRF-Token": client.cookies["csrf"]},
                    )
                    assert response.status_code == 200
                output, errors = process.communicate(timeout=10)
                assert process.returncode == 0, errors.decode()
                assert base in output.decode()
                with pytest.raises(OSError):
                    socket.create_connection(("127.0.0.1", int(port)), timeout=0.2)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)


def test_crashed_process_releases_lock_despite_saved_port(tmp_path):
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; from pathlib import Path; "
            "from bookmark_organization.server import running_server; "
            "\nwith running_server(Path(sys.argv[1]), 0) as listener:\n"
            " print(listener.getsockname()[1], flush=True)\n time.sleep(30)",
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip().isdigit()
        process.kill()
        process.communicate(timeout=10)
        assert (tmp_path / "server.lock").read_text().strip()
        with running_server(tmp_path, 0):
            pass
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
