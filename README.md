# Paheli777

Telegram bot for **Paheli777**. Cricket and football scores, fixtures, results, and news, plus a daily winner prediction game with leaderboards.

This repository is Paheli777 only. It does not call, link to, or share a database with any other brand.

## Features

- Welcome screen in English and Hindi
- Cricket and football menus: live scores, upcoming fixtures, results, and news
- Team search with `/team`
- Match alerts you can turn on or off, plus settings
- Brand website button from `BRAND_URL` (placeholder until the real site is known)
- Admin commands limited to `ADMIN_USER_ID`: `/admin`, `/broadcast`, `/leads`, `/sync`, `/reminders`
- Lead funnel: `/start` campaign tags (`ad_…` or any referral code), website opens, “count me in”, subscriptions, and predictions
- Broadcast to subscribers only
- Reminder before kick-off for subscribers who have not picked yet

### Daily predictions

Each day the bot builds a card of notable football and cricket matches from the [Highlightly](https://highlightly.net) API (known leagues first; if none are scheduled, it uses the rest of that day’s matches, up to six per sport).

- Pick the winner: home, away, or draw
- Optionally send an exact score (`2-1`, or cricket leading run totals such as `181-180`)
- Picks lock at kick-off, and also if the match is already live, finished, or void
- After full time, results are fetched from Highlightly and picks are scored
- **3 points** for the correct winner, **+2** for the exact score as well
- The exact-score bonus counts only when the winner is also correct
- Football exact score is the score at the end of play. A penalty shootout can decide the winner and is not part of the exact score
- Postponed, cancelled, and abandoned matches are void and do not affect a streak
- Weekly leaderboard (Monday–Sunday, Asia/Kolkata, by kick-off time) and an all-time leaderboard
- `/mystats` shows points, correct winners, exact scores, current streak, and best streak

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `BOT_TOKEN` | yes | Telegram bot token |
| `ADMIN_USER_ID` | yes | Telegram user id allowed to run admin commands |
| `HIGHLIGHTLY_API_KEY` | yes for scores and the card | Paid Highlightly key, sent as `x-rapidapi-key` |
| `DATABASE_URL` | recommended on Railway | Postgres URL. Empty locally uses `sqlite:///paheli777.db` |
| `BRAND_URL` | recommended | Public website. `.env.example` uses `https://example.com` until the real URL is set |

Optional: `REMINDER_LEAD_MINUTES` (default 45), `REMINDER_QUIET_HOURS` (for example `23-8`, off by default), `NOTABLE_PER_SPORT` (default 6), `SYNC_INTERVAL_SECONDS` (default 300).

`postgres://` URLs are accepted and normalized to `postgresql://`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill BOT_TOKEN, ADMIN_USER_ID, HIGHLIGHTLY_API_KEY, BRAND_URL
python bot.py
```

Check the Highlightly key without starting the bot:

```bash
python highlightly_smoke.py
```

## Tests

```bash
pytest
```

The scoring and lock tests do not call Telegram or Highlightly.

## Railway

Run it as a **worker**. It polls Telegram and does not serve HTTP.

1. Create a Railway service from this repo.
2. Add a Postgres plugin. Railway sets `DATABASE_URL`.
3. Set `BOT_TOKEN`, `ADMIN_USER_ID`, `HIGHLIGHTLY_API_KEY`, and `BRAND_URL`.
4. Start command: `python bot.py` (`Procfile` and `railway.json` already say this).
5. Use one replica so two processes do not both poll Telegram. Reminder sends are still claimed in the database, so a retry will not double-send the same match.

Data lives in Postgres, so a restart does not wipe users, picks, or the leaderboard.
