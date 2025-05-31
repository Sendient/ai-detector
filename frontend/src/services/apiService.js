import axios from 'axios';

// Determine the base URL for the API
// In development, Vite uses import.meta.env.VITE_API_BASE_URL
// In production, it might be the same or a different configured URL
// Ensure VITE_API_BASE_URL is set in your .env files (e.g., .env.development, .env.production)
// For local development, it might be something like 'http://localhost:8000/api/v1'
// For production, it will be your actual API endpoint.
const HOST_URL = import.meta.env.VITE_API_BASE_URL;

// Fallback if VITE_API_BASE_URL is not set - this might be useful for some local dev setups
// but the primary goal is to use the env variable. Consider error handling if it's undefined.
// if (!HOST_URL) {
//   console.error("VITE_API_BASE_URL is not defined. API calls may fail or use relative paths if HOST_URL is missing.");
//   // Potentially set a default local URL here FOR DEVELOPMENT ONLY if absolutely necessary,
//   // but it's better to ensure VITE_API_BASE_URL is always defined in the environment.
//   // For example: HOST_URL = 'http://localhost:8000/api/v1'; (This line would be conditional)
// }

const API_PREFIX = '/api/v1'; // Define your API prefix

const FULL_API_URL = HOST_URL ? `${HOST_URL}${API_PREFIX}` : undefined;

// if (!FULL_API_URL) {
//   console.error("VITE_API_BASE_URL is not defined. API calls may fail or use relative paths if HOST_URL is missing.");
// }

const apiService = axios.create({
    baseURL: FULL_API_URL, // e.g., http://localhost:8000/api/v1 or https://your-prod-api.com/api/v1
    headers: {
        'Content-Type': 'application/json',
    },
});

// Function to set the Authorization token
apiService.setAuthToken = (token) => {
    if (token) {
        apiService.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        // console.log("apiService: Token set");
    } else {
        delete apiService.defaults.headers.common['Authorization'];
        // console.log("apiService: Token removed");
    }
};

// Interceptor to handle errors globally (optional but good practice)
apiService.interceptors.response.use(
    response => response.data, // Return data directly for successful responses
    error => {
        // console.error('API Error:', error.response || error.message);
        // Handle specific error codes or scenarios
        if (error.response && error.response.status === 401) {
            // Example: redirect to login or refresh token
            // This depends on your auth flow with Kinde.
            // For now, just logging. KindeProvider might handle redirects.
            console.warn('API returned 401 Unauthorized. Token might be expired or invalid.');
        }
        // It's important to return a rejected promise here so that individual
        // .catch() blocks in your components still work.
        return Promise.reject(error);
    }
);

export default apiService;

export const getCsrfToken = async () => {
    // ... existing code ...
}; 