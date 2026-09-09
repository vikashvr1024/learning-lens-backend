# Backend on Cloudflare

## Free account — use Tunnel (only free option)

Plain Workers cannot run Python/FastAPI, and Containers needs the paid Workers
plan, so on a free account the backend runs on your own machine (or Render,
see below) and Cloudflare Tunnel gives it a public `https://` URL on
Cloudflare's network. Free, no credit card.

**1. Start the backend** (as usual):

```powershell
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**2. Expose it** (install `cloudflared` once from cloudflare.com, then):

```powershell
cloudflared tunnel --url http://localhost:8000
```

You get a public URL like `https://random-name.trycloudflare.com`.
`GET https://<that-url>/health` should return `{"status": "ok", ...}`.
Run both commands whenever you want the backend live; stop them when you don't.

**Stable URL (optional, still free):** instead of the quickstart above,

```powershell
cloudflared tunnel login
cloudflared tunnel create learning-lens-api
cloudflared tunnel route dns learning-lens-api api.yourdomain.com
cloudflared tunnel --config cloudflare-tunnel.example.yml run learning-lens-api
```

(copy `cloudflare-tunnel.example.yml` to `cloudflare-tunnel.yml`, fill in your
tunnel ID + hostname first).

**CORS:** set `FRONTEND_URL` in your backend `.env` to your frontend origin
(e.g. your Cloudflare Pages URL) and restart uvicorn.

## Free account — alternative: Render (no own machine needed)

Render dashboard -> New -> Blueprint -> select `learning-lens-backend`.
`render.yaml` provisions API + Postgres on the free tier. Use the Render URL
as `NEXT_PUBLIC_API_URL` in your frontend.

## Paid account — Workers + Containers (already wired)

Your API code stays 100% Python — nothing in `app/` changed. Cloudflare just
requires one tiny JS file (`src/index.js`, ~15 lines) that receives traffic
and hands it to your Python container, which runs this repo's `Dockerfile`
(uvicorn on port 8000) unchanged.

```
internet -> Worker (src/index.js) -> container (Dockerfile -> FastAPI)
                                              -> Postgres (external, e.g. Render)
```

Postgres cannot live inside the container (it sleeps when idle), so keep using
an external database and point `DATABASE_URL` at it.

Upgrade Workers to Paid, then either run `npx wrangler deploy` locally
(after `wrangler login` + `wrangler secret put DATABASE_URL/SECRET_KEY/AI_API_KEY`),
or connect the repo under Workers & Pages -> Settings -> Builds
(Build: empty, Deploy: `npx wrangler deploy`, secrets under Variables and Secrets).

Notes: containers sleep after 30 min idle (`sleepAfter` in `src/index.js`);
`max_instances = 2` caps parallel containers. Non-secret settings live in
`wrangler.toml` under `[vars]`.
