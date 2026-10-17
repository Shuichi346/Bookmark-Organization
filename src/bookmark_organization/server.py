"""Reserve a loopback listener and one console server per data directory."""

import errno
import fcntl
import os
import socket
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PORTS = range(8765, 8770)


class AlreadyRunning(Exception):
    def __init__(self, url: str | None):
        self.url = url
        super().__init__(url)


class StartupError(Exception):
    pass


def bind_listener(port: int | None) -> socket.socket:
    ports = DEFAULT_PORTS if port is None else [port]
    if any(number < 0 or number > 65535 for number in ports):
        raise StartupError("Port must be between 0 and 65535.")
    for number in ports:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", number))
            listener.listen(128)
            return listener
        except OSError as exc:
            listener.close()
            if exc.errno != errno.EADDRINUSE:
                raise StartupError(
                    f"Cannot listen on 127.0.0.1:{number}: {exc}"
                ) from exc
    choices = "8765-8769" if port is None else str(port)
    raise StartupError(
        f"No available port on 127.0.0.1 ({choices}). "
        "Choose another port with BOOKMARK_PORT."
    )


@contextmanager
def running_server(directory: Path, port: int | None):
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / "server.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            saved_port = lock.read().strip()
            url = (
                f"http://127.0.0.1:{int(saved_port)}"
                if saved_port.isascii()
                and saved_port.isdecimal()
                and len(saved_port) <= 5
                and 1 <= int(saved_port) <= 65535
                else None
            )
            raise AlreadyRunning(url) from exc
        # Never unlink this file: other starters must lock the same inode.
        lock.truncate(0)
        try:
            with bind_listener(port) as listener:
                lock.write(str(listener.getsockname()[1]))
                lock.flush()
                yield listener
        finally:
            # Closing the file releases the OS lock, including after crashes.
            lock.seek(0)
            lock.truncate()
