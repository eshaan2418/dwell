#!/usr/bin/env python3
"""Static "no raw audio" checker for the Dwell firmware (stdlib only).

Fails (exit 1) if raw microphone samples could flow anywhere except the level DSP:

R1  I2S read calls (i2s_read, i2s_channel_read, I2S.read...) appear only in ALLOWED_I2S_FILES.
R2  Taint flow: the buffer filled by an I2S read (and anything assigned/aliased/memcpy'd from it)
    may only be passed to ALLOWED_CONSUMERS (the DSP entry points, sizeof). Any statement that
    combines a tainted identifier with an output sink (SD/File write, Serial, HTTP/WiFi client,
    UDP, queues, logger) or returns it is a violation.
R3  DSP module files contain no I/O: no Arduino/SD/WiFi/stdio includes, no print/write calls.
R4  The logger interfaces accept only record structs: every log(...) parameter must be one of
    the *Record types and no sample-pointer types appear in those headers.
R5  No WAV/PCM writer anywhere in firmware/ (RIFF/WAVE headers, .wav paths, audio/wav MIME, ...).

Usage: python3 tools/check_no_raw_audio.py [--root firmware/]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CODE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".ino"}
TEXT_EXT = CODE_EXT | {".py", ".ini", ".txt", ".json", ".cfg", ".toml", ".yaml", ".yml", ".sh", ".mk", ""}
SKIP_DIRS = {".pio", "build", "__pycache__", ".pytest_cache", ".vscode"}
SELF_FILES = {"tools/check_no_raw_audio.py", "tools/test_check_no_raw_audio.py"}

ALLOWED_I2S_FILES = {"src/audio_input.cpp"}
DSP_FILES = {
    "lib/dwell_core/audio_dsp.h",
    "lib/dwell_core/audio_dsp.cpp",
    "lib/dwell_core/level_stats.h",
    "lib/dwell_core/level_stats.cpp",
}
LOGGER_HEADERS = {"lib/dwell_core/log_sink.h", "src/logger.h"}
RECORD_TYPES = {"MinuteRecord", "SecondRecord", "OctaveRecord", "EventRecord"}

# I2S read functions -> index of the destination-buffer argument.
I2S_READS = {"i2s_read": 1, "i2s_read_bytes": 1, "i2s_channel_read": 1, "I2S.read": 0, "I2S.readBytes": 0}
ALLOWED_CONSUMERS = {"process_i2s_frames", "process_samples", "sizeof"} | {
    k.split(".")[-1] for k in I2S_READS
}
TRANSPARENT_CALLS = {"static_cast", "reinterpret_cast", "const_cast", "if", "while", "for", "switch"}
PROPAGATORS = {"memcpy": (1, 0), "memmove": (1, 0), "copy": (0, 2), "copy_n": (0, 2)}  # name: (src, dst)

SINK_RE = re.compile(
    r"\bSerial\d?\b|\bFile\b|\bSD(_MMC)?\s*\.|\bSPIFFS\b|\bLittleFS\b|\.\s*write\s*\(|\.\s*print(ln|f)?\s*\("
    r"|\bf?printf\s*\(|\bfwrite\s*\(|\bfputs\s*\(|\bHTTPClient\b|\.\s*(POST|PUT|sendRequest)\s*\("
    r"|\bWiFi\w*\b|\bclient\b|\budp\b|\besp_http_client_\w+|\bsend(to)?\s*\(|\bxQueueSend\w*\s*\("
    r"|\bxRingbufferSend\w*\s*\(|\bxStreamBufferSend\s*\(|\blog\w*\s*\(|\b\w*[Ll]ogger\w*\b|\bstd::(cout|cerr)\b"
)
DSP_FORBIDDEN_RE = re.compile(
    r"#\s*include\s*[<\"](Arduino\.h|SD\.h|FS\.h|SPI\.h|WiFi\w*\.h|HTTPClient\.h|stdio\.h|cstdio|iostream|fstream"
    r"|driver/[^>\"]*|esp_[^>\"]*|freertos/[^>\"]*)[>\"]"
    r"|\bSerial\b|\bf?printf\s*\(|\bfwrite\s*\(|\bfopen\s*\(|\bstd::(cout|cerr|ofstream)\b|\bFile\b"
)
SAMPLE_PTR_RE = re.compile(r"\b(u?int(8|16|32)_t|float|double|void|short|int)\s*(const\s*)?\*")
WAV_RES = [
    re.compile(r"[\"']RIFF[\"']"),
    re.compile(r"[\"']WAVE(fmt )?[\"']"),
    re.compile(r"[\"']fmt [\"']"),
    re.compile(r"\.wav\b[\"']", re.I),
    re.compile(r"audio/(x-)?wav|audio/L(16|24)|audio/pcm", re.I),
    re.compile(r"\bwave\.open\b|\bscipy\.io\.wavfile\b|\bimport\s+soundfile\b|\bdr_?wav\b", re.I),
    re.compile(r"\b(wav|pcm)_?writer\b|\bwrite_?(wav|pcm)\w*\s*\(", re.I),
]
KEYWORDS = {
    "const",
    "static",
    "volatile",
    "unsigned",
    "signed",
    "char",
    "short",
    "int",
    "long",
    "float",
    "double",
    "void",
    "auto",
    "size_t",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "sizeof",
    "static_cast",
    "reinterpret_cast",
    "const_cast",
    "std",
    "return",
    "nullptr",
    "if",
    "else",
    "while",
    "for",
    "do",
    "switch",
    "case",
    "continue",
    "break",
    "true",
    "false",
}
IDENT_RE = re.compile(r"[A-Za-z_]\w*")


@dataclass
class Violation:
    path: str
    line: int
    rule: str
    msg: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.msg}"


def strip_comments_and_strings(src: str) -> str:
    """Blank out comments and string/char literals, preserving offsets and newlines."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != "\n":
                out[k] = " "
        i = j
    return "".join(out)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def split_args(text: str, open_pos: int) -> tuple[list[tuple[str, int]], int]:
    """Split the argument list starting at text[open_pos] == '(' -> ([(arg, start)], close_pos)."""
    depth, start, args = 0, open_pos + 1, []
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append((text[start:i], start))
                return args, i
        elif ch == "," and depth == 1:
            args.append((text[start:i], start))
            start = i + 1
    return args, len(text)


