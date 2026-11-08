# Deploy RefSheet bot to Cloudflare Containers

Requires the **Workers Paid** plan ($5/month).

## One-time setup

```bash
cd bot/cloudflare
npm install
npx wrangler login
```

## Set secrets

```bash
npx wrangler secret put BOT_TOKEN
# paste your bot token from @BotFather

npx wrangler secret put ADMIN_ID
# paste your Telegram user ID
```

## Deploy

```bash
npx wrangler deploy
```

The first deploy builds the Docker image and pushes it. Later deploys are faster.

## Keep it alive

Containers can scale to zero. To wake the bot:

- Visit `https://refsheet-bot.<your-subdomain>.workers.dev/start`
- Or add a Cron Trigger in the Cloudflare dashboard (every 5–10 minutes) that hits the same endpoint

## Files

- `../Dockerfile` — Python bot image
- `wrangler.toml` — Container + Durable Object config
- `src/index.ts` — Minimal Worker that starts the container
