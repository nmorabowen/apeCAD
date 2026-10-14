// Live view: poll /api/revision so edits from another client (an agent attached over MCP,
// ADR 0028) show up without a reload. Dependencies come in as arguments, so Node can test it.

export const POLL_MS = 1000;

// One poll. Fetches the scene only when the server's revision differs from the one drawn, and
// drops it if the drawn scene changed meanwhile (a local post answered first, with newer state).
// Mid-gesture (`busy`) it waits, so an agent edit never lands under a half-drawn command.
export async function pollOnce({ fetchJson, current, apply, busy }) {
  if (busy()) return false;
  const before = current();
  const { revision } = await fetchJson("/api/revision");
  if (!Number.isInteger(revision) || (before && before.revision === revision)) return false;
  const scene = await fetchJson("/api/scene");
  if (current() !== before || busy()) return false;
  await apply(scene);
  return true;
}

export function startRevisionPoll(deps, intervalMs = POLL_MS) {
  let inFlight = false;
  return setInterval(async () => {
    if (inFlight || document.hidden) return;
    inFlight = true;
    try {
      await pollOnce(deps);
    } catch (_error) {
      // The scratchpad stopped: keep the last scene; the next tick tries again.
    } finally {
      inFlight = false;
    }
  }, intervalMs);
}