def idents(expr: str) -> set[str]:
    return {m.group(0) for m in IDENT_RE.finditer(expr)} - KEYWORDS


def enclosing_calls(code: str, pos: int) -> list[str]:
    """Names of the calls whose parentheses enclose pos, innermost first (within the statement)."""
    names, depth, i = [], 0, pos - 1
    while i >= 0 and code[i] not in ";{}":
        ch = code[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                m = re.search(r"([A-Za-z_]\w*)\s*(<[^()]*>)?\s*$", code[:i])
                names.append(m.group(1) if m else "")
            else:
                depth -= 1
        i -= 1
    return names


def statement_bounds(code: str, pos: int) -> tuple[int, int]:
    s = max(code.rfind(";", 0, pos), code.rfind("{", 0, pos), code.rfind("}", 0, pos)) + 1
    ends = [x for x in (code.find(";", pos), code.find("{", pos), code.find("}", pos)) if x >= 0]
    return s, (min(ends) if ends else len(code))


def find_i2s_calls(code: str):
    for name, idx in I2S_READS.items():
        pat = re.escape(name).replace(r"\.", r"\s*\.\s*")
        for m in re.finditer(r"(?<![\w.])" + pat + r"\s*\(", code):
            args, _ = split_args(code, m.end() - 1)
            yield name, m.start(), (args[idx][0] if idx < len(args) else "")


def taint_file(rel: str, code: str) -> list[Violation]:
    tainted: set[str] = set()
    for _, _, buf in find_i2s_calls(code):
        tainted |= idents(buf)
    if not tainted:
        return []
    # Propagate through assignments / initialisations / memcpy-style copies until a fixpoint.
    changed = True
    while changed:
        changed = False
        for stmt in re.split(r"[;{}]", code):
            m = re.match(r"\s*(.*?)(?<![=!<>+\-*/%&|^])=(?!=)(.*)$", stmt, re.S)
            init = re.match(
                r"\s*[\w:<>\s\*&]+?\b([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*[({](.*)[)}]\s*$", stmt, re.S
            )
            lhs = rhs = None
            if m:
                lhs_ids = [
                    x for x in IDENT_RE.findall(re.sub(r"\[[^\]]*\]", "", m.group(1))) if x not in KEYWORDS
                ]
                lhs, rhs = (lhs_ids[-1] if lhs_ids else None), m.group(2)
            elif init:
                lhs, rhs = init.group(1), init.group(3)
            if lhs and rhs and lhs not in KEYWORDS and idents(rhs) & tainted and lhs not in tainted:
                tainted.add(lhs)
                changed = True
        for name, (src_i, dst_i) in PROPAGATORS.items():
            for m in re.finditer(r"\b" + name + r"\s*\(", code):
                args, _ = split_args(code, m.end() - 1)
                if max(src_i, dst_i) < len(args) and idents(args[src_i][0]) & tainted:
                    new = idents(args[dst_i][0]) - tainted
                    if new:
                        tainted |= new
                        changed = True
    out: list[Violation] = []
    seen: set[tuple[int, str]] = set()
    for ident in sorted(tainted):
        for m in re.finditer(r"\b" + re.escape(ident) + r"\b", code):
            s, e = statement_bounds(code, m.start())
            stmt = code[s:e]
            ln = line_of(code, m.start())
            calls = [c for c in enclosing_calls(code, m.start()) if c not in TRANSPARENT_CALLS]
            problem = None
            if calls and calls[0] not in ALLOWED_CONSUMERS and calls[0] not in PROPAGATORS:
                problem = (
                    f"raw sample buffer '{ident}' passed to '{calls[0]}()' (only DSP entry points allowed)"
                )
            elif SINK_RE.search(stmt) and not (calls and calls[0] in ALLOWED_CONSUMERS - {"sizeof"}):
                problem = f"raw sample buffer '{ident}' used in a statement with an output sink"
            elif re.match(r"\s*return\b", stmt):
                problem = f"raw sample buffer '{ident}' returned (escapes the capture scope)"
            if problem and (ln, ident) not in seen:
                seen.add((ln, ident))
                out.append(Violation(rel, ln, "R2", problem))
    return out


def check_logger_header(rel: str, code: str) -> list[Violation]:
    out = []
    for m in re.finditer(r"\blog\s*\(", code):
        args, _ = split_args(code, m.end() - 1)
        for arg, start in args:
            types = idents(arg) - {"dwell", "r", "record", "override"}
            if not types & RECORD_TYPES:
                out.append(
                    Violation(
                        rel, line_of(code, start), "R4", f"logger log() accepts non-record '{arg.strip()}'"
                    )
                )
    for m in SAMPLE_PTR_RE.finditer(code):
        out.append(
            Violation(
                rel, line_of(code, m.start()), "R4", f"sample-pointer type '{m.group(0)}' in logger API"
            )
        )
    return out


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS):
            yield p, p.relative_to(root).as_posix()


