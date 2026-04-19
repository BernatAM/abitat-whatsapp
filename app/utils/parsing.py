import re


YES_WORDS = {
    "si",
    "sí",
    "claro",
    "vale",
    "ok",
    "okay",
    "necesito",
    "si necesito",
    "sí necesito",
    "por supuesto",
}
NO_WORDS = {
    "no",
    "ahora no",
    "de momento no",
    "mas adelante",
    "más adelante",
    "todavia no",
    "todavía no",
}

TONER_TYPE_MAP = {
    "ecologico": "ecologico",
    "ecológico": "ecologico",
    "habitat": "ecologico",
    "ábitat": "ecologico",
    "abitat": "ecologico",
    "ecologico habitat": "ecologico",
    "ecológico habitat": "ecologico",
    "ecológico ábitat": "ecologico",
    "original": "original",
    "compatible": "compatible",
    "toner_type_ecologico": "ecologico",
    "toner_type_original": "original",
    "toner_type_compatible": "compatible",
}

EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)


def normalize_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def normalize_key(text: str) -> str:
    cleaned = normalize_whitespace(text).lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return cleaned


def normalize_yes_no(text: str) -> str | None:
    value = normalize_key(text)
    if value in YES_WORDS:
        return "yes"
    if value in NO_WORDS:
        return "no"
    yes_markers = ["si", "claro", "vale", "ok", "necesito", "por supuesto"]
    no_markers = ["ahora no", "de momento no", "mas adelante", "todavia no"]
    if any(marker in value for marker in yes_markers):
        return "yes"
    if any(marker in value for marker in no_markers):
        return "no"
    return None


def normalize_toner_type(text: str) -> str | None:
    value = normalize_key(text)
    return TONER_TYPE_MAP.get(value)


def extract_units(text: str) -> int | None:
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def extract_email(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    if not match:
        return None
    return match.group(1)


def strip_email_from_text(text: str, email: str | None) -> str:
    if not email:
        return normalize_whitespace(text)
    return normalize_whitespace(text.replace(email, " "))

