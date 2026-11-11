#!/usr/bin/env python3
"""home-index: local-first file index for ~.

Script mode walks the home dir (ignores caches/venvs/build output) and
emits INDEX.md + index.json. Optional --llm classifies filenames only
via OpenRouter ZDR route; file contents are never read or sent.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
OUT_MD = Path(__file__).resolve().parent / "INDEX.md"
OUT_JSON = Path(__file__).resolve().parent / "index.json"

# Directories skipped wholesale: caches, session-internal state whose
# directory names embed the local username and leak it into the output.
IGNORED = {
    ".cache", ".cargo", "Steam", "node_modules", ".venv", "venv",
    "__pycache__", ".git", "dayflow", ".npm", ".rustup",
    ".bun", ".var", ".mozilla", ".vscode", ".steam", ".ollama",
    "pnpm", "mise", ".local/share/pnpm", ".local/share/mise",
    ".local/share/Steam", "Library", "Pictures/Screenshots/Library",
    ".claude/projects", ".cursor/projects", ".factory/sessions",
    ".gemini/history", ".grok/memory", ".grok/memory-v2", ".hermes/skills",
}
MAX_DEPTH = 4


def detect_lanes() -> dict[str, Path]:
    """Auto-detect lanes from the local layout (no hardcoded names)."""
    lanes: dict[str, Path] = {}
    for label, tail in (("Work", HOME / "Work"), ("Projects", HOME / "Projects")):
        if tail.is_dir():
            for child in sorted(tail.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    lanes[label] = child
                    break
    for label, path in (("Agents", HOME / "Agents"), ("Screenshots", HOME / "Pictures" / "Screenshots")):
        if path.exists():
            lanes[label] = path
    # Omarchy setups: expose the config dir when present.
    if (HOME / ".config" / "omarchy").is_dir():
        lanes["Omarchy config"] = HOME / ".config" / "omarchy"
    return lanes


def _is_ignored(path: Path, root: Path) -> bool:
    """Ignored if any path part matches a cached/generated dir name."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    for part in rel.parts:
        if part in IGNORED or part in {".cache", "node_modules", "__pycache__", ".git", ".venv", "venv"}:
            # Never ignore the repo itself under Projects/*/home-index.
            if rel.parts[0] == "Projects" and "home-index" in rel.parts:
                continue
            return True
    # Path-qualified entries (e.g. .local/share/Steam).
    for needle in IGNORED:
        if "/" in needle and rel.as_posix() == needle:
            return True
    return False


def _redact(text: str) -> str:
    """Scrub usernames/hostnames from any display string (filenames included)."""
    import getpass
    import socket
    tokens = {getpass.getuser(), HOME.name, socket.gethostname()}
    for token in sorted(tokens, key=len, reverse=True):
        if token and len(token) >= 2:
            text = text.replace(token, "<user>")
    return text


def _rel(entry: Path, root: Path) -> str:
    """Home-relative label (no username/hostname leaks into the output)."""
    return _redact(entry.relative_to(root).as_posix() + ("/" if entry.is_dir() else ""))


