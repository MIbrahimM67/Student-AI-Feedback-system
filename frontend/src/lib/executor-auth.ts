import { createHash, createPublicKey, verify } from "node:crypto";
import { EXECUTOR_PUBLIC_KEY_DER } from "./executor-public-key";

export function validExecutorRequest(body: string, timestamp: string, signature: string, now = Date.now(), publicKeyDer = EXECUTOR_PUBLIC_KEY_DER): boolean {
  if (!/^\d{10}$/.test(timestamp) || Math.abs(now / 1000 - Number(timestamp)) > 60) return false;
  if (!/^[A-Za-z0-9+/=]{300,800}$/.test(signature)) return false;
  try {
    const key = createPublicKey({ key: Buffer.from(publicKeyDer, "base64"), format: "der", type: "spki" });
    const digest = createHash("sha256").update(body).digest("hex");
    return verify("RSA-SHA256", Buffer.from(`gradewise-executor-v1\n${timestamp}\n${digest}`), key, Buffer.from(signature, "base64"));
  } catch { return false; }
}

export type CodeRequest = { id: string; language: "python" | "cpp" | "java"; code: string; inputs: string[] };
export function validCodeRequest(value: unknown): value is CodeRequest {
  if (!value || typeof value !== "object") return false;
  const v = value as CodeRequest;
  return typeof v.id === "string" && /^[0-9a-f-]{36}$/.test(v.id)
    && ["python", "cpp", "java"].includes(v.language)
    && typeof v.code === "string" && v.code.length > 0 && v.code.length <= 60000
    && Array.isArray(v.inputs) && v.inputs.length > 0 && v.inputs.length <= 5
    && v.inputs.every(input => typeof input === "string" && input.length <= 8000);
}
