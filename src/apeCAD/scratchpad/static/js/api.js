// JSON calls to the scratchpad HTTP host (server.py). The document lives server-side; the
// client only posts ops (ADR 0003).

export async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

export function createdId(payload, fallbackList) {
  if (payload.created_id != null) return payload.created_id;
  const items = payload[fallbackList] || [];
  if (!items.length) throw new Error("operation did not create an entity");
  return items[items.length - 1].entity_id;
}
