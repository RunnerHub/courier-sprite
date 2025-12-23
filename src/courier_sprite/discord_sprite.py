import logging
from datetime import datetime, timedelta, timezone

import discord
import feedparser
from boltons.iterutils import first
from discord import ui
from discord.ext import tasks

from .time_sprite import TimeSprite

log = logging.getLogger(__name__)

class DiscordSprite(discord.Client):

    def arm_watch_trigger(self) -> None:
        self.watch_triggers.append(datetime.now(timezone.utc) + timedelta(minutes=self.config.get("rss").get("watch_timeout_min", 60)))
        log.info("Added watch trigger; now", len(self.watch_triggers), "active")

    def __init__(self, config, calendar, seen_posts, **kwargs):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents, **kwargs)
        self.watch_triggers: list[datetime] = []
        self.config = config
        self.calendar = calendar
        self.seen_posts = seen_posts
        interval = int(self.config.get("rss").get("check_interval_min", 5))
        self.check_posts_loop.change_interval(minutes=interval)

    async def on_ready(self):
        log.info(f'We have logged in as {self.user}')
        await self.check_posts()
        # if not check_posts_loop.is_running():
        #     check_posts_loop.start()


    async def check_posts(self) -> int:
        log.info("Checking posts at", datetime.now(timezone.utc))
        seen_posts = self.seen_posts.data
        calendar = self.calendar

        channel = self.get_channel(self.config.get("discord").get("post_channel_id"))
        if not channel:
            channel = await self.fetch_channel(self.config.get("discord").get("post_channel_id"))
        if channel is None:
            log.info("Channel not found")
            return 0

        feed = feedparser.parse(self.config.get("rss").get("url"), agent=self.config.get("rss").get("user_agent"))
        if hasattr(feed, "status"):
            log.info(f"RSS Status: {feed.status}")

        # Process oldest-first so calendar events are created in chronological order
        entries = list(feed.entries)
        entries.reverse()

        new_count = 0

        for entry in entries:
            entry_id = getattr(entry, "id", None) or entry.link

            # Already seen posts, ignore
            if entry_id in seen_posts:
                if seen_posts[entry_id]["title"] == entry.title and seen_posts[entry_id]["contents"] == entry.content:
                    continue

            modified_entry = TimeSprite.reinterpret_post(entry)

            if modified_entry.parsed_time is None:
                log.info(f"Skipping (no parsable timestamp): {modified_entry.title!r}")
            else:
                new_count += 1

                entry_unique = {"title": entry.title, "contents": entry.content}
                event_id = None
                if entry_id in seen_posts:
                    event_id = seen_posts[entry_id].get("calendar_event_id") or None
                calendar_event = calendar.put_event(modified_entry, event_id=event_id)
                entry_unique["calendar_event_id"] = calendar_event.get('id')

                view = self.build_view(modified_entry, calendar_event.get('htmlLink'), calendar.google_subscribe_link())
                if entry_id in seen_posts and seen_posts[entry_id]["discord_message_id"]:
                    original_message = await channel.fetch_message(seen_posts[entry_id]["discord_message_id"])
                    # discord_message = \
                    await original_message.edit(view=view)
                else:
                    discord_message = await channel.send(view=view)
                    entry_unique["discord_message_id"] = discord_message.id

                self.seen_posts.set(entry_id, entry_unique)
            log.info("-----")
        return new_count

    async def on_message(self, message):
        # Process only the webhook watch bot in the specific channel
        if (
                not message.author.bot
                or message.author.id != self.config.get("discord").get("webhook_watch_id")
                or message.channel.id != self.config.get("discord").get("webhook_watch_channel")
        ):
            return

        # Only react in specific channel
        if message.channel.id == self.config.get("discord").get("webhook_watch_channel"):
            try:
                await message.add_reaction("👁️")
                if not self.check_posts_loop.is_running():
                    self.check_posts_loop.start()
                self.arm_watch_trigger()
                await self.check_posts()
                await message.add_reaction("✅")
            except Exception as e:
                log.info("on_message error:", e)

    @tasks.loop(minutes=5)  # placeholder; overwritten in __init__
    async def check_posts_loop(self):
        self.watch_triggers = [t for t in self.watch_triggers if t >= datetime.now(timezone.utc)]

        if not self.watch_triggers:
            log.info("No active watch triggers; stopping loop")
            self.check_posts_loop.stop()
            return

        try:
            await self.check_posts()

        except Exception as e:
            log.info("check_posts_loop error:", e)

    @staticmethod
    def build_view(entry, calendar_event_link, calendar_link) -> ui.LayoutView:
        container = ui.Container(accent_color=0x4444CC)

        entry_tag = first(getattr(entry, "tags", None))
        subreddit = getattr(entry_tag, "label", None) or getattr(entry_tag, "term", None) or "(Unknown subreddit!)"

        header = (
                f"New Post in {subreddit}!" +
                f"\n# [{entry.title}]({entry.link})" +
                (f"\n## Time: {TimeSprite.full_discord_time(entry.parsed_time)}" if entry.parsed_time else "")
        )
        container.add_item(ui.TextDisplay(header))

        container.add_item(ui.Separator())

        for content in getattr(entry, "content", []):
            container.add_item(ui.TextDisplay(content))

        container.add_item(ui.Separator())

        author = getattr(entry, "author_detail", None)
        author_name = getattr(author, "name", "unknown") if author else "unknown"
        author_href = getattr(author, "href", None) if author else None
        footer = (
            f"Google Calendar: "
            f"[[Specific Event]]({calendar_event_link}) "
            f"[[Whole Calendar]]({calendar_link})\n"
        )
        if author_href:
            footer += f"submitted by [{author_name}]({author_href})"
        else:
            footer += f"submitted by {author_name}"
        container.add_item(ui.TextDisplay(footer))

        view = ui.LayoutView(timeout=None)
        view.add_item(container)

        return view
