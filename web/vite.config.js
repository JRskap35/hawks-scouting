import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// `npm run build` makes the GitHub Pages site (dist/).
// `npm run build:preview` makes a single self contained demo file (dist-preview/index.html).
export default defineConfig(({ mode }) => ({
  base: './',                       // works at https://<user>.github.io/<repo>/ without knowing the repo name
  plugins: mode === 'preview' ? [react(), viteSingleFile()] : [react()],
  build: {
    outDir: mode === 'preview' ? 'dist-preview' : 'dist',
    chunkSizeWarningLimit: 2000,
  },
}))
