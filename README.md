# Disneyland Paris table checker

Checks Bistrot Chez Rémy, PYM Kitchen, and the Downtown Restaurant (Art of
Marvel) for lunch/dinner availability on 7, 8 and 9 Oct 2026, for a party of
3, every 15 minutes, and pings you on Telegram the moment a slot that wasn't
there before shows up.

It calls the same (undocumented) API the official booking widget at
bookrestaurants.disneylandparis.com uses. It doesn't need your Disney login
— just a static API key that's shipped in the site's own JavaScript.

## 1. Create your Telegram bot (2 minutes)

1. In Telegram, message **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot`, give it a name and a username (must end in `bot`, e.g.
   `george_dlp_tables_bot`).
3. BotFather replies with a token that looks like
   `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`. Save it — that's
   `TELEGRAM_BOT_TOKEN`.
4. Open a chat with your new bot (search its username, tap **Start**, send
   it any message, e.g. "hi"). Telegram bots can't message you until you've
   messaged them first.
5. In your browser, visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` (swap in your real
   token). Find `"chat":{"id":12345678,...}` in the response — that number
   is your `TELEGRAM_CHAT_ID`.

## 2. Create a GitHub repo

1. Go to [github.com/new](https://github.com/new). Name it something like
   `dlp-table-checker`, set it to **Private**, create it.
2. Upload all the files in this folder (or `git init` / `git add` / `git
   commit` / `git push` them, if you're comfortable with git) — keep the
   `.github/workflows/check.yml` path exactly as-is, that's what tells
   GitHub to run it on a schedule.

## 3. Add your secrets

In the repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add two:

- `TELEGRAM_BOT_TOKEN` — the token from step 1.3
- `TELEGRAM_CHAT_ID` — the number from step 1.5

## 4. Turn it on

Go to the **Actions** tab. If GitHub asks you to enable workflows, click
enable. Click into "Check DLP dining availability" → **Run workflow** to
fire it manually once and confirm it works — check the run's logs, and you
should get nothing on Telegram (no availability yet) but no errors either.

After that it runs on its own every 15 minutes. No further action needed
until you get a message.

## Notes / things that could go wrong

- **Disney's API might rate-limit or block requests from GitHub's cloud IP
  ranges.** This is calling an endpoint that's meant to be hit from a real
  browser, and some sites' bot-protection is stricter about datacenter IPs
  than home internet connections. If checks start failing consistently
  you'll get one Telegram alert about it (not spammed every 15 min) — if
  that happens, the fix is to run `checker.py` on a machine with a normal
  residential IP instead (e.g. your own laptop via `cron`/Task Scheduler,
  or a Raspberry Pi left on). Ask me and I'll adapt the setup for that.
- **The `x-api-key` is baked into the script.** It's the same key every
  visitor to the site gets from the page's JavaScript, not something tied
  to your account — but if Disney rotates it, the checker will start
  failing and you'll get the same "checks failing" alert. If that happens,
  re-capture it the same way we did originally (DevTools → Network → the
  request to `.../book-dine/availabilities/...` → check the `x-api-key`
  header) and swap it into `checker.py`.
- **GitHub disables scheduled workflows after 60 days with zero repo
  activity.** Since the checker commits `state.json` back to the repo
  every time availability changes, and your trip is under 60 days out
  already, this shouldn't bite — but if you ever see it's stopped running
  for no reason, a manual "Run workflow" click resets the clock.
- Dates/restaurants/party size are set at the top of `checker.py` — edit
  the `RESTAURANTS`, `DATES`, or `PARTY_MIX` constants directly if your
  plans change.
