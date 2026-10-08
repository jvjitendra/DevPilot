from dataclasses import dataclass
import re

DANGEROUS_PATTERNS = [
    r"\bgit\s+push\s+--force\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\brm\s+-rf\b",
    r"\bDROP\s+DATABASE\b",
    r"\bDROP\s+TABLE\b",
]

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?[^\s'\"]+",
]

@dataclass
class ScopeResult:
    allowed: bool
    reason: str


def validate_command(command: str) -> ScopeResult:
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return ScopeResult(False, "Command requires explicit human intervention.")
    return ScopeResult(True, "Command passed the basic safety gate.")


def redact_secrets(text: str) -> str:
    return re.sub(r"(?i)((?:api[_-]?key|secret|token|password)\s*[=:]\s*)([^\s,;]+)", r"\1[REDACTED]", text)
