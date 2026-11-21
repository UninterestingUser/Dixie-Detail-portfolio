// Cloudflare Worker, every 5 minutes: replays the offline requests the
// Pages Function holds in Workers KV to the server, signed, and drops each
// one the server takes (shared/offline.js). While the server is still down
// it stops at the first try, so an outage costs one call per run. Then it
// reports to the Healthchecks check HEALTHCHECKS_OFFLINE_URL: success, or
// /fail when a request is refused or stuck (decision 0114). It logs the
// counts, never a request.
import { replay, report, status } from "../../shared/offline.js";

export async function run(env, fetcher = fetch, log = console) {
  const counts = await replay(env, fetcher, log);
  const summary = await status(env, counts, fetcher);
  const ok = await report(env, summary, fetcher, log);
  log.log(`Offline replay: sent ${summary.sent}, refused ${summary.refused}, held ${summary.held}, stuck ${summary.stuck}${ok ? "" : " (reported as failing)"}`);
  return summary;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(env));
  },
};
