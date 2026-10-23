import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    // En desarrollo, el frontend reenvía /api al backend local.
    proxy: { '/api': 'http://localhost:8000' },
  },
  // Sin recursos en línea (data:) para cumplir la política CSP estricta de nginx.
  build: { sourcemap: false, assetsInlineLimit: 0 },
});
