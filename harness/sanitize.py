import re

_HIDDEN = [re.compile(r"<!--.*?-->", re.S), re.compile(r"[​‌‍⁠﻿]"),
           re.compile(r"<[^>]*(display:\s*none|visibility:\s*hidden|color:\s*#?fff)[^>]*>.*?</[^>]+>", re.S | re.I)]
_IMPERATIVE = re.compile(
    r"[^.!?\n]*\b(ignore (all |any )?(previous|prior) instructions|as an ai|ai (assistant|agent)|you must approve|"
    r"approve this vendor|call approve_vendor|pre-?approved by compliance|system prompt)\b[^.!?\n]*[.!?]?", re.I)
_URL_INSTR = re.compile(r"[^.!?\n]*\b(visit|go to|open|fetch)\b[^.!?\n]*https?://\S+[^.!?\n]*[.!?]?", re.I)


def sanitize(text: str, rules: list[str]) -> str:
    if "drop_hidden_text" in rules:
        for pat in _HIDDEN:
            text = pat.sub(" ", text)
    if "strip_imperatives" in rules:
        text = _IMPERATIVE.sub(" ", text)
    if "strip_urls_in_instructions" in rules:
        text = _URL_INSTR.sub(" ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip() if rules else text
