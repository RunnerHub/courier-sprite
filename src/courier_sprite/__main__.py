#!/usr/bin/env python3
from .calendar_sprite import GCalendar
from .discord_sprite import DiscordSprite
from .file_sprite import StateFile, ConfigFile

# ===== MAIN =====
if __name__ == "__main__":
    # Load configs
    config_file = ConfigFile("config.json")
    discord_token = ConfigFile("discord_secret.json").data["discord_token"]

    # initialize google calendar service
    calendar_state: StateFile = StateFile("calendar_state.json")
    gcal: GCalendar = GCalendar(config_file.get("google_calendar"), calendar_state)
    calendar_id: str = gcal.calendar_id()

    # initialize seen posts
    seen_posts = StateFile("seen_posts.json")

    client = DiscordSprite(config_file, calendar=gcal, seen_posts=seen_posts)

    client.run(discord_token)
