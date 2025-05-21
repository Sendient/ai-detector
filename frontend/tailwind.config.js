/** @type {import('tailwindcss').Config} */
import daisyui from "daisyui";

// Define the custom theme as a constant
const sendientCustomTheme = {
    "primary": "#7070FF",             // User's desired primary
    "primary-content": "#FFFFFF",     // White for contrast
    "secondary": "#f000b8",           // Default DaisyUI secondary for light theme (example)
    "secondary-content": "#FFFFFF",   // White
    "accent": "#37cdbe",              // Default DaisyUI accent for light theme (example)
    "accent-content": "#FFFFFF",      // White
    "neutral": "#3d4451",             // Default DaisyUI neutral for light theme (example)
    "neutral-content": "#FFFFFF",     // White
    "base-100": "#FFFFFF",            // White (page background)
    "base-200": "#F2F2F2",            // Off-white
    "base-300": "#E5E6E6",            // Off-white
    "base-content": "#12344A",        // User's desired main text color
    "info": "#3abff8",                // Default DaisyUI info for light theme (example)
    "info-content": "#FFFFFF",        // White
    "success": "#36d399",             // Default DaisyUI success for light theme (example)
    "success-content": "#FFFFFF",     // White
    "warning": "#fbbd23",             // Default DaisyUI warning for light theme (example)
    "warning-content": "#FFFFFF",     // White
    "error": "#f87272",               // Default DaisyUI error for light theme (example)
    "error-content": "#FFFFFF",       // White
};

export default {
    // Configure files where Tailwind classes can be used
    content: [
        "./index.html", // Scans the main HTML file in the project root
        "./src/**/*.{js,ts,jsx,tsx}", // Scans all JS/TS/JSX/TSX files within the src folder
    ],
    theme: {
        extend: {
            colors: {
                // You can add custom non-DaisyUI color utilities here if needed
            },
            fontFamily: {
                sans: ['Montserrat', 'sans-serif'],
            },
        },
    },
    // Action 2.2: Add DaisyUI Plugin
    plugins: [daisyui],

    // Action 2.4: Define Sendient Theme for DaisyUI
    daisyui: {
        themes: [
            {
                sendient_theme: {
                    "primary": "#7070FF",             // User's desired primary
                    "primary-content": "#FFFFFF",     // White for contrast
                    "secondary": "#f000b8",           // Default DaisyUI secondary for light theme (example)
                    "secondary-content": "#FFFFFF",   // White
                    "accent": "#37cdbe",              // Default DaisyUI accent for light theme (example)
                    "accent-content": "#FFFFFF",      // White
                    "neutral": "#3d4451",             // Default DaisyUI neutral for light theme (example)
                    "neutral-content": "#FFFFFF",     // White
                    "base-100": "#FFFFFF",            // White (page background)
                    "base-200": "#F2F2F2",            // Off-white
                    "base-300": "#E5E6E6",            // Off-white
                    "base-content": "#12344A",        // User's desired main text color
                    "info": "#3abff8",                // Default DaisyUI info for light theme (example)
                    "info-content": "#FFFFFF",        // White
                    "success": "#36d399",             // Default DaisyUI success for light theme (example)
                    "success-content": "#FFFFFF",     // White
                    "warning": "#fbbd23",             // Default DaisyUI warning for light theme (example)
                    "warning-content": "#FFFFFF",     // White
                    "error": "#f87272",               // Default DaisyUI error for light theme (example)
                    "error-content": "#FFFFFF",       // White
                },
            },
        ],
        styled: true,
        base: true,
        utils: true,
        logs: true, // Keep logs enabled
        prefix: "",
        darkTheme: false, // Explicitly set darkTheme to false
    },
};