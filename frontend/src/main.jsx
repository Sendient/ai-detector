// src/main.jsx
import React, { Suspense } from 'react'; // Import Suspense
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import 'react-toastify/dist/ReactToastify.css';

// Import KindeProvider
import { KindeProvider } from '@kinde-oss/kinde-auth-react';
// Import BrowserRouter
import { BrowserRouter } from 'react-router-dom';

// --- Import i18next configuration ---
import './i18n'; // This executes the i18n setup from src/i18n.js
// ------------------------------------

// --- ADDED: Import AuthProvider ---
import { AuthProvider } from './contexts/AuthContext';
// --------------------------------

// Access environment variables provided by Vite
const kindeDomain = import.meta.env.VITE_KINDE_DOMAIN;
const kindeClientId = import.meta.env.VITE_KINDE_CLIENT_ID;
const kindeLogoutUri = import.meta.env.VITE_KINDE_LOGOUT_REDIRECT_URI;
const kindeLoginRedirectUri = import.meta.env.VITE_KINDE_LOGIN_REDIRECT_URI;
const kindeAudience = import.meta.env.VITE_KINDE_AUDIENCE; // Read the audience

// Basic check if required variables are present
if (!kindeDomain || !kindeClientId || !kindeLogoutUri || !kindeLoginRedirectUri) {
  console.error("Kinde environment variables (VITE_KINDE_DOMAIN, VITE_KINDE_CLIENT_ID, VITE_KINDE_LOGIN_REDIRECT_URI, VITE_KINDE_LOGOUT_REDIRECT_URI) are not set in your .env file.");
  // Consider throwing an error or rendering an error message component here
}
// Add check for audience again
if (!kindeAudience) {
     console.warn("VITE_KINDE_AUDIENCE environment variable is not set in your .env file. API calls might fail.");
     // If audience is strictly required by your Kinde setup, you might make this an error.
}


ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* BrowserRouter should wrap KindeProvider and App */}
    <BrowserRouter>
        <KindeProvider
            clientId={kindeClientId}
            domain={kindeDomain}
            logoutUri={kindeLogoutUri}
            redirectUri={kindeLoginRedirectUri}
            // Ensure the audience for your API is included
            // This is necessary to get a token that the backend can validate
            audience={kindeAudience}
            // --- ADDED: Request necessary scopes ---
            // Request standard OIDC scopes to get user profile info in the token
            scope="openid profile email"
            // --------------------------------------
        >
          {/* --- Wrap App with Suspense for i18n loading --- */}
          <Suspense fallback={<div>Loading...</div>}>
          {/*
             Note: The fallback UI itself isn't easily translatable here
             because translations might not be loaded yet when this fallback
             is needed. Keep it simple or use a non-text loading indicator.
          */}
            <AuthProvider>
              <App />
            </AuthProvider>
          </Suspense>
          {/* ------------------------------------------------- */}
        </KindeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);