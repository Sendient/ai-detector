import React, { useState, useEffect, useCallback } from 'react';
// Import Kinde auth hook
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
// Import useAuth to access currentUser for usage stats
import { useAuth } from '../contexts/AuthContext'; 
// Assuming you have Lucide icons installed for React
// npm install lucide-react
import { Calendar as CalendarIcon, TrendingUp, FileText, Users, BarChart2, AlertTriangle, ListChecks, Link as LinkIcon } from 'lucide-react';
import { ChevronUpIcon, ChevronDownIcon, ArrowsUpDownIcon } from '@heroicons/react/20/solid';

// --- Authentication Placeholder Removed ---
// Removed the placeholder getAuthToken function

// --- Mock API Calls Removed ---
// Removed mockFetchRecentActivity


// --- Reusable Stat Card Component ---
const StatCard = ({ title, value, description, icon: Icon, isLoading, className = "" }) => {
  return (
    <div className={`bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 flex flex-col justify-between min-h-[140px] ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</h3>
        {Icon && <Icon className="h-5 w-5 text-gray-400 dark:text-gray-500" />}
      </div>
      <div>
        {isLoading ? (
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-3/4 mb-1"></div>
        ) : typeof value === 'object' && value !== null && value.current !== undefined ? (
          // Display structured data for document counts if value is an object with 'current'
          <div className="mt-1">
            <p className="text-xl font-semibold text-gray-900 dark:text-white">{value.current} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">Current</span></p>
            <p className="text-lg font-medium text-gray-700 dark:text-gray-300">{value.deleted} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">Deleted</span></p>
            <p className="text-lg font-medium text-gray-700 dark:text-gray-300">{value.total} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">Total Processed</span></p>
          </div>
        ) : (
          <p className="text-2xl font-semibold text-gray-900 dark:text-white">{value ?? 'N/A'}</p>
        )}
        {description && !isLoading && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{description}</p>}
      </div>
    </div>
  );
};

// --- Main Analytics Page Component ---
function AnalyticsPage() {
  // Kinde Auth Hook
  const { user, getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  // AuthContext Hook to get currentUser for usage stats
  const { currentUser, loading: authContextLoading } = useAuth();

  // State Hooks
  const [dashboardStats, setDashboardStats] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [isLoadingActivity, setIsLoadingActivity] = useState(false);
  const [activityError, setActivityError] = useState(null);
  const [dashboardError, setDashboardError] = useState(null);

  // Sorting state for Recent Activity table
  const [activitySortField, setActivitySortField] = useState('upload_timestamp'); // Default sort field
  const [activitySortOrder, setActivitySortOrder] = useState('desc'); // Default sort order

  // Format date for display and API
  const formatDateTime = (dateString) => {
      if (!dateString) return 'N/A';
      try { return new Date(dateString).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short'}); } catch (e) { return 'Invalid Date'; }
  }

  const handleActivitySort = (field) => {
    if (activitySortField === field) {
      setActivitySortOrder(activitySortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setActivitySortField(field);
      // Default sort order for new field:
      // 'desc' for dates like upload_timestamp
      // 'asc' for text fields like original_filename
      setActivitySortOrder(field === 'upload_timestamp' ? 'desc' : 'asc');
    }
  };

  // Fetch Dashboard Stats Function (Using Kinde Auth)
   const fetchDashboardData = useCallback(async () => {
    if (isAuthLoading || !user?.id) return;
    setIsLoadingDashboard(true); setDashboardError(null); let token;
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
    const apiUrl = `${API_BASE_URL}/api/v1/dashboard/stats`;
    try {
        token = await getToken(); if (!token) throw new Error("Authentication token not available.");
        console.log(`Fetching Dashboard Stats from: ${apiUrl}`);
        const response = await fetch(apiUrl, { method: 'GET', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', }, });
        if (!response.ok) { const errorData = await response.json().catch(() => ({ detail: 'Failed to parse error response' })); throw new Error(errorData.detail || `HTTP error! status: ${response.status}`); }
        const data = await response.json(); setDashboardStats(data);
    } catch (err) { console.error("Failed to fetch dashboard stats:", err); setDashboardError(err.message || "Failed to load dashboard statistics."); setDashboardStats(null);
    } finally { setIsLoadingDashboard(false); }
   }, [user?.id, getToken, isAuthLoading]);

   // Fetch Recent Activity Function (Using Kinde Auth)
   const fetchActivityData = useCallback(async (limit = 5) => {
    if (isAuthLoading || !user?.id) return;
    setIsLoadingActivity(true); setActivityError(null); let token;
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
    // Assuming your documents endpoint supports limit, sort_by, and sort_order query params
    const apiUrl = `${API_BASE_URL}/api/v1/dashboard/recent`;
    try {
        token = await getToken(); if (!token) throw new Error("Authentication token not available.");
        console.log(`Fetching Recent Activity from: ${apiUrl}`);
        const response = await fetch(apiUrl, { method: 'GET', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', }, });
        if (!response.ok) { const errorData = await response.json().catch(() => ({ detail: 'Failed to parse error response' })); throw new Error(errorData.detail || `HTTP error! status: ${response.status}`); }
        const data = await response.json();
        // Ensure data is an array before setting state
        if (Array.isArray(data)) {
            console.log('[AnalyticsPage] Data received for Recent Activity:', data);
            // Add validation for item ID
            const validData = data.filter(item => item && (item.id || item._id));
            if (validData.length !== data.length) {
              console.warn("[AnalyticsPage] Some recent activity items were missing an ID and were filtered out.");
            }
            // Map _id to id if necessary (optional, depending on backend consistency)
            const mappedData = validData.map(item => ({ ...item, id: item.id || item._id }));
            setRecentActivity(mappedData); // Set state with validated and mapped data
        } else {
            console.error("Recent activity API did not return an array:", data);
            setRecentActivity([]); // Set to empty array if response is not as expected
            throw new Error("Invalid data format received for recent activity.");
        }
    } catch (err) { console.error("Failed to fetch recent activity:", err); setActivityError(err.message || "Failed to load recent activity."); setRecentActivity([]);
    } finally { setIsLoadingActivity(false); }
   }, [user?.id, getToken, isAuthLoading]);


  // Sort recentActivity before rendering
  const sortedRecentActivity = React.useMemo(() => {
    if (!recentActivity || recentActivity.length === 0) return [];
    return [...recentActivity].sort((a, b) => {
      const fieldA = a[activitySortField];
      const fieldB = b[activitySortField];

      if (fieldA == null && fieldB == null) return 0;
      if (fieldA == null) return activitySortOrder === 'asc' ? 1 : -1;
      if (fieldB == null) return activitySortOrder === 'asc' ? -1 : 1;

      let comparison = 0;
      if (activitySortField === 'upload_timestamp') {
        // Date comparison
        comparison = new Date(fieldA) - new Date(fieldB);
      } else if (typeof fieldA === 'string' && typeof fieldB === 'string') {
        // String comparison
        comparison = fieldA.localeCompare(fieldB);
      } else {
        // Basic comparison for numbers or other types
        if (fieldA < fieldB) comparison = -1;
        if (fieldA > fieldB) comparison = 1;
      }
      return activitySortOrder === 'asc' ? comparison : comparison * -1;
    });
  }, [recentActivity, activitySortField, activitySortOrder]);

  // Effect Hook for Dashboard Stats & Recent Activity (fetch on mount or when auth state changes)
  useEffect(() => { if (isAuthenticated) { fetchDashboardData(); fetchActivityData(5); } else { setDashboardStats(null); setRecentActivity([]); } }, [fetchDashboardData, fetchActivityData, isAuthenticated]);


  // --- Helper to get status badge color ---
  const getStatusBadgeClass = (status) => {
    switch (status?.toUpperCase()) {
        case 'COMPLETED': return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
        case 'PROCESSING': return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300';
        case 'QUEUED': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
        case 'ERROR': return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
        default: return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
  }

  // Handle Auth Loading State
  if (isAuthLoading || authContextLoading) { return <div className="p-8 text-center">Loading authentication...</div>; }

  // Handle Not Authenticated State
  if (!isAuthenticated) { return <div className="p-8 text-center">Please log in to view analytics.</div>; }

  let integrationsValue = "No integrations active.";
  let integrationsDescription = "Upgrade to Schools for integrations.";
  let iconColorClass = "text-gray-400 dark:text-gray-500"; // Default grey icon

  if (currentUser && currentUser.current_plan === 'SCHOOLS') {
    integrationsValue = "Schools Plan Features Active";
    integrationsDescription = "LMS & API access enabled.";
    iconColorClass = "text-green-500 dark:text-green-400"; // Green icon for active
  }

  return (
    // Using Tailwind classes for styling
    <div className="p-4 md:p-8 bg-gray-50 dark:bg-gray-900 min-h-screen font-inter">
      {/* Page Title */}
      <h1 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-6">Analytics</h1>

      {/* Display general errors if any */}
      {(dashboardError || activityError) && (
        <div className="mb-8 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-md shadow-md">
          {dashboardError && <p className="text-red-600 dark:text-red-400 text-sm font-medium">Dashboard Stats Error: {dashboardError}</p>}
          {activityError && <p className="text-red-600 dark:text-red-400 text-sm font-medium">Activity Error: {activityError}</p>}
        </div>
      )}

      {/* --- Stats Grid --- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6 mb-8">
        {/* Usage Stats Card - MODIFIED to use currentUser from useAuth */}
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 col-span-1 flex flex-col min-h-[140px]">
           <div className="flex items-center justify-between mb-4"> <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Current Cycle Usage</h3> <CalendarIcon className="h-5 w-5 text-gray-400 dark:text-gray-500" /> </div>
           <div className="flex-grow flex items-end">
             {authContextLoading ? ( <div className="space-y-3 animate-pulse w-full"><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div></div>
             ) : currentUser ? (
                currentUser.current_plan === 'SCHOOLS' ? (
                    <p className="text-sm text-gray-700 dark:text-gray-300">Your Schools plan includes unlimited word usage.</p>
                ) : (
                  <div className="space-y-2 w-full">
                      <div className="flex justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
                          <span>Monthly Word Limit:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">{currentUser.current_plan_word_limit?.toLocaleString() ?? 'N/A'}</span>
                      </div>
                      <div className="flex justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
                          <span>Words Used This Cycle:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">{currentUser.words_used_current_cycle?.toLocaleString() ?? '0'}</span>
                      </div>
                      <div className="flex justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
                          <span>Words Remaining:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">{currentUser.remaining_words_current_cycle?.toLocaleString() ?? 'N/A'}</span>
                      </div>
                      <div className="flex justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
                          <span>Documents Processed:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">{currentUser.documents_processed_current_cycle?.toLocaleString() ?? '0'}</span>
                      </div>
                      {currentUser.current_plan_word_allowance && currentUser.current_plan_word_allowance > 0 && currentUser.current_plan !== 'SCHOOLS' && (
                          <progress 
                              className="progress progress-primary w-full mt-2" 
                              value={currentUser.words_used_current_cycle || 0} 
                              max={currentUser.current_plan_word_allowance}>
                          </progress>
                      )}
                  </div>
                )
             ) : ( <p className="text-sm text-gray-500 dark:text-gray-400">Usage data not available. Ensure you are logged in.</p> )}
           </div>
        </div>
        {/* Other Stat Cards */}
        <StatCard 
          title="Total Documents Assessed" 
          value={
            isLoadingDashboard ? null : // Show loading state for value
            dashboardStats ? { // Check if dashboardStats is available
              current: dashboardStats.current_documents !== undefined ? dashboardStats.current_documents.toLocaleString() : 'N/A',
              deleted: dashboardStats.deleted_documents !== undefined ? dashboardStats.deleted_documents.toLocaleString() : 'N/A',
              total: dashboardStats.total_processed_documents !== undefined ? dashboardStats.total_processed_documents.toLocaleString() : 'N/A'
            } : { current: 'N/A', deleted: 'N/A', total: 'N/A' } // Fallback if dashboardStats is null
          }
          description="All time" 
          icon={FileText} 
          isLoading={isLoadingDashboard} 
          className="col-span-1" 
        />
        <StatCard title="Average AI Score" value={dashboardStats?.avgScore !== null && dashboardStats?.avgScore !== undefined ? `${(dashboardStats.avgScore * 100).toFixed(1)}%` : 'N/A'} description="Across all assessed" icon={TrendingUp} isLoading={isLoadingDashboard} className="col-span-1" />
        <StatCard title="Pending Documents" value={dashboardStats?.pending?.toLocaleString()} description="In queue or processing" icon={Users} isLoading={isLoadingDashboard} className="col-span-1" />
        {/* MODIFIED StatCard for Active Integrations */}
        <StatCard 
          title="Active Integrations"
          value={authContextLoading ? null : integrationsValue} 
          description={authContextLoading ? null : integrationsDescription}
          icon={() => <LinkIcon className={`h-5 w-5 ${iconColorClass}`} />} // Custom icon rendering with color
          isLoading={authContextLoading} 
          className="col-span-1" 
        />
        <StatCard title="Recently Flagged" value={dashboardStats?.flaggedRecent?.toLocaleString()} description="In the last 7 days (example)" icon={AlertTriangle} isLoading={isLoadingDashboard} className="col-span-1" />
      </div>

      {/* --- Recent Activity Table --- */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4 sm:p-6 border-b border-gray-200 dark:border-gray-700"> <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center"> <ListChecks className="h-5 w-5 mr-2 text-gray-500 dark:text-gray-400" /> Recent Activity </h2> <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Your last 5 processed documents.</p> </div>
          <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer" onClick={() => handleActivitySort('original_filename')}>
                        Filename
                        {activitySortField === 'original_filename' ? (
                          activitySortOrder === 'asc' ? <ChevronUpIcon className="h-3 w-3 inline ml-1" /> : <ChevronDownIcon className="h-3 w-3 inline ml-1" />
                        ) : <ArrowsUpDownIcon className="h-3 w-3 inline ml-1 text-gray-400" />}
                      </th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer" onClick={() => handleActivitySort('upload_timestamp')}>
                        Uploaded
                        {activitySortField === 'upload_timestamp' ? (
                          activitySortOrder === 'asc' ? <ChevronUpIcon className="h-3 w-3 inline ml-1" /> : <ChevronDownIcon className="h-3 w-3 inline ml-1" />
                        ) : <ArrowsUpDownIcon className="h-3 w-3 inline ml-1 text-gray-400" />}
                      </th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">AI Score</th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Words</th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Chars</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                      {isLoadingActivity ? (
                        <tr><td colSpan="6" className="text-center py-4"><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-1/2 mx-auto"></div></td></tr>
                      ) : sortedRecentActivity.length > 0 ? (
                        sortedRecentActivity.map((item, index) => (
                          <tr key={item.id || item._id || index} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                            <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{item.original_filename || 'N/A'}</td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{formatDateTime(item.upload_timestamp)}</td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusBadgeClass(item.status)}`}>
                                {item.status || 'N/A'}
                              </span>
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                              {item.score ? `${(item.score * 100).toFixed(1)}%` : 'N/A'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                              {item.word_count?.toLocaleString() ?? 'N/A'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                              {item.character_count?.toLocaleString() ?? 'N/A'}
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="6" className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-center text-gray-500 dark:text-gray-400">
                            No recent activity to display.
                          </td>
                        </tr>
                      )}
                  </tbody>
              </table>
          </div>
      </div>

    </div>
  );
}

// Export the main component
export default AnalyticsPage; 