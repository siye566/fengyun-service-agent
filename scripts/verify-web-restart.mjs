// CI-only restart of the disposable deployment stack; no production invocation.
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
if (process.env.ACS_RESTART_TEST !== "1")
  throw new Error("Set ACS_RESTART_TEST=1 only for the disposable CI stack");
const origin = "http://127.0.0.1:8080";
const response = await fetch(`${origin}/api/session`);
assert.equal(response.status, 200);
const cookie = response.headers.get("set-cookie").split(";")[0];
const session = await response.json();
async function turn(action, fields = {}) {
  const response = await fetch(`${origin}/api/turn`, {
    method: "POST",
    headers: {
      Origin: origin,
      Cookie: cookie,
      "Content-Type": "application/json",
      "X-CSRF-Token": session.csrf,
    },
    body: JSON.stringify({
      action,
      event_id: randomUUID().replaceAll("-", ""),
      ...fields,
    }),
  });
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.result.ok, true);
  return result;
}
await turn("prepare_repair", {
  device_serial: session.devices[0].serial_no,
  symptom: "机器异响",
});
const saved = await turn("confirm_repair");
const ticket = saved.snapshot.tickets[0].ticket_no;
execFileSync(
  "docker",
  [
    "compose",
    "--env-file",
    ".env",
    "-f",
    "deploy/compose.yaml",
    "restart",
    "web",
  ],
  { stdio: "inherit" },
);
let ready = false;
for (let attempt = 0; attempt < 30; attempt++) {
  try {
    ready = (await fetch(`${origin}/healthz`)).ok;
  } catch {
    /* startup in progress */
  }
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 2000));
}
assert(ready, "web did not become healthy after restart");
const restored = await (
  await fetch(`${origin}/api/session`, { headers: { Cookie: cookie } })
).json();
assert.equal(restored.company, session.company);
assert.equal(restored.state.stage, "completed");
assert.equal(restored.tickets.length, 1);
assert.equal(restored.tickets[0].ticket_no, ticket);
console.log(
  "Container restart preserved the visitor, task and PostgreSQL ticket.",
);
