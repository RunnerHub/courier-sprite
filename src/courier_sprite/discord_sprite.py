import json
import logging
import re
from datetime import datetime
from typing import Any

import discord
from discord import ui

from .calendar_sprite import GCalendar

log = logging.getLogger(__name__)

JSON_RE = re.compile(r"```json\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)

class DiscordSprite(discord.Client):
    def __init__(self, config, calendar, seen_posts, **kwargs):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents, **kwargs)
        self.watch_triggers: list[datetime] = []
        self.config = config
        self.calendar: GCalendar = calendar
        self.seen_posts = seen_posts

    async def on_ready(self):
        log.info(f'We have logged in as {self.user}')


    async def on_message(self, message):
        # Process only the webhook watch bot in the specific channel
        if (
                not message.author.bot
                or message.author.id != self.config.get("discord").get("webhook_watch_id")
                or message.channel.id != self.config.get("discord").get("webhook_watch_channel")
        ):
            return

        try:
            raw = JSON_RE.match(message.content)
            payload: dict[str, Any] = json.loads(raw.group(1))
        except Exception as e:
            log.info("on_message error:", e)
            return

        if "created" in payload:
            data = payload["created"]
            await self.upsert_announcement(data)
        elif "updated" in payload:
            data = payload["updated"]
            await self.upsert_announcement(data)
        elif "deleted" in payload:
            data = payload["deleted"]
            await self.delete_announcement(data)
        else:
            log.warning(f"unsupported operation: {payload}")

    def build_view(self, calendar_event):
        container = ui.Container(accent_color=0x4444CC)
        calendar_event_link = calendar_event.get('htmlLink')
        google_subscribe_link = self.calendar.google_subscribe_link()

        footer = (
            f"Added to Google Calendar: "
            f"[[Specific Event]]({calendar_event_link}) "
            f"[[Whole Calendar]]({google_subscribe_link})\n"
        ) if calendar_event_link or google_subscribe_link else ""
        container.add_item(ui.TextDisplay(footer))

        view = ui.LayoutView(timeout=None)
        view.add_item(container)

        return view

    async def upsert_announcement(self, data):
        reddit_id = data.get("id")
        post_state = self.seen_posts.get(reddit_id, {})
        prev_calendar_event = post_state.get("calendar_event_id", None)
        prior_post_id = post_state.get("discord_post_id", None)
        calendar_event = self.calendar.put_event(data, prev_calendar_event)
        source_discord_post = data.get("discordPost")
        dest_channel_id = self.config.get("discord").get("post_channel_id")
        channel = self.get_channel(dest_channel_id) or await self.fetch_channel(dest_channel_id)
        view = self.build_view(calendar_event)
        if prior_post_id:
            prior_post = await channel.fetch_message(prior_post_id)
            new_post = await prior_post.edit(view=view)
        else:
            parent_post = await channel.fetch_message(source_discord_post)
            new_post = await parent_post.reply(view=view)
        post_state["calendar_event_id"] = calendar_event.get('id')
        post_state["discord_post_id"] = new_post.id
        self.seen_posts[reddit_id] = post_state

    async def delete_announcement(self, data) -> None:
        reddit_id = data.get("id")
        post_state = self.seen_posts.get(reddit_id, {})
        prior_post_id = post_state.get("discord_post_id", None)
        dest_channel_id = self.config.get("discord").get("post_channel_id")
        channel = self.get_channel(dest_channel_id) or await self.fetch_channel(dest_channel_id)
        prior_post = await channel.fetch_message(prior_post_id)
        await prior_post.delete()
