import re

def validate_pan(pan: str) -> bool:
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    return bool(re.match(pattern, pan))

def get_pan_type(pan: str) -> str:
    if not validate_pan(pan):
        return None
    fourth_char = pan[3]
    types = {
        'P': 'Individual',
        'C': 'Company',
        'H': 'HUF',
        'F': 'Firm'
    }
    return types.get(fourth_char, 'Unknown')