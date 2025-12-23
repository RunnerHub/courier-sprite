# RunnerHub Courier Sprite

Grabs Reddit posts, parses out timestamps, converts them to Markdown, and puts them in discord and on Google Calendar.

Config directory should be something like: `~/.config/courier-sprite/`

You will need 3 files in there:
- google calendar service account secret: `calendar_secret.json`
  - this is the secret file downloaded from your Google Cloud IAM. Do not create OAuth credentials; use a service account.
- a discord bot token: `discord_secret.json`
  - (the file should contain `{"discord_token": "YOUR_BOT_TOKEN"}`)
- a config file matching the format in `example_config.json`
  - `rss`:
    - `watch_timeout_min`: How long it will wait for a new post to appear when it gets a ping from the Reddit webhook.
    - `check_interval_min`: How frequently to check for new posts in that time. 5min is okay as long as it's not always on; 15min is better if it's likely to be constantly checking, so it doesn't get rate limited. 
    - `url`: The url of the RSS feed. usually /r/your_subreddit_here/new/.rss
    - `user_agent`: the user_agent of the bot. Reddit is stricter with anonymous or common user_agents
  - `google_calendar`:
    - `calendar_name`: The name of the calendar. The sprite will search for a calendar by this name. If it doesn't find one, it will create one.
    - `timezone`: Time zone. Must be a valid Google time zone, so most cities don't work.
    - `event_duration_min`: How long the scheduled events should show up as in Google Calendar. 240 min = 4 hours, a common default.
    - `admin_email`: This email (if it has a Google account associated with it) will be given edit permissions for the calendar, so they can correct it if the bot bugs out.
  - `discord`: 
    - `post_channel_id`: Channel ID the bot will post in.
    - `webhook_watch_id`: Webhook the Reddit bot will use to notify when there is a new post.
    - `webhook_watch_channel`: Channel the Reddit bot will post the notification in.

The bot will also need access to `~/.local/state` to create its state files; these files are where it tracks what posts it has seen, and where it caches the calendar ID.

Once everything is in place, you should be able to just 
```
pip install -e .
python -m courier_sprite
```
Or use a venv if versions are finicky.