"""Java runtime discovery for the `doctor` diagnostic."""
from __future__ import annotations

import glob
import os
import re
import shutil
from pathlib import Path

VERSION_RE = re.compile(r'version\s+"(\d+)(?:\.(\d+))?')


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []

    def add(path: str | os.PathLike[str] | None) -> None:
        if path:
            p = Path(path)
            candidates.append(p / "bin" / "java.exe" if p.is_dir() else p)

    add(os.getenv("JAVA_HOME"))
    if java := shutil.which("java"):
        candidates.append(Path(java))

    patterns = [
        r"C:\Program Files\Java\*\bin\java.exe",
        r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
        r"C:\Program Files\Microsoft\jdk-*\bin\java.exe",
        r"C:\Program Files\Zulu\*\bin\java.exe",
        r"C:\Program Files\BellSoft\*\bin\java.exe",
        r"C:\Program Files (x86)\Java\*\bin\java.exe",
        r"%LOCALAPPDATA%\Programs\Eclipse Adoptium\*\bin\java.exe",
        r"%USERPROFILE%\.jdks\*\bin\java.exe",
    ]
    for pattern in patterns:
        for match in glob.glob(os.path.expandvars(pattern)):
            if Path(match).is_file():
                candidates.append(Path(match))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen and path.is_file():
            seen.add(key)
            unique.append(path)
    return unique


def find_java(preferred: str | None = None) -> Path | None:
    if preferred:
        path = Path(preferred)
        if path.is_file():
            return path
        if path.is_dir() and (path / "bin" / "java.exe").is_file():
            return path / "bin" / "java.exe"
    for candidate in _candidate_paths():
        return candidate
    return None


def java_major(java: Path) -> int | None:
    """Return the Java feature version, or None when it can't be determined."""
    import subprocess

    try:
        proc = subprocess.run(
            [str(java), "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
        )
        raw = (proc.stderr or "") + (proc.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return None

    match = VERSION_RE.search(raw)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):
        major = int(match.group(2))
    return major
