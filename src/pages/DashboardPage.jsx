import { API_ENDPOINTS, createFetchOptions, handleApiResponse } from '../api/config';

const fetchDashboardData = useCallback(async () => {
  if (!isAuthenticated) {
    setIsLoading(false);
    return;
  }
  setIsLoading(true);
  setError(null);
  
  try {
    const token = await getToken();
    if (!token) throw new Error(t('messages_error_authTokenMissing'));

    // Fetch all data in parallel - CORRECTED ENDPOINTS
    const [statsResponse, distributionResponse, recentDocsResponse] = await Promise.all([
      fetch('/api/v1/dashboard/stats', { // CORRECTED PATH
        headers: { 'Authorization': `Bearer ${token}` }
      }),
      fetch('/api/v1/dashboard/score-distribution', { // CORRECTED PATH
        headers: { 'Authorization': `Bearer ${token}` }
      }),
      fetch('/api/v1/dashboard/recent', { // CORRECTED PATH
        headers: { 'Authorization': `Bearer ${token}` }
      })
    ]);

    // Log successful responses
    console.log('Dashboard data fetched successfully:', {
      stats: statsResponse,
      distribution: distributionResponse,
      recentDocs: recentDocsResponse
    });

    // Update state with fetched data
    setKeyStats(statsResponse);
    setChartData(distributionResponse);
    setRecentAssessments(recentDocsResponse);

  } catch (err) {
    console.error("Dashboard: Error fetching data:", {
      message: err.message,
      stack: err.stack,
      token: 'Bearer token present: ' + Boolean(await getToken())
    });
    setError(err.message || "Failed to load dashboard data.");
    // Clear potentially partial data on error
    setKeyStats(null);
    setChartData([]);
    setRecentAssessments([]);
  } finally {
    setIsLoading(false);
  }
}, [isAuthenticated, getToken]); 