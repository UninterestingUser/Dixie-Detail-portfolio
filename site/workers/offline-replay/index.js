// Cloudflare Worker, every 5 minutes: replays the offline requests the
// Pages Function holds in Workers KV to the server, signed, and drops each
// one the server takes (shared/offline.js). While the server is still down
// it stops at the first try, so an outage costs one call per run.
import { replay } from "../../shared/offline.js";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(replay(env).then((counts) => console.log(`Offline replay: ${JSON.stringify(counts)}`)));
  },
};
