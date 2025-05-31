import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import tailwindConfig from './tailwind.config.js' // Import the config object
import path from 'path' // Import the 'path' module

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
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
    define: {
      // Expose env variables to your client-side code
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(env.VITE_API_BASE_URL),
    },
    server: {
      port: 5173, // Keep the frontend running on 5173 (or your preferred port)
      proxy: {
        // Proxy requests starting with '/api' to your backend server
        '/api': {
          target: env.VITE_API_BASE_URL || 'https://localhost:8000', // Use HTTPS
          changeOrigin: true, // Recommended for virtual hosted sites
          secure: true, // Enable SSL certificate verification
          // rewrite: (path) => path.replace(/^\/api/, ''), // Uncomment if your backend doesn't expect /api prefix
        }
      }
    }
  }
})
