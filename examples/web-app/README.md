# STT reference web app

A small React + Vite app showing **dictation** and **live captions** against the
self-hosted STT service via [`@manzke/stt-web-sdk`](../../clients/web-sdk).

```bash
cd examples/web-app
npm install
npm run dev      # http://localhost:5173
```

Point "Server URL" at your `/asr` endpoint (default `ws://localhost:8000/asr`;
use `wss://…` in production). If auth is enabled (see `helm/stt` `auth.*`), put
the bearer token in the Token field — the SDK sends it as `?token=` on the WS
handshake.

Notes:
- The SDK is consumed directly from source via a Vite alias (see
  `vite.config.ts`), so you don't need to build/publish the package first.
- The `AudioWorklet` is served as a static file (`public/pcm-worklet.js`) and
  passed to the SDK via `workletUrl`. It mirrors the SDK's
  `src/pcm-worklet.ts` (worklet modules must be plain JS).
- Microphone capture requires a **secure context** — `localhost` is fine; any
  other host needs HTTPS.

Build a static bundle with `npm run build` (output in `dist/`).
