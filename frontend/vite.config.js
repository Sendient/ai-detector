import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import tailwindConfig from './tailwind.config.js' // Import the config object

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
  server: {
    port: 5173, // Keep the frontend running on 5173 (or your preferred port)
    proxy: {
      // Proxy requests starting with '/api' to your backend server
      '/api': {
        target: 'http://localhost:8000', // Your backend server address
        changeOrigin: true, // Recommended for virtual hosted sites
        // secure: false, // Uncomment if your backend uses http locally
        // rewrite: (path) => path.replace(/^\/api/, ''), // Uncomment if your backend doesn't expect /api prefix
      }
    }
  }
})
