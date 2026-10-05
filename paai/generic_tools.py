from datetime import datetime

from paai.context import get_user_timezone


def get_time(_raw: str = "") -> str:
    """
    Current time in the requesting user's timezone, with the zone spelled out.

    Returning a bare local time from the server (which runs in UTC) made every
    relative date wrong for part of the day: at 9pm in New York, "today" was
    already tomorrow.
    """
    tz = get_user_timezone()
    now = datetime.now(tz)
    offset = now.strftime("%z")
    return (
        f"{now.strftime('%A %Y-%m-%d %H:%M:%S')} "
        f"(timezone {tz.key}, UTC{offset[:3]}:{offset[3:]})"
    )