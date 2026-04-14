import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")

PAN_TYPE_MAP = {
    "P": "Individual",
    "C": "Company",
    "H": "HUF",
    "F": "Firm",
    "A": "AOP",
    "T": "Trust",
    "B": "BOI",
    "L": "Local Authority",
    "J": "Artificial Juridical Person",
    "G": "Government",
}


def validate_pan(pan: str) -> bool:
    return bool(PAN_REGEX.match(pan))


def get_pan_type(pan: str) -> str:
    fourth_char = pan[3]
    return PAN_TYPE_MAP.get(fourth_char, "Other")


def validate_phone(phone: str) -> bool:
    return bool(PHONE_REGEX.match(phone))
