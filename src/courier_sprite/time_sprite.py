
import copy
import logging
import re
from datetime import datetime

import dateutil.parser as dparser
from bs4 import BeautifulSoup
from markdownify import markdownify

log = logging.getLogger(__name__)

class TimeSprite:
    def __init__(self):
        pass


    DATE_PATTERN = r"(?P<date>\w{1,4}[-./]\w{1,4}[-./]\w{1,4})"
    TIME_PATTERN = r"\d{1,2}[:\.h]?\d{2}\s*(?:[aApP][mM])?"
    ZONE_PATTERN = r"(?:Z|[a-zA-Z]{2,5})"

    # Helpers
    BRACKET_OPENED = r"[\[\(\{\<]"
    BRACKET_CLOSED = r"[\]\)\}\>]"
    SPACES = r"\s*"

    # Sometimes people put the timezone in brackets, but if we're not careful, it could match the outer brackets, too.
    TZ_BRACKET = rf"(?:{BRACKET_OPENED}{ZONE_PATTERN}{BRACKET_CLOSED})"
    TZ_CAPTURE = rf"(?:{TZ_BRACKET}|{ZONE_PATTERN})"

    # Time with optional timezone
    TIME_WITH_ZONE = rf"(?P<time>{TIME_PATTERN}{SPACES}{TZ_CAPTURE}?)"

    # ISO format puts a T in between instead of a space
    DATE_TIME_RE = re.compile(
        rf"{BRACKET_OPENED}?{SPACES}(?P<datetime>{DATE_PATTERN}(?:{SPACES}|T){TIME_WITH_ZONE}){SPACES}{BRACKET_CLOSED}?"
    )
    TIME_DATE_RE = re.compile(
        rf"{BRACKET_OPENED}?{SPACES}(?P<datetime>{TIME_WITH_ZONE}{SPACES}{DATE_PATTERN}){SPACES}{BRACKET_CLOSED}?"
    )
    TIME_24_RE = re.compile(r"24(?P<rest>[:.h]?\d{2}\s*(?:[aApP][mM])?)")
    TIME_3DIG_RE = re.compile(r"^\d{3}\b\s*(?:[aApP][mM])?")


    @staticmethod
    def normalize_time(t: str) -> str:
        t = t.strip()
        t = re.sub(TimeSprite.BRACKET_OPENED, "", t)
        t = re.sub(TimeSprite.BRACKET_CLOSED, "", t)
        if TimeSprite.TIME_24_RE.match(t):
            t = "00" + t[2:]

        if TimeSprite.TIME_3DIG_RE.match(t):
            t = "0" + t

        return t


    @staticmethod
    def discordify_timestamp(time: datetime, f: str):
        return f"<t:{int(time.timestamp())}:{f}>"


    @staticmethod
    def full_discord_time(time: datetime):
        return f"{TimeSprite.discordify_timestamp(time, 'F')} ({TimeSprite.discordify_timestamp(time, 'R')})"


    @staticmethod
    def _replace_datetimes(text: str, time_state: dict) -> str:
        # time_state: {"first_time": datetime | None, "title_time": datetime | None}
        def repl(match: re.Match) -> str:
            norm_time = TimeSprite.normalize_time(match.group("time"))
            combined = f"{match.group('date')} {norm_time}"
            log.info(f"Timestamp parsed: {combined}")
            dt = dparser.parse(combined, fuzzy=True)

            # capture the very first dt once, to feed back to caller
            if time_state["first_time"] is None:
                # but if there is already a time in the title, and first body time doesn't match, mark it accordingly
                if time_state["title_time"] is not None and dt != time_state["title_time"]:
                    time_state["first_time"] = dt
                    return f"Time in body is different: {TimeSprite.full_discord_time(dt)}"
                # otherwise there is no time in the title, or the first body time matches it
                else:
                    time_state["first_time"] = dt
                    return ""

            # later matches → Discord timestamp
            return TimeSprite.full_discord_time(dt)

        text = TimeSprite.DATE_TIME_RE.sub(repl, text)
        text = TimeSprite.TIME_DATE_RE.sub(repl, text)
        return text


    # ===== CUSTOM PARSING =====
    @staticmethod
    def parse_timestamp_from_entry(title, contents):
        state = {"first_time": None, "title_time": None}

        try:
            title = TimeSprite._replace_datetimes(title, state)
        except Exception as e:
            log.error("Error parsing title:", e)

        state["title_time"] = state["first_time"]
        state["first_time"] = None

        for i, content in enumerate(contents):
            try:
                contents[i] = TimeSprite._replace_datetimes(content, state)
            except Exception as e:
                log.error("Error parsing content:", e)

        parsed_time = state["title_time"] if state["title_time"] is not None else state["first_time"]

        return title, contents, parsed_time


    @staticmethod
    def reinterpret_post(entry):
        """
        Leaves the original entry untouched.
        """
        modified_entry = copy.deepcopy(entry)
        title = modified_entry.title
        contents = getattr(modified_entry, "content", [])
        for i in range(0, len(contents)):
            soup = BeautifulSoup(contents[i].value, "html.parser")
            div_html = soup.find("div", attrs={'class': 'md'}) or None
            if div_html:
                contents[i] = markdownify(str(div_html))
                # Make empty quote lines contiguous
                contents[i] = re.sub(r">$", "> ", contents[i])

        title, contents, parsed_time = TimeSprite.parse_timestamp_from_entry(title, contents)
        modified_entry.title = title
        modified_entry.content = contents
        modified_entry.parsed_time = parsed_time
        return modified_entry
