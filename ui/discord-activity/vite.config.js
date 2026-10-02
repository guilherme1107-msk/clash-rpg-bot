import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // A Activity pode ser aberta tanto na raiz quanto através do proxy do Discord.
  // Caminhos relativos evitam que o CSS seja procurado fora do iframe.
  base: './',
  plugins: [react()],
  build: {
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/clashbot-app-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 5175,
    strictPort: true,
    proxy: {'/.proxy/api': 'http://127.0.0.1:8780'},
  },
})
