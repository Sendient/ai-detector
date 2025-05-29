import axios from 'axios';

// Determine the base URL for the API
// In development, Vite uses import.meta.env.VITE_API_BASE_URL
// In production, it might be the same or a different configured URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const apiService = axios.create({
    baseURL: API_BASE_URL,
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