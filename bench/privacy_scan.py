"""Privacy scan over the whole git history and the working tree (Definition of Done item 5).

Fails (exit 1) on: any path under data/private/; raw video/audio/photo files; blobs > 5 MB;
street-address-like strings; secrets (private keys, API tokens, Wi-Fi passwords); a real firmware
config.h. False positives can be allowlisted (with a reason) in docs/privacy_allowlist.txt.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from core.provenance import REPO, write_result

MEDIA = re.compile(r"\.(mp4|mov|m4v|avi|mkv|webm|heic|heif|jpe?g|wav|pcm|raw|flac|mp3|m4a|aac|ply|splat|e57)$", re.I)
ALLOWED_MEDIA = re.compile(r"^(app/test/fixtures/.*\.wav)$")
ADDRESS = re.compile(
    r"\b\d{1,5}\s+(?:[A-Z][a-z]+\.?\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Crescent|Cres|"
    r"Lane|Ln|Court|Ct|Place|Pl|Way|Terrace|Gardens|Gdns|Parkway|Pkwy|Circle|Square|Sq)\b\.?(?:\s*(?:Unit|Apt|#)\s*\d+)?"
)
SECRETS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{32,}"),
    re.compile(r"(?i)xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r'(?i)#define\s+DWELL_WIFI_PASSWORD\s+"(?!your|changeme|")[^"]+"'),
]
MAX_BYTES = 5 * 1024 * 1024


def _git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=REPO).decode(errors="replace")


def allowlist() -> list[str]:
    p = REPO / "docs" / "privacy_allowlist.txt"
    if not p.exists():
        return []
    return [ln.split("#")[0].strip() for ln in p.read_text().splitlines() if ln.split("#")[0].strip()]


def scan_blob(path: str, data: bytes, allow: list[str]) -> list[str]:
    issues = []
    if path.startswith("data/private/") or "/private/" in path:
        issues.append(f"private path committed: {path}")
    if MEDIA.search(path) and not ALLOWED_MEDIA.match(path):
        issues.append(f"raw media file: {path}")
    if path.endswith("firmware/include/config.h"):
        issues.append(f"real firmware config committed: {path}")
    if len(data) > MAX_BYTES:
        issues.append(f"large file ({len(data) // 1024} KiB): {path}")
    if b"\0" in data[:8000]:
        return issues
    text = data.decode(errors="replace")
    for m in ADDRESS.finditer(text):
        if not any(a in m.group(0) for a in allow):
            line = text.count("\n", 0, m.start()) + 1
            # never echo the matched text: a real address must not be copied into results/ or logs
            issues.append(f"address-like string in {path}:{line}")
    for rx in SECRETS:
        if rx.search(text):
            issues.append(f"secret-like pattern {rx.pattern[:30]!r} in {path}")
    return issues


def main() -> int:
    allow = allowlist()
    issues: set[str] = set()
    # all blobs reachable from any ref (history)
    objs = _git("rev-list", "--all", "--objects").splitlines()
    pairs = [ln.split(" ", 1) for ln in objs if " " in ln]
    n_hist = 0
    if pairs:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=REPO,
            input="\n".join(p[0] for p in pairs).encode(),
            capture_output=True,
            check=True,
        )
        buf = proc.stdout
        i = 0
        for _sha, path in pairs:
            nl = buf.index(b"\n", i)
            header = buf[i:nl].decode().split()
            size = int(header[2]) if len(header) > 2 else 0
            body = buf[nl + 1 : nl + 1 + size]
            i = nl + 1 + size + 1
            if header[1] != "blob":
                continue
            n_hist += 1
            issues.update(scan_blob(path, body, allow))
    # working tree files that would be committed (tracked + untracked, not ignored)
    files = _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    for f in files:
        p = REPO / f
        if p.is_file():
            issues.update(scan_blob(f, p.read_bytes(), allow))
    ok = not issues
    write_result(
        "privacy/scan.json",
        {"ok": ok, "n_history_blobs": n_hist, "n_tree_files": len(files), "issues": sorted(issues)},
        seed=None,
        config={"max_bytes": MAX_BYTES},
        data_hash="n/a",
        data_kind="none",
    )
    for s in sorted(issues):
        print("PRIVACY:", s)
    print(f"privacy scan: {'OK' if ok else 'FAIL'} ({n_hist} history blobs, {len(files)} tree files)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


_ = Path
