// API configuration
export const API_BASE_URL = 'http://localhost:3000'; // Update this for production

export const createAuthHeaders = async (getToken) => {
  const token = await getToken();
  if (!token) {
    throw new Error('No authentication token available');
  }
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
};

export const handleApiResponse = async (response) => {
  if (response.status === 401) {
    throw new Error('Authentication failed - please log in again');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API request failed with status ${response.status}`);
  }
  return response.json();
};

// Common fetch options to ensure consistent behavior
export const createFetchOptions = async (getToken) => {
  const headers = await createAuthHeaders(getToken);
  return {
    headers,
    credentials: 'include', // Include cookies if any
    mode: 'cors', // Explicit CORS mode
  };
};

export const API_ENDPOINTS = {
  dashboard: {
    stats: `${API_BASE_URL}/api/v1/dashboard/stats`,
    scoreDistribution: `${API_BASE_URL}/api/v1/dashboard/score-distribution`,
  },
  documents: {
    recent: (limit = 4) => 
      `${API_BASE_URL}/api/v1/documents?limit=${limit}&sort_by=upload_time&sort_order=-1`,
  },
}; 