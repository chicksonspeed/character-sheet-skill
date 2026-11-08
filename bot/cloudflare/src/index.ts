import { Container } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

export class RefSheetBot extends Container {
  defaultPort = 8080;
  sleepAfter = "1h";

  // Pass Worker secrets into the container at start
  envVars = {
    BOT_TOKEN: env.BOT_TOKEN,
    ADMIN_ID: env.ADMIN_ID,
  };

  override onStart() {
    console.log("RefSheet bot container started");
  }

  override onStop() {
    console.log("RefSheet bot container stopped");
  }

  override onError(error: unknown) {
    console.log("Container error:", error);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/start" || url.pathname === "/") {
      // fetch() (not start()) renews the sleepAfter timer on a running container
      const res = await env.BOT.getByName("main").fetch("http://container/health");
      return new Response(`RefSheet bot container alive (health: ${res.status})`);
    }

    return new Response("RefSheet bot — POST /start to wake", { status: 200 });
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    // start() is a no-op on a running container and does NOT renew sleepAfter,
    // so the container used to be killed every 30m (wiping conversation state).
    // A fetch through the container renews the activity timer.
    ctx.waitUntil(
      env.BOT.getByName("main")
        .fetch("http://container/health")
        .then((r) => console.log("keepalive", r.status))
        .catch((e) => console.log("keepalive failed", e)),
    );
  },
};
