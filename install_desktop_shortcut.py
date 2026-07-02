#!/usr/bin/env python3
"""Create a Windows desktop shortcut for the Tax Document PDF Renamer app."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Tax Document PDF Renamer"
LAUNCHER_NAME = "start_tax_document_renamer.cmd"
SHORTCUT_NAME = f"{APP_NAME}.lnk"


def windows_desktop_dir() -> Path:
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        return Path(user_profile) / "Desktop"
    return Path.home() / "Desktop"


def default_python_executable() -> Path:
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else executable


def launcher_contents(python_executable: Path, app_path: Path) -> str:
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        f'cd /d "{app_path.parent}"\r\n'
        f'start "" "{python_executable}" "{app_path}"\r\n'
    )


def write_launcher(repo_dir: Path, python_executable: Path) -> Path:
    app_path = repo_dir / "windows_app.py"
    if not app_path.exists():
        raise FileNotFoundError(f"Could not find {app_path}")
    launcher_path = repo_dir / LAUNCHER_NAME
    launcher_path.write_text(launcher_contents(python_executable, app_path), encoding="utf-8", newline="")
    return launcher_path


def powershell_shortcut_script(shortcut_path: Path, launcher_path: Path, repo_dir: Path) -> str:
    return "\n".join([
        "$WshShell = New-Object -ComObject WScript.Shell",
        f"$Shortcut = $WshShell.CreateShortcut({json.dumps(str(shortcut_path))})",
        f"$Shortcut.TargetPath = {json.dumps(str(launcher_path))}",
        f"$Shortcut.WorkingDirectory = {json.dumps(str(repo_dir))}",
        f"$Shortcut.Description = {json.dumps(APP_NAME)}",
        "$Shortcut.Save()",
    ])


def create_shortcut(shortcut_path: Path, launcher_path: Path, repo_dir: Path) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = powershell_shortcut_script(shortcut_path, launcher_path, repo_dir)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a desktop shortcut for the Windows GUI app.")
    parser.add_argument("--desktop", type=Path, default=windows_desktop_dir(), help="Desktop folder where the shortcut is created")
    parser.add_argument("--python", type=Path, default=default_python_executable(), help="Python executable used by the shortcut")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.name != "nt":
        raise SystemExit("This shortcut installer is intended for Windows.")
    repo_dir = Path(__file__).resolve().parent
    launcher_path = write_launcher(repo_dir, args.python.resolve())
    shortcut_path = args.desktop.expanduser().resolve() / SHORTCUT_NAME
    create_shortcut(shortcut_path, launcher_path, repo_dir)
    print(shortcut_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
