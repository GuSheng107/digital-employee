from __future__ import annotations

import re


def extract_bullets(content: str) -> list[str]:
    bullets: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            bullet_text = stripped[2:].strip()
            if bullet_text:
                bullets.append(bullet_text)
        elif re.match(r"^\d+\.\s+", stripped):
            bullet_text = re.sub(r"^\d+\.\s+", "", stripped).strip()
            if bullet_text:
                bullets.append(bullet_text)
    return bullets


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def estimate_tokens(text: str) -> int:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5) + other_chars // 4 + 1


PRIORITY_MAP: dict[str, float] = {
    "explicit": 10.0,
    "work": 8.0,
    "profile": 6.0,
    "documents": 5.0,
    "timeline": 4.0,
    "rules": 3.0,
    "inbox": 2.0,
    "changelog": 1.0,
}

NEGATION_PATTERNS = [
    r"不(?:要|能|可以|应该|需要|用|使)",
    r"禁止",
    r"never|don'?t|must not|should not",
]


def has_negation(text: str) -> bool:
    import re
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
