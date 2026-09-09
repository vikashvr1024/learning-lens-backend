import { Container, getContainer } from "@cloudflare/containers";

// Single shared container instance for the FastAPI backend.
// All state lives in Postgres, so one instance is enough and avoids
// duplicate `alembic upgrade head` runs on cold start.
export class Backend extends Container {
  // Must match the port uvicorn listens on (Dockerfile CMD uses ${PORT:-8000}).
  defaultPort = 8000;
  // Cold starts boot uvicorn + run migrations, so stay warm a bit longer.
  sleepAfter = "30m";
}

export default {
  async fetch(request, env) {
    return getContainer(env.BACKEND).fetch(request);
  },
};
