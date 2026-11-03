"""Bounded incremental PII redaction. Keeps overlap to catch split patterns."""
from __future__ import annotations
import re

EMAIL = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+")
SSN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
OVERLAP = 320  # exceeds supported email (254) and card (37) pattern lengths.

def luhn(value: str) -> bool:
    digits = [int(x) for x in value if x.isdigit()]
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2:
            digit *= 2
            if digit > 9: digit -= 9
        total += digit
    return bool(13 <= len(digits) <= 19 and total % 10 == 0)

def redact(text: str) -> str:
    text = EMAIL.sub(lambda m: "[REDACTED]" if len(m.group()) <= 254 else m.group(), text)
    text = SSN.sub("[REDACTED]", text)
    return CARD.sub(lambda m: "[REDACTED]" if luhn(m.group()) else m.group(), text)

class IncrementalRedactor:
    def __init__(self, overlap: int = OVERLAP):
        self.buffer = ""
        self.overlap = overlap
    def feed(self, text: str, final: bool = False) -> str:
        self.buffer += text
        if final:
            result = redact(self.buffer); self.buffer = ""; return result
        if len(self.buffer) <= self.overlap: return ""
        cut = len(self.buffer) - self.overlap
        # A complete PII token can straddle the tentative cut. Move the cut to
        # the beginning of such a match so no prefix of that token escapes.
        for pattern in (EMAIL, SSN, CARD):
            for match in pattern.finditer(self.buffer):
                if pattern is EMAIL and len(match.group()) > 254:
                    continue
                if pattern is CARD and not luhn(match.group()):
                    continue
                if match.start() < cut < match.end():
                    cut = match.start()
        safe, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return redact(safe)
