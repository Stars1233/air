"""Documentation integration tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_documentation_builds(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
