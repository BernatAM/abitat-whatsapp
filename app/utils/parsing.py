import re
import unicodedata
from datetime import date


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
    "yes",
}
NO_WORDS = {
    "no",
    "ahora no",
    "de momento no",
    "mas adelante",
    "más adelante",
    "todavia no",
    "todavía no",
    "no",
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
    "ecologico abitat": "ecologico",
    "abitat toner ecologico": "ecologico",
    "original": "original",
    "compatible": "compatible",
    "toner_type_ecologico": "ecologico",
    "toner type ecologico": "ecologico",
    "toner_type_original": "original",
    "toner type original": "original",
    "toner_type_compatible": "compatible",
    "toner type compatible": "compatible",
}

EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)
NUMERIC_DATE_RE = re.compile(r"\b([0-3]?\d)[/\-.]([01]?\d)(?:[/\-.](\d{2,4}))?\b")
TEXTUAL_DATE_RE = re.compile(
    r"\b([0-3]?\d)\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+de\s+(\d{2,4}))?\b",
    re.IGNORECASE,
)

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

SLOT_MARKERS = {
    "manana",
    "mañana",
    "tarde",
    "mediodia",
    "mediodía",
    "primera hora",
    "ultima hora",
    "última hora",
}
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])(?::|\.|h)([0-5]\d)?\b")


def normalize_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def normalize_key(text: str) -> str:
    cleaned = normalize_whitespace(text).lower()
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    return normalize_whitespace(cleaned)


def normalize_yes_no(text: str) -> str | None:
    value = normalize_key(text)
    if value == "yes":
        return "yes"
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


def has_valid_pickup_slot(text: str, today: date | None = None) -> bool:
    today = today or date.today()
    return _extract_future_date(text, today) is not None and _has_time_slot(text)


def _extract_future_date(text: str, today: date) -> date | None:
    numeric_match = NUMERIC_DATE_RE.search(text)
    if numeric_match:
        parsed = _build_date(
            day=int(numeric_match.group(1)),
            month=int(numeric_match.group(2)),
            year_text=numeric_match.group(3),
            today=today,
        )
        if parsed is not None:
            return parsed

    textual_match = TEXTUAL_DATE_RE.search(normalize_key(text))
    if textual_match:
        parsed = _build_date(
            day=int(textual_match.group(1)),
            month=MONTHS[textual_match.group(2)],
            year_text=textual_match.group(3),
            today=today,
        )
        if parsed is not None:
            return parsed

    return None


def _build_date(day: int, month: int, year_text: str | None, today: date) -> date | None:
    year = today.year
    if year_text:
        year = int(year_text)
        if year < 100:
            year += 2000
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed < today and year_text is None:
        try:
            parsed = date(year + 1, month, day)
        except ValueError:
            return None
    return parsed if parsed >= today else None


def _has_time_slot(text: str) -> bool:
    value = normalize_key(text)
    if TIME_RE.search(value):
        return True
    return any(marker in value for marker in SLOT_MARKERS)
