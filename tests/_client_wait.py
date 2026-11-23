"""The wait the section-client node tests share: the requests in flight, not a fixed delay.

`create()` sends its opening `scene` request at once; a test that needs that reply (or an
edit's reply) landed before it goes on awaits the transport's requests, inside one 20 s
budget, as `test_js_client_against_live_python_http_transport` does (apeSection#244, #248).
`track(inner)` wraps a transport; `settled()` resolves when none is in flight.
"""

SETTLED_JS = """
const inflight = new Set();
const track = (inner) => (request) => {
  const reply = inner(request);
  inflight.add(reply);
  reply.then(() => inflight.delete(reply), () => inflight.delete(reply));
  return reply;
};
const settled = async () => {
  let timer;
  const bound = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("requests in flight did not settle in 20 s")), 20000);
  });
  const drained = (async () => { while (inflight.size) await Promise.allSettled([...inflight]); })();
  try { await Promise.race([drained, bound]); } finally { clearTimeout(timer); }
};
"""
