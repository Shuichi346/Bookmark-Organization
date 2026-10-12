"""Run a requested finite verification unit with bounded subprocess output."""

import argparse
import subprocess

CHECKS = {
    "ruff": ["uv", "run", "--locked", "ruff", "check", "src", "tests"],
    "format": ["uv", "run", "--locked", "ruff", "format", "--check", "src", "tests"],
    "ty": ["uv", "run", "--locked", "ty", "check", "src"],
    "lint": ["npm", "run", "lint"],
    "typecheck": ["npm", "run", "typecheck"],
    "build": ["npm", "run", "build"],
    "unit": [
        "uv",
        "run",
        "--locked",
        "pytest",
        "-q",
        "tests/test_bookmarks.py",
        "tests/test_fetching.py",
        "tests/test_llm.py",
        "tests/test_settings.py",
        "tests/test_jobs.py",
        "tests/test_organizing.py",
        "tests/test_i18n.py",
    ],
    "smoke": ["uv", "run", "--locked", "python", "tests/smoke_app.py"],
    "models": [
        "uv",
        "run",
        "--locked",
        "python",
        "tests/smoke_local_models.py",
        "--settings",
        "data/settings.json",
    ],
}
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unit", choices=CHECKS)
    args = parser.parse_args()
    limit = (
        1200
        if args.unit == "models"
        else 180
        if args.unit in {"unit", "smoke"}
        else 120
    )
    result = subprocess.run(
        CHECKS[args.unit], capture_output=True, text=True, timeout=limit
    )
    print((result.stdout + result.stderr)[-14000:])
    raise SystemExit(result.returncode)
