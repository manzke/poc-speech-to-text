import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Consume the SDK directly from source so the example needs no publish/build of
// the package. The AudioWorklet is served as a static file from public/ (see
// public/pcm-worklet.js) and referenced via SttClientOptions.workletUrl.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@manzke/stt-web-sdk": fileURLToPath(
        new URL("../../clients/web-sdk/src/index.ts", import.meta.url),
      ),
    },
  },
});
