/** @type {import('tailwindcss').Config} */
import daisyui from "daisyui"; // Action 2.1: Import DaisyUI

export default {
    // Configure files where Tailwind classes can be used
    content: [
        "./index.html", // Scans the main HTML file in the project root
        "./src/**/*.{js,ts,jsx,tsx}", // Scans all JS/TS/JSX/TSX files within the src folder
    ],
    theme: {
        extend: {
            // Action 2.3: Define Fonts
            fontFamily: {
                sans: ['Montserrat', 'sans-serif'], // Set Montserrat as default sans-serif
            },
            // Optional: You can still add specific named colours here if needed
            // outside the main theme, but primary styling should use the daisyui theme below.
            colors: {
                 'sendient-success': '#17B26A', // Example explicit color
                 'sendient-info': '#3295C5',
                 'sendient-warning': '#F2930D',
                 'sendient-error': '#F84B3B',
            }
        },
    },
    // Action 2.2: Add DaisyUI Plugin
    plugins: [daisyui],

    // Action 2.4: Define Sendient Theme for DaisyUI
    daisyui: {
        themes: [
            {
                sendient_theme: { // Your custom theme name
                    // --- Mapped Colours (From Sendient UI Kit - Colours.pdf) ---
                    "primary": "#685CF8",        // Primary 500
                    "primary-content": "#ffffff",  // White text

                    "secondary": "#21ABAB",      // Secondary 500
                    "secondary-content": "#ffffff",// White text

                    "accent": "#17B598",         // Accent 500
                    "accent-content": "#ffffff",   // White text

                    "neutral": "#364152",        // Grey 700
                    "neutral-content": "#ffffff",  // White text

                    "base-100": "#ffffff",        // White background
                    "base-200": "#F8FAFC",        // Grey 50
                    "base-300": "#E3E8EF",        // Grey 200
                    "base-content": "#121926",    // Grey 900 (default text)

                    "info": "#3295C5",           // Info 500
                    "info-content": "#ffffff",   // White text

                    "success": "#17B26A",         // Success 500
                    "success-content": "#ffffff",  // White text

                    "warning": "#F2930D",         // Warning 500
                    "warning-content": "#441704", // Dark text (Warning 950) for contrast

                    "error": "#F84B3B",           // Error 500
                    "error-content": "#ffffff",    // White text

                    // --- Optional: Styling variables from UI Kit ---
                    "--rounded-box": "0.5rem",    // 8px radius for cards, etc.
                    "--rounded-btn": "0.375rem",  // 6px radius for buttons
                },
            },
            // Add other themes like a dark theme here later if required
        ],
        // Optional settings:
        // darkTheme: "sendient_theme", // Force your theme for dark mode
        logs: true, // Keep logs enabled during development
    },
};