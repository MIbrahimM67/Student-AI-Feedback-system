import { APIError, Sandbox, Snapshot } from "@vercel/sandbox";
import { validExecutorRequest, validCodeRequest } from "@/lib/executor-auth";
import { EXECUTOR_RUNNER } from "@/lib/executor-runner";

export const runtime = "nodejs";
export const maxDuration = 180;
export const dynamic = "force-dynamic";
// Replay protection in a warm function instance; the signature also expires in 60s.
const seen = new Map<string, number>();
let toolchainPromise: Promise<string> | undefined;

async function toolchainSnapshot(): Promise<string> {
  // This snapshot contains compilers only. No submitted code, inputs or keys.
  const previous = await (await Snapshot.list({ name: "gradewise-toolchain-v1" })).toArray();
  const saved = previous.find(snapshot => snapshot.status === "created");
  if (saved) return saved.id;
  // Only trusted, signed distro package installation happens in this VM.
  // Network is blocked before the snapshot and in every submission VM.
  // The API can report a stopped ephemeral sandbox with HTTP 400 rather than
  // the SDK's expected snapshot_not_found/410. Retrieve metadata without resume
  // and remove only our failed compiler-only resource (never a submission VM).
  let existing: Awaited<ReturnType<typeof Sandbox.get>> | undefined;
  try { existing = await Sandbox.get({ name: "gradewise-toolchain-v1", resume: false }); }
  catch (error) { if (!(error instanceof APIError) || error.response.status !== 404) throw error; }
  if (existing && existing.status !== "running" && !existing.currentSnapshotId) {
    await existing.delete();
    existing = undefined;
  }
  const builder = existing || await Sandbox.create({ name: "gradewise-toolchain-v1", resources: { vcpus: 1 },
    timeout: 120000, persistent: false,
    networkPolicy: "allow-all" });
  try {
    const tools = await builder.runCommand("sh", ["-c", "command -v python3 && command -v g++ && command -v javac"]);
    if (tools.exitCode !== 0) {
      const install = await builder.runCommand({ cmd: "sh", args: ["-c", "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends g++ default-jdk-headless"], sudo: true });
      if (install.exitCode !== 0) throw new Error(`Compiler setup failed: ${(await install.stderr()).slice(-1800)}`);
    }
    await builder.update({ networkPolicy: "deny-all" });
    await builder.createUser("student");
    return (await builder.snapshot({ expiration: 0 })).snapshotId;
  } finally { await builder.stop().catch(() => {}); }
}

export async function POST(request: Request) {
  if (Number(request.headers.get("content-length")) > 300000) return Response.json({ error: "Request too large" }, { status: 413 });
  const reader = request.body?.getReader();
  if (!reader) return Response.json({ error: "Missing body" }, { status: 400 });
  const chunks: Uint8Array[] = [];
  let length = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > 300000) { await reader.cancel(); return Response.json({ error: "Request too large" }, { status: 413 }); }
    chunks.push(value);
  }
  const body = Buffer.concat(chunks).toString("utf8");
  if (!validExecutorRequest(body, request.headers.get("x-gradewise-time") || "", request.headers.get("x-gradewise-signature") || "")) {
    return Response.json({ error: "Unauthorized execution request" }, { status: 401 });
  }
  let data: unknown;
  try { data = JSON.parse(body); } catch { return Response.json({ error: "Invalid JSON" }, { status: 400 }); }
  if (!validCodeRequest(data)) return Response.json({ error: "Invalid code request" }, { status: 422 });
  for (const [id, time] of seen) if (Date.now() - time > 120000) seen.delete(id);
  if (seen.has(data.id)) return Response.json({ error: "Duplicate request" }, { status: 409 });
  seen.set(data.id, Date.now());
  let sandbox: Awaited<ReturnType<typeof Sandbox.create>> | undefined;
  try {
    toolchainPromise ??= toolchainSnapshot().catch(error => { toolchainPromise = undefined; throw error; });
    const snapshotId = await toolchainPromise;
    sandbox = await Sandbox.create({ source: { type: "snapshot", snapshotId }, resources: { vcpus: 1 },
      timeout: 60000, persistent: false, networkPolicy: "deny-all" });
    await sandbox.writeFiles([
      { path: "/tmp/gradewise-runner.py", content: Buffer.from(EXECUTOR_RUNNER), mode: 0o600 },
      { path: "/tmp/gradewise-request.json", content: Buffer.from(body), mode: 0o600 },
    ]);
    const execution = await sandbox.runCommand({ cmd: "python3", args: ["/tmp/gradewise-runner.py", "/tmp/gradewise-request.json"], sudo: true });
    if (execution.exitCode !== 0) throw new Error("Execution harness failed");
    const result = JSON.parse(await execution.stdout());
    if (!Array.isArray(result.results) || result.results.length !== data.inputs.length) throw new Error("Incomplete results");
    return Response.json({ results: result.results }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Isolated execution unavailable:", error instanceof Error ? error.message : "Unknown failure");
    return Response.json({ error: "Isolated execution unavailable. No simulated result was generated." }, { status: 503 });
  } finally {
    if (sandbox) await sandbox.stop().catch(() => console.error("Sandbox stop failed; its hard timeout remains active"));
  }
}
