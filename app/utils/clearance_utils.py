from datetime import datetime

STICKER_CUTOFF_MONTH = 11

def get_sticker_year() -> int:
    now = datetime.now()
    if now.month >= STICKER_CUTOFF_MONTH:
        return now.year + 1
    return now.year