def check(root: Path) -> tuple[list[Violation], int]:
    violations: list[Violation] = []
    n = 0
    for path, rel in iter_files(root):
        if rel in SELF_FILES or path.suffix.lower() not in TEXT_EXT:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n += 1
        for rx in WAV_RES:  # R5 on raw text (string literals matter here)
            for m in rx.finditer(raw):
                violations.append(
                    Violation(rel, line_of(raw, m.start()), "R5", f"WAV/PCM writer pattern '{m.group(0)}'")
                )
        if path.suffix.lower() not in CODE_EXT:
            continue
        code = strip_comments_and_strings(raw)
        for name, pos, _ in find_i2s_calls(code):
            if rel not in ALLOWED_I2S_FILES:
                violations.append(
                    Violation(
                        rel,
                        line_of(code, pos),
                        "R1",
                        f"I2S read '{name}' outside {sorted(ALLOWED_I2S_FILES)}",
                    )
                )
        violations += taint_file(rel, code)
        if rel in DSP_FILES:
            for m in DSP_FORBIDDEN_RE.finditer(raw_includes(raw, code)):
                violations.append(
                    Violation(
                        rel, line_of(code, m.start()), "R3", f"I/O in DSP module: '{m.group(0).strip()}'"
                    )
                )
        if rel in LOGGER_HEADERS:
            violations += check_logger_header(rel, code)
    for req in sorted(ALLOWED_I2S_FILES | LOGGER_HEADERS):
        if not (root / req).exists():
            violations.append(
                Violation(req, 0, "CFG", "expected file missing (update checker configuration)")
            )
    return violations, n


def raw_includes(raw: str, code: str) -> str:
    """Comment-stripped code, but with #include lines restored (their <...>/"..." were blanked)."""
    lines_raw, lines_code = raw.split("\n"), code.split("\n")
    pairs = zip(lines_raw, lines_code, strict=True)
    return "\n".join(r if re.match(r"\s*#\s*include", c) else c for r, c in pairs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="firmware directory")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    violations, n = check(root)
    for v in violations:
        print(v)
    if violations:
        print(f"FAIL: {len(violations)} raw-audio privacy violation(s) in {root}")
        return 1
    print(f"OK: {n} files scanned in {root}; raw I2S samples reach only the level DSP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
