import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import tailwindConfig from './tailwind.config.js' // Import the config object
import path from 'path' // Import the 'path' module

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [
        tailwindcss(tailwindConfig), // Pass the imported config object
        autoprefixer,
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173, // Keep the frontend running on 5173 (or your preferred port)
    proxy: {
      // Using the VITE_API_PROXY_PATH from .env for the proxy path
      // Example: '/api/v1'
      [process.env.VITE_API_PROXY_PATH || '/api/v1']: {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000', // The backend server address
        changeOrigin: true,
        secure: false, // Set to true if your backend is HTTPS and you trust the cert
        // No rewrite needed if the backend expects the full path including /api/v1
      }
    }
  }
})
