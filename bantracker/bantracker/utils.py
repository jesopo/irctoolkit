import re
from typing import Optional

SECONDS_MINUTE = 60
SECONDS_HOUR   = SECONDS_MINUTE*60
SECONDS_DAY    = SECONDS_HOUR  *24
SECONDS_WEEK   = SECONDS_DAY   *7


REGEX_PRETTYTIME = re.compile(
    r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.I)

def from_pretty_time(time: str) -> Optional[int]:
    seconds = 0

    match = re.match(REGEX_PRETTYTIME, time)
    if match:
        seconds += int(match.group(1) or 0)*SECONDS_WEEK
        seconds += int(match.group(2) or 0)*SECONDS_DAY
        seconds += int(match.group(3) or 0)*SECONDS_HOUR
        seconds += int(match.group(4) or 0)*SECONDS_MINUTE
        seconds += int(match.group(5) or 0)

    if seconds > 0:
        return seconds
    return None
