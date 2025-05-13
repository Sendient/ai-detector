// src/i18n.js
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import HttpApi from 'i18next-http-backend';

i18n
  // Plugin for loading translations using HTTP requests (e.g., from /public/locales)
  .use(HttpApi)

  // Plugin for detecting user language (checks localStorage, navigator)
  .use(LanguageDetector)

  // Plugin for integrating i18next with React components/hooks
  .use(initReactI18next)

  // Initialize i18next
  .init({
    // --- Core Settings ---
    // Define the languages you want to support
    supportedLngs: ['en-GB', 'en-US', 'fr-FR'],

    // The default language to use if detection fails or a key is missing
    // This is CRUCIAL for fallback behavior.
    fallbackLng: 'en-GB',

    // Default namespace for your translations. You can have multiple namespaces (files)
    // but 'translation' is standard for the main set.
    defaultNS: 'translation',

    // --- Language Detection Settings (i18next-browser-languagedetector) ---
    detection: {
      // Order in which detection methods are tried
      // 'localStorage': Checks if language was saved from a previous session
      // 'navigator': Checks the browser's configured language(s)
      order: ['localStorage', 'navigator'],

      // Where to cache the detected language? 'localStorage' is common.
      caches: ['localStorage'],

      // The specific key to use in localStorage for saving the language
      lookupLocalStorage: 'appLocale', // You can name this whatever you like
    },

    // --- Backend Loading Settings (i18next-http-backend) ---
    backend: {
      // Path where your translation files will be located.
      // '{{lng}}' will be replaced by the language code (e.g., 'en-GB')
      // '{{ns}}' will be replaced by the namespace (e.g., 'translation')
      // This path assumes a 'locales' folder inside your 'public' directory.
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },

    // --- React Integration Settings (react-i18next) ---
    react: {
      // Use React Suspense to handle loading states while translations are fetched.
      // This prevents rendering components before translations are ready. Highly recommended.
      useSuspense: true,
    },

    // --- Interpolation Settings ---
    interpolation: {
      // React already protects against XSS attacks by default when rendering strings.
      // Setting this to false avoids unnecessary escaping.
      escapeValue: false,
    },

    // --- Debugging (Optional) ---
    // Set to true to see detailed logs in the browser console during development
    // Helps troubleshoot loading issues or missing keys. Turn off for production.
    // debug: process.env.NODE_ENV === 'development',
    debug: false, // Keep it false unless actively debugging i18n issues
  });

// Export the configured i18n instance so it can be imported elsewhere (e.g., index.js)
export default i18n;