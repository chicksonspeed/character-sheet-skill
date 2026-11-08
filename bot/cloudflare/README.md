# Deploy RefSheet bot to Cloudflare Containers

Requires the **Workers Paid** plan.

## One-time setup

```zsh
cd bot/cloudflare
npm install
npx wrangler login
npx wrangler secret put BOT_TOKEN   # token from @BotFather
npx wrangler secret put ADMIN_ID    # your Telegram user ID (optional)
```

## Deploy (from `bot/`)

```zsh
docker build --no-cache --platform linux/amd64 -t refsheet-bot:vX .
npx wrangler containers push refsheet-bot:vX   # retry if "blob unknown to registry"
cd cloudflare
sed -i '' 's|image = ".*"|image = "registry.cloudflare.com/<account-id>/refsheet-bot:vX"|' wrangler.toml
npx wrangler deploy --config wrangler.toml
```

## Keep-alive

A cron trigger (`*/5 * * * *`, in `wrangler.toml`) fetches the container's health
endpoint. That renews the `sleepAfter` timer; calling `start()` alone does not.
`GET /start` on the Worker does the same and reports the health status:
`200` = bot polling, `503` = container up but bot not running (check `npx wrangler tail`).

If the bot crashes with a valid token the process exits after 30 s and the next
keep-alive restarts the container. Conversation state is in memory, so a restart
or redeploy ends in-progress sessions (users get a "send /start" reply).

## Files

- `../Dockerfile` — Python bot image
- `wrangler.toml` — Container + Durable Object + cron config
- `src/index.ts` — Worker: keep-alive + container class
