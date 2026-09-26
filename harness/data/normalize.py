import re
import unicodedata

_SUFFIXES = {
    "LLC", "LTD", "LIMITED", "CO", "COMPANY", "CORP", "CORPORATION", "INC", "JSC", "PJSC", "OJSC", "CJSC", "OAO", "OOO",
    "ZAO", "PAO", "AO", "GMBH", "AG", "SA", "SAS", "SRL", "BV", "NV", "PLC", "FZE", "FZCO", "FZ", "LLP", "PTE", "SDN", "BHD",
    "PUBLIC", "JOINT", "STOCK", "OPEN", "CLOSED", "THE",
}


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).upper()
    s = re.sub(r"[^\w\s&]", " ", s)
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    return " ".join(tokens)


def is_latin(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)
