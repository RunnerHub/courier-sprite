#!/usr/bin/env python3
import logging
import os

from google.auth.exceptions import MalformedError

from .calendar_sprite import GCalendar
from .discord_sprite import DiscordSprite
from .file_sprite import StateFile, ConfigFile

# ===== MAIN =====
if __name__ == "__main__":
    # Set up logging from env
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    )

    # Load configs
    config_file = ConfigFile("config.json")
    discord_token = ConfigFile("discord_secret.json").data["discord_token"]

    # initialize google calendar service
    calendar_state: StateFile = StateFile("calendar_state.json")
    google_secret = ConfigFile("calendar_secret.json")
    gcal: GCalendar | None = GCalendar(config_file.get("google_calendar"), calendar_state, google_secret=google_secret)

    try:
        calendar_id: str = gcal.calendar_id()
    except MalformedError:
        # No calendar thing
        gcal = None

    # initialize seen posts
    seen_posts = StateFile("seen_posts.json")

    client = DiscordSprite(config_file, calendar=gcal, seen_posts=seen_posts)

    client.run(discord_token)