def scan_root(root: Path, max_depth: int = 1) -> dict[str, list[str]]:
    """Walk root to max_depth, never following symlinked dirs (no double count).

    - max_depth=1: old behavior (root children only, 8-child summaries).
    - max_depth>=2: recursive dir counts + first-8 children per dir.
    No content reads. Symlink loops are impossible (links are listed,
    never descended). Permission errors are collected, not raised.
    """
    result: dict[str, list[str]] = {}
    errors: list[str] = []
    seen: set[str] = set()  # realpaths already descended

    def walk(current: Path, depth: int) -> None:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError as e:
            errors.append(f"{_rel(current, root)}: {e}")
            return
        for entry in entries:
            if _is_ignored(entry, root):
                continue
            if entry.is_symlink():
                target = entry.readlink()
                try:
                    result.setdefault("Symlinks", []).append(
                        f"{_rel(entry, root)} -> {target.relative_to(root)}"
                    )
                except ValueError:
                    result.setdefault("Symlinks", []).append(f"{_rel(entry, root)} -> {target.name}")
                continue
            if entry.is_dir():
                try:
                    children = sorted(p.name for p in entry.iterdir())
                except OSError as e:
                    children = []
                    errors.append(f"{_rel(entry, root)}: {e}")
                real = str(entry.resolve())
                if real in seen:
                    result.setdefault("Dirs", []).append(
                        f"{_rel(entry, root)} (already indexed; alias)"
                    )
                    continue
                seen.add(real)
                # children names can themselves embed usernames; redact them.
                shown = _redact(", ".join(children[:8]))
                label = f"{_rel(entry, root)} ({len(children)} entries)" + (
                    f": {shown}" if children else ""
                )
                result.setdefault("Dirs", []).append(label)
                if max_depth and depth < max_depth:
                    walk(entry, depth + 1)
            else:
                result.setdefault("Files", []).append(_rel(entry, root))

    walk(root, 1)
    if errors:
        result["Errors"] = errors
    return result


def lane_report(root: Path) -> list[str]:
    lines = []
    for label, path in detect_lanes().items():
        count = sum(1 for _ in path.iterdir())
        # Never print the detected dir name (it can be a username).
        lines.append(f"- {label}: `~/{label.replace(' ', '').lower()}/...` ({count} entries)")
    return lines


def render_md(scan: dict[str, list[str]], stamp: str, root: Path) -> str:
    out = [
        "# INDEX — home file index",
        "",
        f"Generated {stamp} by `index.py` (script mode; see README.md).",
        "",
        "## Lanes",
        "",
        *lane_report(root),
        "",
        "## Home root",
        "",
    ]
    for section, items in scan.items():
        out.append(f"### {section}")
        out.append("")
        out.extend(f"- {i}" for i in items)
        out.append("")
    return "\n".join(out)


def llm_classify(rows: list[str]) -> None:
    """Optional OpenRouter classification of names only (ZDR route)."""
    if not rows:
        return
    import subprocess
    import urllib.request

    try:
        key = subprocess.run(
            ["omaseal", "get", "openrouter", "default"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        key = ""
    if not key:
        print("No omaseal openrouter/default key; skipping --llm.", file=sys.stderr)
        return
    if "--yes" not in sys.argv and input("Send filenames to OpenRouter (ZDR route)? [y/N] ").lower() != "y":
        print("Aborted --llm.")
        return
    payload = json.dumps({
        "model": "openrouter/auto",
        "messages": [{"role": "user", "content":
                      "Classify each path as work|personal|agent|app|other. Return JSON list.\n"
                      + "\n".join(rows[:200])}],
        "provider": {"data_collection": "deny"},
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        print(resp.read().decode()[:2000])


def main() -> int:
    ap = argparse.ArgumentParser(description="Local-first home index.")
    ap.add_argument("--print", action="store_true", help="Print stats only.")
    ap.add_argument("--llm", action="store_true", help="Also classify names via OpenRouter ZDR.")
    ap.add_argument("--yes", action="store_true", help="Skip llm confirmation.")
    ap.add_argument("--depth", type=int, default=3, choices=(1, 3),
                    help="Scan depth: 1=root only (default pre-v0.2), 3=+3 levels (default).")
    args = ap.parse_args()

    scan = scan_root(HOME, max_depth=args.depth)
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    total = sum(len(v) for v in scan.values())
    print(f"Scanned ~ depth {args.depth}: {total} entries.")
    for section, items in scan.items():
        print(f"  {section}: {len(items)}")

    if args.llm:
        names = [f"{k}: {v}" for k, vs in scan.items() for v in vs]
        llm_classify(names)

    if args.print:
        return 0
    OUT_JSON.write_text(json.dumps({"generated": stamp, "scan": scan}, indent=2, sort_keys=True))
    OUT_MD.write_text(render_md(scan, stamp, HOME))
    print(f"Wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
