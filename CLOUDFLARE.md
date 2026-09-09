# Backend on Cloudflare (Workers + Containers)

Your API code stays 100% Python — nothing in `app/` changed for Cloudflare.
Cloudflare just requires one tiny JS file (`worker/src/index.js`, ~15 lines)
that receives internet traffic and hands it to your Python container, which
runs this repo's `Dockerfile` (uvicorn on port 8000) unchanged.

Render hosting still works as before via `render.yaml`. Both can run side by side.

## How it works

```
internet -> Worker (worker/src/index.js) -> container (Dockerfile -> FastAPI)
                                                     -> Postgres (external, e.g. Render)
```

Postgres cannot live inside the container (it sleeps when idle), so keep using
an external database — e.g. the Render Postgres from `render.yaml` — and point
`DATABASE_URL` at it.

## Deploy from your machine

Requirements: Node.js 20+, Docker running, `wrangler login` done once.

```powershell
cd backend
npm --prefix worker ci
npx wrangler secret put DATABASE_URL    # paste your Postgres URL
npx wrangler secret put SECRET_KEY      # any long random string
npx wrangler secret put AI_API_KEY      # only if AI_PROVIDER != mock
npx wrangler deploy
```

Non-secret settings live in `wrangler.toml` under `[vars]`.

## Deploy from the dashboard (Workers Builds)

1. Workers & Pages -> open the `learning-lens-api` worker -> Settings -> Builds,
   connect the `learning-lens-backend` repo.
2. Build command: `npm --prefix worker ci`
3. Deploy command: `npx -y wrangler deploy`
   (Dockerfile builds run in the Builds environment — no local Docker needed.)
4. Add the same three secrets under Settings -> Variables and Secrets.
5. Every push to `main` redeploys.

## After deploy

1. Copy your worker URL: `https://learning-lens-api.<you>.workers.dev`
2. `GET https://<worker>/health` should return `{"status": "ok", ...}`
   (first hit cold-starts the container: boots uvicorn + runs alembic — slow once).
3. Add the worker URL to the backend's `FRONTEND_URL` (comma-separated supported)
   wherever the API runs, and set your frontend's `NEXT_PUBLIC_API_URL` to the worker URL.

## Notes

- Containers sleep after 30 min idle (`sleepAfter` in `worker/src/index.js`);
  the next request cold-starts (a few seconds).
- `max_instances = 2` in `wrangler.toml` caps parallel containers.
- `wrangler dev` (with Docker running) reproduces the whole setup locally.
