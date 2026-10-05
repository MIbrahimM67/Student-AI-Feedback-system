const assert = require('node:assert/strict');
const { createHash, generateKeyPairSync, sign } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
// Load the actual TypeScript functions without generating repository artifacts.
const file = path.join(__dirname, '../src/lib/executor-auth.ts');
const mod = { exports: {} };
const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
new Function('require', 'exports', js)((id) => id === './executor-public-key' ? { EXECUTOR_PUBLIC_KEY_DER: '' } : require(id), mod.exports);
const { validExecutorRequest, validCodeRequest } = mod.exports;
const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const der = publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
const now = Date.now(), timestamp = String(Math.floor(now / 1000));
const body = JSON.stringify({ id: '12345678-1234-1234-1234-123456789abc', language: 'python', code: 'print(42)', inputs: [''] });
const message = `gradewise-executor-v1\n${timestamp}\n${createHash('sha256').update(body).digest('hex')}`;
const signature = sign('RSA-SHA256', Buffer.from(message), privateKey).toString('base64');
assert(validExecutorRequest(body, timestamp, signature, now, der));
assert(!validExecutorRequest(body + ' ', timestamp, signature, now, der));
assert(!validExecutorRequest(body, timestamp, signature, now + 61000, der));
assert(!validExecutorRequest(body, timestamp, 'invalid', now, der));
assert(!validExecutorRequest(body, timestamp, signature, now, 'invalid-key'));
assert(validCodeRequest(JSON.parse(body)));
for (const change of [{ inputs: [] }, { inputs: Array(6).fill('') }, { inputs: ['x'.repeat(8001)] }, { code: 'x'.repeat(60001) }, { language: 'javascript' }]) {
  assert(!validCodeRequest({ ...JSON.parse(body), ...change }));
}
console.log('Execution auth passed: valid signature, tampering, expiry, key mismatch, request limits.');
