import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Vite blocks requests with an unrecognized Host header by default (DNS
    // rebinding protection). Set to the public hostname when fronting this
    // dev server with a tunnel (ngrok, Cloudflare Tunnel, etc.) — comma-separated
    // for more than one.
    allowedHosts: process.env.VITE_ALLOWED_HOSTS
      ? process.env.VITE_ALLOWED_HOSTS.split(',').map((h) => h.trim())
      : undefined,
    proxy: {
      '/api': {
        // Overridden to the backend's Compose service name (e.g. "backend")
        // when running in Docker, where 127.0.0.1 would mean "this container".
        target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
