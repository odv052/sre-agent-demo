import re
from pathlib import Path

from langchain_core.tools import tool

from sre_agent.models import LogRecord

ROOT = Path(__file__).parent.parent.resolve()
LOG_FILE = ROOT / "app.log"
REPORTS_DIR = ROOT / "reports"
IGNORED = {".venv", "__pycache__", ".idea", ".git", "reports"}

RECORD_START = re.compile(r"^(\d{4}-\d{2}-\d{2} [\d:,]+) (\w+) \[([^\]]+)\] trace=(\S+) (.*)")
FRAME = re.compile(r'File "(.+?)", line (\d+), in (\S+)')


def parse_log(path: Path = LOG_FILE) -> list[LogRecord]:
    """Parse the log file into records, gluing traceback lines to the record they belong to."""
    records: list[LogRecord] = []
    if not path.exists():
        return records
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if match := RECORD_START.match(line):
            records.append(LogRecord(lineno, *match.groups()))
        elif records:  # continuation of a multi-line record (traceback)
            records[-1].text += "\n" + line
    return records


def project_frames(text: str) -> list[tuple[str, int, str]]:
    """Extract (file, line, func) stack frames that point to our own code, skipping libraries."""
    frames = []
    for file, line, func in FRAME.findall(text):
        resolved = Path(file).resolve()
        if resolved.is_relative_to(ROOT) and not IGNORED & set(resolved.relative_to(ROOT).parts):
            frames.append((str(resolved.relative_to(ROOT)), int(line), func))
    return frames


def _safe_path(path: str) -> Path:
    """Resolve a path inside the project; refuse anything outside it or in ignored directories."""
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT) or IGNORED & set(resolved.relative_to(ROOT).parts):
        raise ValueError(f"access denied: {path}")
    return resolved


@tool
def list_files() -> str:
    """List source files of the project."""
    files = [
        str(file_path.relative_to(ROOT)) for file_path in ROOT.rglob("*")
        if file_path.is_file() and file_path.suffix in {".py", ".toml", ".txt", ".cfg", ".yaml", ".yml"}
           and not IGNORED & set(file_path.relative_to(ROOT).parts)
    ]
    return "\n".join(sorted(files))


@tool
def read_file(path: str, start: int = 1, end: int = 0) -> str:
    """Read a project file with line numbers. `end=0` means up to 200 lines from `start`."""
    try:
        lines = _safe_path(path).read_text().splitlines()
    except Exception as error:
        return f"error: {error}"
    end = end or start + 199
    return "\n".join(f"{lineno:>4} | {lines[lineno - 1]}" for lineno in range(max(1, start), min(end, len(lines)) + 1))


@tool
def search_code(pattern: str) -> str:
    """Regex search over project source files. Returns `file:line: text` matches."""
    out = []
    for file in list_files.invoke({}).splitlines():
        for lineno, line in enumerate((ROOT / file).read_text().splitlines(), 1):
            if re.search(pattern, line):
                out.append(f"{file}:{lineno}: {line.strip()}")
    return "\n".join(out[:30]) or "no matches"


@tool
def get_trace(trace_id: str) -> str:
    """
    Get ALL log lines of one request by its trace_id, in order. Logs of concurrent requests
    are interleaved in app.log, so this is the only reliable way to see what one request did.
    """
    trace_id = trace_id.removeprefix("trace=")
    lines = []
    for record in parse_log():
        if record.trace_id == trace_id:
            text = record.text.splitlines()
            if len(text) > 6:  # traceback: keep only the tail
                text = [text[0], "  ...", *text[-4:]]
            lines.append(f"{record.lineno}: {record.ts} {record.level} {text[0]}")
            lines += text[1:]
    return "\n".join(lines) or f"no log lines for trace {trace_id}"


@tool
def search_logs(pattern: str) -> str:
    """
    Regex search over app.log. Returns total match count and up to 20 last matching lines.
    Every line contains trace=<id>; pass it to get_trace to see the whole request.
    """
    lines = LOG_FILE.read_text().splitlines()
    hits = [f"{lineno}: {line}" for lineno, line in enumerate(lines, 1) if re.search(pattern, line)]
    return f"{len(hits)} matches\n" + "\n".join(hits[-20:])


def step(name: str, text: str = ""):
    """Print a colored pipeline step header."""
    print(f"\n\033[1;36m━━ {name} ━━\033[0m {text}")
