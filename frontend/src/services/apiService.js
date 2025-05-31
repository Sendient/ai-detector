import axios from 'axios';

// Get the API base URL from environment variables
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// Create axios instance with base configuration
const apiService = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add request interceptor to add auth token
apiService.interceptors.request.use(
    async (config) => {
        const token = await getToken();
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

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

// Export both the service and URL constants for direct fetch calls
export { apiService, API_BASE_URL };

export const getCsrfToken = async () => {
    // ... existing code ...
}; 