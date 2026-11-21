"""Shared helpers for the script tests.

The scripts under test live in hyphenated or same-named files
(`plan-issues.py`, two `build.py`s), so they cannot be imported by module name.
`load_script` loads one by path under a unique name, and `run_script` runs one
as the CLI the skills actually call.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
from types import ModuleType

# Importing a skill's script would otherwise leave `scripts/__pycache__/` in the
# skill directory, which scripts/validate.py reports as an unreferenced file.
sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"


def load_script(path: pathlib.Path, name: str) -> ModuleType:
    """Import the script at `path` as a module called `name`."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(
    path: pathlib.Path, *args: str, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the script at `path` with this interpreter; never raises on a non-zero exit."""
    return subprocess.run(
        [sys.executable, str(path), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
