🇬🇧 English | [🇵🇱 Polski](README.pl.md)

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

**Bibo is an ADHD-aware companion that sits next to you.** It chats with you
on Telegram, remembers how you work, and reaches out on its own a few times a
day, like a friend at the next desk rather than a reminder app.

Runs on [Hermes Agent](https://github.com/NousResearch/hermes-agent): the installer turns a Hermes install into Bibo (as its main profile, so the dashboard and `/login` configure Bibo directly). Best on a dedicated Hermes instance.
Bibo currently speaks **Polish only**.

- 🧠 Remembers you: goals, how your ADHD shows up, what works, what you promised and when
- 💬 Starts conversations: 1–3 times a day, at humane hours, never while you're mid-chat
- 🧩 Gets ADHD: smallest next step, body doubling, no moralising
- 🪞 No sycophancy: one good question instead of "great idea!"
- 💸 Lean: ~13 KB of prompt per message (stock Hermes is ~50–60 KB), compacted history, a single tool

> Status: **MVP (v0.2)**. Install, prompt size and cron were verified locally; a live bot test is still pending.
> Design rationale (Polish): [docs/REANALIZA.md](docs/REANALIZA.md).

## Install

You need [Hermes Agent](https://github.com/NousResearch/hermes-agent) ≥ 0.21, a Telegram bot token
(from [@BotFather](https://t.me/BotFather)), your Telegram user ID (from [@userinfobot](https://t.me/userinfobot))
and an Anthropic API key.

```bash
git clone https://github.com/Grandpa1001/hi-bibo
cd hi-bibo
./install.sh
```

Then message your bot.

**Updating:** `hermes bibo update` fetches the latest version from GitHub (no git needed; does nothing if you are up to date, `--force` reinstalls), installs
`SOUL.md`, scripts, plugins and the Mini App, then restarts Bibo. It never touches `.env`, config,
memory or cron jobs. `hermes bibo version` shows what's installed. On installs older than this command,
run it once as `curl -fsSL https://raw.githubusercontent.com/Grandpa1001/hi-bibo/main/update.sh | bash`.

**Model billing:** an `ANTHROPIC_API_KEY` is the recommended path. Hermes' Claude subscription login (OAuth)
only works on Claude **Max**, and it bills only purchased *extra usage*, never the plan's included allowance.
It does not work on Pro at all.

**Config panel:** `hermes dashboard` (on a server, tunnel it with `ssh -L 9119:127.0.0.1:9119 host`).

**Proactive messages:** tune them in `~/.hermes/local/bibo_pulse.json`, or pause them with
`hermes cron pause bibo-pulse`.

**Insight report:** `./raport.sh` shows what Bibo knows about you, token/$ usage per message, per day
and per proactive nudge, a timeline of memory writes, and its support plan (`--opinia` asks Bibo for a full
opinion with one model call).

## License

MIT, see [LICENSE](LICENSE).
