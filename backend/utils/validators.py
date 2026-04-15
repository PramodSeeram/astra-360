import re

def validate_pan(pan: str) -> bool:
    return bool(re.match(r'[A-Z]{5}[0-9]{4}[A-Z]', pan))

def get_pan_type(pan: str) -> str:
    type_map = {
        'P': 'Individual',
        'C': 'Company',
        'H': 'HUF',
        'F': 'Firm'
    }
    return type_map.get(pan[3], 'Unknown')