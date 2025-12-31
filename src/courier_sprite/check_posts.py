import logging
import re
from datetime import datetime, timezone

import feedparser
from boltons.iterutils import first
from discord import ui, MediaGalleryItem

from courier_sprite.time_sprite import TimeSprite

log = logging.getLogger(__name__)
async def check_posts(client) -> int:
    log.info("Checking posts at %s", datetime.now(timezone.utc))
    seen_posts = client.seen_posts.data

    channel = client.get_channel(client.config.get("discord").get("post_channel_id"))
    if not channel:
        channel = await client.fetch_channel(client.config.get("discord").get("post_channel_id"))
    if channel is None:
        log.info("Channel not found")
        return 0

    feed = feedparser.parse(client.config.get("rss").get("url"), agent=client.config.get("rss").get("user_agent"))
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
            calendar_event_link = ""
            google_subscribe_link = ""
            if entry_id in seen_posts:
                event_id = seen_posts[entry_id].get("calendar_event_id") or None
            if client.calendar:
                calendar_event = client.calendar.put_event(modified_entry, event_id=event_id)
                entry_unique["calendar_event_id"] = calendar_event.get('id')
                calendar_event_link = calendar_event.get('htmlLink')
                google_subscribe_link = client.calendar.google_subscribe_link()

            view = build_view(modified_entry, calendar_event_link, google_subscribe_link)
            log.debug(view.to_components())
            if entry_id in seen_posts and seen_posts[entry_id]["discord_message_id"]:
                original_message = await channel.fetch_message(seen_posts[entry_id]["discord_message_id"])
                # discord_message = \
                await original_message.edit(view=view)
            else:
                discord_message = await channel.send(view=view)
                entry_unique["discord_message_id"] = discord_message.id

            client.seen_posts.set(entry_id, entry_unique)
        log.info("-----")
    return new_count

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

    # Can't have more than 30 visual components, so we can't be generous with discord ui separators
    body_separator = "\n━━━━━━━━━━━━━━━━━━━━\n"
    raw_blocks = []
    for content in getattr(entry, "content", []):
        for part in content.split("---"):
            part = part.strip()
            if part:
                raw_blocks.append(part)

    body_text = body_separator.join(raw_blocks)

    url_re = re.compile(r"<(https?://[^\s'\"]+\.(?:jpg|jpeg|png|gif|bmp|webp|svg)(?:\?[^\s'\"]*)?)>")
    url_separated = url_re.split(body_text)
    texts = url_separated[0::2] # slice every 2nd element starting at 0
    urls = url_separated[1::2] # slice every 2nd element starting at 1

    if len(urls) < 5: # max 5 inline images TODO: Configurable
        container.add_item(ui.TextDisplay(texts[0].strip()))
        for url_part, text_part in zip(urls, texts[1:]):
            container.add_item(ui.MediaGallery(MediaGalleryItem(url_part)))
            container.add_item(ui.TextDisplay(text_part.strip()))
    else:
        container.add_item(ui.TextDisplay(body_text))

    container.add_item(ui.Separator())

    author = getattr(entry, "author_detail", None)
    author_name = getattr(author, "name", "unknown") if author else "unknown"
    author_href = getattr(author, "href", None) if author else None
    footer = (
        f"Google Calendar: "
        f"[[Specific Event]]({calendar_event_link}) "
        f"[[Whole Calendar]]({calendar_link})\n"
    ) if calendar_event_link or calendar_link else ""
    if author_href:
        footer += f"submitted by [{author_name}]({author_href})"
    else:
        footer += f"submitted by {author_name}"
    container.add_item(ui.TextDisplay(footer))

    view = ui.LayoutView(timeout=None)
    view.add_item(container)

    return view
