import re
import json
from typing import Tuple, Optional

# if DB not available
_FALLBACK_FORMATS = [
    {"segments": [7, 4, 7],    "is_active": True},
    {"segments": [3, 2, 4, 7], "is_active": True},
]


def _build_regex(segments: list) -> str:
    parts = [f"\\d{{{n}}}" for n in segments]
    return r"^" + r"-".join(parts) + r"$"


def validate_bin_number(
    bin_number: str,
    formats_json: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    
    if not bin_number or not bin_number.strip():
        return True, None  

    value = bin_number.strip()

    try:
        raw_formats = json.loads(formats_json) if formats_json else _FALLBACK_FORMATS
    except Exception:
        raw_formats = _FALLBACK_FORMATS

    active_formats = [f for f in raw_formats if f.get("is_active", True)]

    if not active_formats:
        return True, None   

    for fmt in active_formats:
        pattern = _build_regex(fmt["segments"])
        if re.match(pattern, value):
            return True, None

    examples = []
    for fmt in active_formats:
        examples.append("-".join(["0" * s for s in fmt["segments"]]))

    return False, f"Invalid BIN format. Expected one of: {', '.join(examples)}"