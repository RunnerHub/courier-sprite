import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from .check_posts import check_posts

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
        await check_posts(self)
        # if not check_posts_loop.is_running():
        #     check_posts_loop.start()

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
                await check_posts(self)
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
            await check_posts(self)

        except Exception as e:
            log.info("check_posts_loop error:", e)
