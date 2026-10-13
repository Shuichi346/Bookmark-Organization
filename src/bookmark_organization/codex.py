"""Isolated, subscription-authenticated Codex CLI analysis."""

import asyncio
import json
import os
import shutil
import signal
from pathlib import Path
from tempfile import TemporaryDirectory

from bookmark_organization.schemas import CODEX_MODEL, CODEX_REASONING, AppError


class CodexCLI:
    def __init__(self, timeout: float):
        self.timeout = timeout or None

    @staticmethod
    def environment() -> dict[str, str]:
        # Keep the user's CLI auth store, but never inherit provider credentials
        # or alternate endpoints from the web server's environment.
        return {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "HOME",
                "CODEX_HOME",
                "TMPDIR",
                "LANG",
                "LC_ALL",
                "LC_CTYPE",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
            }
        }

    async def run(
        self,
        args: list[str],
        directory: str,
        *,
        prompt: str | None = None,
        timeout: float | None = 30,
    ) -> tuple[int, str, str]:
        executable = shutil.which("codex")
        if not executable:
            raise AppError("codex_missing", 503)
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                cwd=directory,
                env=self.environment(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise AppError("codex_missing", 503) from exc
        communication = asyncio.create_task(
            process.communicate(prompt.encode() if prompt is not None else None)
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communication), timeout=timeout
            )
            return process.returncode or 0, stdout.decode(), stderr.decode()
        except TimeoutError as exc:
            raise AppError("codex_timeout", 503) from exc
        finally:
            # Worker cancellation and response deadlines stop the whole CLI
            # process group, including any child processes, before cleanup.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(asyncio.shield(communication), timeout=2)
                except TimeoutError:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            await communication

    async def require_chatgpt(self, directory: str):
        code, out, err = await self.run(["login", "status"], directory)
        if code or "Logged in using ChatGPT" not in out + err:
            raise AppError("codex_login_required", 503)

    async def models(self) -> list[str]:
        with TemporaryDirectory(prefix="bookmark-codex-") as directory:
            await self.require_chatgpt(directory)
            code, out, err = await self.run(
                [
                    "debug",
                    "models",
                    "-c",
                    'model_provider="openai"',
                    "-c",
                    'forced_login_method="chatgpt"',
                ],
                directory,
            )
        if code:
            raise self.failure(out + err)
        try:
            catalog = json.loads(out)["models"]
            return (
                [CODEX_MODEL] if any(m["slug"] == CODEX_MODEL for m in catalog) else []
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError("codex_failed", 503) from exc

    @staticmethod
    def failure(detail: str) -> AppError:
        text = detail.lower()
        if "max_output_tokens" in text:
            return AppError("analysis_invalid")
        if any(
            word in text
            for word in (
                "usage_limit",
                "usage limit",
                "rate_limit",
                "rate limit",
                "429",
            )
        ):
            return AppError("codex_limit", 503)
        if any(
            word in text
            for word in ("unauthorized", "token expired", "401", "not logged in")
        ):
            return AppError("codex_login_required", 503)
        if "model_not_found" in text or "model is not supported" in text:
            return AppError("model_unavailable", 503)
        return AppError("codex_failed", 503)

    async def chat(self, messages: list[dict], schema: dict) -> tuple[str, str]:
        with TemporaryDirectory(prefix="bookmark-codex-") as directory:
            await self.require_chatgpt(directory)
            output_path = Path(directory) / "result.json"
            instructions_path = Path(directory) / "instructions.txt"
            # Verified Luna subscription runs did not complete with the CLI's
            # constrained-output route. Request JSON and validate in LocalAI.
            instructions_path.write_text(
                messages[0]["content"]
                + "\nRequired JSON schema:\n"
                + json.dumps(schema, ensure_ascii=False),
                encoding="utf-8",
            )
            # No app repository, prior thread, user instructions, hooks or tools
            # are needed to classify the single supplied page.
            overrides = {
                "model_provider": "openai",
                "forced_login_method": "chatgpt",
                "model_reasoning_effort": CODEX_REASONING,
                "web_search": "disabled",
                "approval_policy": "never",
                "project_doc_max_bytes": 0,
                "model_instructions_file": str(instructions_path),
                "log_dir": directory,
                "features": {
                    name: False
                    for name in (
                        "shell_tool",
                        "unified_exec",
                        "shell_snapshot",
                        "apps",
                        "plugins",
                        "remote_plugin",
                        "multi_agent",
                        "memories",
                        "hooks",
                        "browser_use",
                        "computer_use",
                        "image_generation",
                        "view_image",
                        "code_mode",
                        "code_mode_host",
                        "skill_search",
                        "goals",
                        "unbounded_connection_retries",
                    )
                },
            }
            args = [
                "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--strict-config",
                "--model",
                CODEX_MODEL,
                "--output-last-message",
                str(output_path),
                "--json",
            ]
            for key, value in overrides.items():
                # JSON objects are not TOML tables; emit feature overrides singly.
                if isinstance(value, dict):
                    for name, enabled in value.items():
                        args.extend(["-c", f"{key}.{name}={json.dumps(enabled)}"])
                else:
                    args.extend(["-c", f"{key}={json.dumps(value)}"])
            args.append("-")
            prompt = messages[1]["content"]
            code, out, err = await self.run(
                args, directory, prompt=prompt, timeout=self.timeout
            )
            if code:
                raise self.failure(out + err)
            try:
                events = [json.loads(line) for line in out.splitlines() if line.strip()]
                if not any(e.get("type") == "turn.completed" for e in events) or any(
                    e.get("type") == "turn.failed" for e in events
                ):
                    raise self.failure(out)
                return output_path.read_text(encoding="utf-8"), "stop"
            except (OSError, ValueError, TypeError) as exc:
                raise AppError("analysis_invalid") from exc
