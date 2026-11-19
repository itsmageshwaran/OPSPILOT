"""
Input Sanitization & Injection Defense Suite for OpsPilot.
Demonstrates:
1. Regex detection of SQL Injection vectors (UNION SELECT, DROP TABLE, comment truncations)
2. HTML entity encoding to prevent Cross-Site Scripting (XSS)
3. Safe query parameter sanitization
"""

import re
import html
from typing import Tuple, List

# Compiled regex patterns for detecting dangerous SQL injection vectors
SQL_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"(\b(UNION(\s+ALL)?)\b\s+SELECT\b)", re.IGNORECASE),
    re.compile(r"(;\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE)\b)", re.IGNORECASE),
    re.compile(r"(--|/\*|\*/|#)", re.IGNORECASE),
    re.compile(r"(\bOR\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"])", re.IGNORECASE),
    re.compile(r"(\bEXEC(\s+XP_)?\b)", re.IGNORECASE),
    re.compile(r"(';\s*SHUTDOWN\b)", re.IGNORECASE),
]


def detect_sql_injection(query: str) -> Tuple[bool, str]:
    """
    Scans an input string for known SQL injection signatures.
    Returns (is_suspicious: bool, reason: str).
    """
    if not query:
        return False, "Empty query string."

    for pattern in SQL_INJECTION_PATTERNS:
        match = pattern.search(query)
        if match:
            matched_text = match.group(0)
            return True, f"Dangerous SQL injection pattern detected: '{matched_text}'"

    return False, "Input passed SQL injection safety checks."


def sanitize_html(text_input: str) -> str:
    """
    Encodes special characters to HTML entities, defusing stored and reflected XSS:
    < -> &lt;
    > -> &gt;
    & -> &amp;
    " -> &quot;
    ' -> &#x27;
    """
    if not text_input:
        return ""
    return html.escape(text_input, quote=True)


def sanitize_input(value: str, max_length: int = 2000) -> str:
    """
    Cleans raw user input:
    - Trims excess whitespace
    - Removes null bytes
    - Enforces length boundary
    - Escapes HTML entities
    """
    if not value:
        return ""
    cleaned = value.replace("\x00", "").strip()[:max_length]
    return sanitize_html(cleaned)
