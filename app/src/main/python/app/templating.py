from datetime import datetime, date, time
import jdatetime
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory="templates")


def _to_jdatetime(value):
    """Convert date, datetime, time, or supported string values to Jalali datetime."""

    if value in (None, "", "-"):
        return None

    # Already Jalali datetime
    if isinstance(value, jdatetime.datetime):
        return value

    # Already Jalali date
    if isinstance(value, jdatetime.date):
        return jdatetime.datetime(
            value.year,
            value.month,
            value.day
        )

    # Python datetime
    if isinstance(value, datetime):
        return jdatetime.datetime.fromgregorian(
            datetime=value
        )

    # Python date
    if isinstance(value, date):
        return jdatetime.datetime.fromgregorian(
            date=value
        )

    # Python time
    if isinstance(value, time):
        base = datetime.combine(
            date.today(),
            value
        )

        return jdatetime.datetime.fromgregorian(
            datetime=base
        )

    # Convert to string
    s = str(value).strip()

    # Time-only strings
    for fmt in (
        "%H:%M:%S",
        "%H:%M",
    ):
        try:
            parsed_time = datetime.strptime(
                s,
                fmt
            ).time()

            base = datetime.combine(
                date.today(),
                parsed_time
            )

            return jdatetime.datetime.fromgregorian(
                datetime=base
            )

        except ValueError:
            continue

    # Date / datetime strings
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",

        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ):
        try:
            parsed = datetime.strptime(
                s,
                fmt
            )

            return jdatetime.datetime.fromgregorian(
                datetime=parsed
            )

        except ValueError:
            continue

    return None


def format_money(value) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0"

    return "{:,.0f}".format(value)


def format_date(value) -> str:
    jd = _to_jdatetime(value)

    if jd:
        return jd.strftime("%Y/%m/%d")

    return "-"


def format_time(value) -> str:
    jd = _to_jdatetime(value)

    if jd:
        return jd.strftime("%H:%M")

    return "-"


def format_datetime(value) -> str:
    jd = _to_jdatetime(value)

    if jd:
        return jd.strftime("%Y/%m/%d - %H:%M")

    return "-"


# Register Jinja2 filters
templates.env.filters["money"] = format_money
templates.env.filters["jdate"] = format_date
templates.env.filters["jtime"] = format_time
templates.env.filters["jdatetime"] = format_datetime