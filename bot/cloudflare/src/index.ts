import { Container } from "@cloudflare/containers";

export class RefSheetBot extends Container {
  defaultPort = 8080;
  sleepAfter = "30m";

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

    // Hit /start to wake the container
    if (url.pathname === "/start" || url.pathname === "/") {
      const container = env.BOT.getByName("main");
      await container.start();
      return new Response("RefSheet bot container started / kept alive");
    }

    return new Response("RefSheet bot — POST /start to wake", { status: 200 });
  },

  // Optional: cron to keep it alive
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const container = env.BOT.getByName("main");
    ctx.waitUntil(container.start());
  },
};
