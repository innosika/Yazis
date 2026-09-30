import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// The voice activity detector runs in the browser: Silero VAD through onnxruntime-web.
// Its model, audio worklet and the two WASM runtime files are served from /vad/.
const vadAssets = [
  'node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js',
  'node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx',
  'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm',
  'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs',
]

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteStaticCopy({ targets: vadAssets.map((src) => ({ src, dest: 'vad', rename: { stripBase: true } })) }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5174,
    // `npm run dev` on the host talks to the API in its container.
    proxy: { '/api': { target: 'http://localhost:8030', changeOrigin: true } },
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 1200 },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
})
