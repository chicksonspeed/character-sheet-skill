import { Container } from "@cloudflare/containers";

export class RefSheetBot extends Container {
  defaultPort = 8080;
  sleepAfter = "30m";

  // Pass Worker secrets into the container
  envVars = {
    BOT_TOKEN: "",
    ADMIN_ID: "",
  };

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.envVars = {
      BOT_TOKEN: env.BOT_TOKEN || "",
      ADMIN_ID: env.ADMIN_ID || "",
    };
  }

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
      const container = env.BOT.getByName("main");
      await container.start();
      return new Response("RefSheet bot container started / kept alive");
    }

    return new Response("RefSheet bot — POST /start to wake", { status: 200 });
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const container = env.BOT.getByName("main");
    ctx.waitUntil(container.start());
  },
};
