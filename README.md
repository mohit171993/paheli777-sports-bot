# Paheli777

Telegram bot for **Paheli777**. It follows live cricket and football, and runs a daily prediction game with a leaderboard.

There is no live TV. Points are for the leaderboard only.

## What it does

- Welcome screen in English and Hindi, with settings for language
- Cricket and football menus: live scores, upcoming fixtures, results, and news
- Team search with `/team India` or `/team Arsenal`
- Daily prediction board for the day's notable cricket and football matches
- Winner pick, plus an optional exact score (`2-1` or `137/8-139/4`)
- Picks lock at kick-off, and also once a match is live or finished
- Finished matches are scored from Highlightly: **3** points for the correct winner, **+2** for the exact score
- Weekly and all-time leaderboards, plus personal stats and a correct-winner streak
- A reminder before kick-off for subscribers, and for anyone who has predicted before, when they still have not picked
- Match-alert subscribe toggle, admin broadcast, and a small start-link lead funnel
- Website button driven by `BRAND_URL`

Notable matches prefer major competitions (IPL, internationals, Premier League, Champions League, ISL, and similar). If a day has none of those, the board falls back to the earliest matches so there is still something to play.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `BOT_TOKEN` | yes | Telegram bot token from @BotFather |
| `ADMIN_USER_ID` | yes for admin commands | Numeric Telegram user id. `/admin`, `/broadcast`, `/leads`, and `/reminders` are refused for everyone else. |
| `HIGHLIGHTLY_API_KEY` | yes for scores | Highlightly All Sports key, sent as `x-rapidapi-key` |
| `DATABASE_URL` | yes on Railway | `postgresql://` or `postgres://` URL. Empty locally uses sqlite file `paheli777.db`. |
| `BRAND_URL` | yes once the site exists | Public website. `.env.example` uses `https://example.com` until the real URL is known. |

Optional:

- `APP_TIMEZONE` (default `Asia/Kolkata`) — “today”, the weekly board, and quiet hours
- `REMINDER_LEAD_MINUTES` (default `45`) — how long before kick-off a reminder can go out

Copy `.env.example` to `.env` for local runs. Do not commit `.env`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in BOT_TOKEN, ADMIN_USER_ID, HIGHLIGHTLY_API_KEY, BRAND_URL
python bot.py --check
python bot.py
```

`--check` creates the database schema and builds the bot, including the reminder and scoring jobs, without calling Telegram. `python bot.py` long-polls Telegram. Leave `DATABASE_URL` empty locally and the bot stores data in `paheli777.db`.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover winner and exact-score points, the kick-off lock, notable-match selection, Highlightly score parsing, and sqlite settle/leaderboard behaviour.

## Railway

This bot is a worker. It does not serve HTTP.

1. Create a Railway project and add Postgres.
2. Deploy this repo as a service. `railway.json` sets the start command to `python bot.py` and `Procfile` exposes a `worker` process. Keep **one replica** so two pollers do not run at once.
3. Set `BOT_TOKEN`, `ADMIN_USER_ID`, `HIGHLIGHTLY_API_KEY`, and `BRAND_URL`.
4. Set `DATABASE_URL` to the Postgres connection string (`${{Postgres.DATABASE_URL}}` if you reference the database variable). Data on the local sqlite file does not survive a Railway restart.

Scoring runs about every 10 minutes and reminders about every 5 minutes. Reminders pause from 11pm to 8am in `APP_TIMEZONE`. `/reminders off` pauses them until `/reminders on`.

## Admin commands

Restricted to `ADMIN_USER_ID`:

- `/admin` — users, subscribers, predictions, database, API
- `/broadcast your message` — plain text to users who turned alerts on, with a website button when `BRAND_URL` is set
- `/leads` — start → alerts → first pick → website screen, grouped by `?start=` campaign
- `/reminders on` / `/reminders off`

Campaign names: a start payload such as `ad_launch` is stored as `ad_launch`. Later plain `/start` visits do not overwrite it.

## User commands

- `/start` — home
- `/predict` — today's board
- `/leaderboard` — this week
- `/mystats` — points, ranks, streak
- `/team NAME` — team search
- `/sports` — coverage check
- `/stop` — turn alerts off
- `/help`

## Scoring

- Call the winner: home, away, or draw/tie.
- Optional exact score. Football uses goals (`2-1`). Cricket uses the scoreboard (`137/8-139/4`).
- The winner call and the exact score are scored separately. A correct winner is 3 points. A matching exact score is 2 more, even if the winner call was wrong.
- After a penalty shoot-out, the winner follows the shoot-out and the exact score is still the goal score.
- Picks lock when the clock reaches kick-off, or as soon as Highlightly marks the match live or finished.
- The streak is consecutive settled picks with a correct winner, newest first. It stops on the first miss.
- The weekly board is Monday 00:00 to the next Monday in `APP_TIMEZONE`, using each match's kick-off.
