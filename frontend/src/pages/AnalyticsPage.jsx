import React, { useState, useEffect, useCallback } from 'react';
// Import Kinde auth hook
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
// Assuming you have Lucide icons installed for React
// npm install lucide-react
import { Calendar as CalendarIcon, TrendingUp, FileText, Users, BarChart2, AlertTriangle, ListChecks } from 'lucide-react';

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
        {isLoading ? ( <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-3/4 mb-1"></div> ) : ( <p className="text-2xl font-semibold text-gray-900 dark:text-white">{value ?? 'N/A'}</p> )}
        {description && !isLoading && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{description}</p>}
      </div>
    </div>
  );
};

// --- Main Analytics Page Component ---
function AnalyticsPage() {
  // Kinde Auth Hook
  const { user, getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();

  // State Hooks
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [selectedPeriod, setSelectedPeriod] = useState('monthly');
  const [usageStats, setUsageStats] = useState(null);
  const [dashboardStats, setDashboardStats] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [isLoadingUsage, setIsLoadingUsage] = useState(false);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [isLoadingActivity, setIsLoadingActivity] = useState(false);
  const [usageError, setUsageError] = useState(null);
  const [activityError, setActivityError] = useState(null);
  const [dashboardError, setDashboardError] = useState(null);

  // --- Get Current User ---
  // Now using the user object from useKindeAuth hook
  const currentUser = user; // Kinde's user object often has an 'id' property

  // Format date for display and API
  const formatDate = (date) => {
      if (!(date instanceof Date)) { try { date = new Date(date); } catch (e) { console.error("Invalid date provided to formatDate:", date); return ''; } }
      if (isNaN(date.getTime())) { console.error("Invalid date resulted after conversion:", date); return ''; }
      return date.toISOString().split('T')[0];
  }

  const formatDateTime = (dateString) => {
      if (!dateString) return 'N/A';
      try { return new Date(dateString).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short'}); } catch (e) { return 'Invalid Date'; }
  }

  // --- API Fetching Functions ---

  // Fetch Usage Stats Function (Using Kinde Auth)
  const fetchUsageData = useCallback(async () => {
    if (isAuthLoading || !currentUser?.id || !selectedDate || !selectedPeriod) return;
    setIsLoadingUsage(true); setUsageError(null); let token;
    const targetDateFormatted = formatDate(selectedDate);
    if (!targetDateFormatted) { setUsageError("Invalid date selected."); setIsLoadingUsage(false); return; }
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
    const apiUrl = `${API_BASE_URL}/api/v1/analytics/usage/${selectedPeriod}?target_date=${targetDateFormatted}`;
    try {
        token = await getToken(); if (!token) throw new Error("Authentication token not available.");
        console.log(`Fetching Usage Stats from: ${apiUrl}`);
        const response = await fetch(apiUrl, { method: 'GET', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', }, });
        if (!response.ok) { const errorData = await response.json().catch(() => ({ detail: 'Failed to parse error response' })); throw new Error(errorData.detail || `HTTP error! status: ${response.status}`); }
        const data = await response.json(); setUsageStats(data);
    } catch (err) { console.error("Failed to fetch usage stats:", err); setUsageError(err.message || "Failed to load usage statistics."); setUsageStats(null);
    } finally { setIsLoadingUsage(false); }
  }, [selectedDate, selectedPeriod, currentUser?.id, getToken, isAuthLoading]);

  // Fetch Dashboard Stats Function (Using Kinde Auth)
   const fetchDashboardData = useCallback(async () => {
    if (isAuthLoading || !currentUser?.id) return;
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
   }, [currentUser?.id, getToken, isAuthLoading]);

   // Fetch Recent Activity Function (Using Kinde Auth)
   const fetchActivityData = useCallback(async (limit = 5) => {
    if (isAuthLoading || !currentUser?.id) return;
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
   }, [currentUser?.id, getToken, isAuthLoading]); // Added dependencies


  // Effect Hook for Usage Stats (Runs when date or period changes)
  useEffect(() => { if (isAuthenticated) { fetchUsageData(); } else { setUsageStats(null); } }, [fetchUsageData, isAuthenticated]);

  // Effect Hook for Dashboard Stats & Recent Activity (fetch on mount or when auth state changes)
  useEffect(() => { if (isAuthenticated) { fetchDashboardData(); fetchActivityData(5); } else { setDashboardStats(null); setRecentActivity([]); } }, [fetchDashboardData, fetchActivityData, isAuthenticated]);


  // --- Helper to format usage stats display ---
  const getUsagePeriodLabel = () => { /* ... (no changes) ... */
    if (!usageStats) return "Selected Period";
    switch (selectedPeriod) {
      case 'daily': return `On ${usageStats.target_date}`;
      case 'weekly': return `Week: ${usageStats.week_start_date} to ${usageStats.week_end_date}`;
      case 'monthly':
        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const monthIndex = usageStats.month - 1;
        if (monthIndex >= 0 && monthIndex < 12) { return `For ${monthNames[monthIndex]} ${usageStats.year}`; }
        return "Invalid Month";
      default: return "Selected Period";
    }
  };

  // --- Helper to get status badge color ---
  const getStatusBadgeClass = (status) => { /* ... (no changes) ... */
    switch (status?.toUpperCase()) {
        case 'COMPLETED': return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
        case 'PROCESSING': return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300';
        case 'QUEUED': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
        case 'ERROR': return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
        default: return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
  }

  // Handle Auth Loading State
  if (isAuthLoading) { return <div className="p-8 text-center">Loading authentication...</div>; }

  // Handle Not Authenticated State
  if (!isAuthenticated) { return <div className="p-8 text-center">Please log in to view analytics.</div>; }


  return (
    // Using Tailwind classes for styling
    <div className="p-4 md:p-8 bg-gray-50 dark:bg-gray-900 min-h-screen font-inter">
      {/* Page Title */}
      <h1 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-6">Analytics</h1>

      {/* --- Time Period Selector Card --- */}
      {/* ... (no changes) ... */}
      <div className="mb-8 p-4 bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <label htmlFor="date-select" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Select Date</label>
            <input id="date-select" type="date" value={formatDate(selectedDate)} onChange={(e) => setSelectedDate(new Date(e.target.value))} className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-indigo-500 focus:border-indigo-500" aria-label="Select date for analytics period" />
          </div>
          <div className="flex-1">
             <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Select Period</label>
            <div className="flex space-x-2">
              {['daily', 'weekly', 'monthly'].map((period) => ( <button key={period} onClick={() => setSelectedPeriod(period)} className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${ selectedPeriod === period ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-500' }`} aria-pressed={selectedPeriod === period} > {period.charAt(0).toUpperCase() + period.slice(1)} </button> ))}
            </div>
          </div>
        </div>
         {(usageError || dashboardError || activityError) && ( <div className="mt-4 space-y-1 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-md"> {usageError && <p className="text-red-600 dark:text-red-400 text-sm font-medium">Usage Stats Error: {usageError}</p>} {dashboardError && <p className="text-red-600 dark:text-red-400 text-sm font-medium">Dashboard Stats Error: {dashboardError}</p>} {activityError && <p className="text-red-600 dark:text-red-400 text-sm font-medium">Activity Error: {activityError}</p>} </div> )}
      </div>

      {/* --- Stats Grid --- */}
      {/* ... (no changes to grid structure) ... */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6 mb-8">
        {/* Usage Stats Card */}
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 col-span-1 flex flex-col min-h-[140px]">
           <div className="flex items-center justify-between mb-4"> <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Usage ({selectedPeriod})</h3> <CalendarIcon className="h-5 w-5 text-gray-400 dark:text-gray-500" /> </div>
           <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{getUsagePeriodLabel()}</p>
           <div className="flex-grow flex items-end">
             {isLoadingUsage ? ( <div className="space-y-3 animate-pulse w-full"><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div><div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div></div>
             ) : usageStats ? (
              <div className="space-y-3 w-full">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Documents: <span className="font-semibold text-gray-900 dark:text-white">{usageStats.document_count?.toLocaleString() ?? 'N/A'}</span></p>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Characters: <span className="font-semibold text-gray-900 dark:text-white">{usageStats.total_characters?.toLocaleString() ?? 'N/A'}</span></p>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Words: <span className="font-semibold text-gray-900 dark:text-white">{usageStats.total_words?.toLocaleString() ?? 'N/A'}</span></p>
              </div>
             ) : ( <p className="text-sm text-gray-500 dark:text-gray-400">No usage data available.</p> )}
           </div>
        </div>
        {/* Other Stat Cards */}
        <StatCard title="Total Documents Assessed" value={dashboardStats?.totalAssessed?.toLocaleString()} description="All time" icon={FileText} isLoading={isLoadingDashboard} className="col-span-1" />
        <StatCard title="Average AI Score" value={dashboardStats?.avgScore !== null && dashboardStats?.avgScore !== undefined ? `${(dashboardStats.avgScore * 100).toFixed(1)}%` : 'N/A'} description="Across all assessed" icon={TrendingUp} isLoading={isLoadingDashboard} className="col-span-1" />
        <StatCard title="Pending Documents" value={dashboardStats?.pending?.toLocaleString()} description="In queue or processing" icon={Users} isLoading={isLoadingDashboard} className="col-span-1" />
        <StatCard title="Score Distribution" value={"See Chart"} description="Breakdown of AI scores" icon={BarChart2} isLoading={false} className="col-span-1" />
        <StatCard title="Recently Flagged" value={dashboardStats?.flaggedRecent?.toLocaleString()} description="In the last 7 days (example)" icon={AlertTriangle} isLoading={isLoadingDashboard} className="col-span-1" />
      </div>

      {/* --- Recent Activity Table --- */}
      {/* ... (no changes) ... */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4 sm:p-6 border-b border-gray-200 dark:border-gray-700"> <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center"> <ListChecks className="h-5 w-5 mr-2 text-gray-500 dark:text-gray-400" /> Recent Activity </h2> <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Your last 5 processed documents.</p> </div>
          <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Filename</th>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">AI Score</th>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Characters</th>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Words</th>
                      <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Processed At</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                      {isLoadingActivity ? ( [...Array(3)].map((_, i) => ( <tr key={`loading-${i}`} className="animate-pulse"> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div></td> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div></td> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4"></div></td> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div></td> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div></td> <td className="px-4 sm:px-6 py-4 whitespace-nowrap"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div></td> </tr> )))
                      : recentActivity.length > 0 ? ( recentActivity.map((activity) => {
                            // Add Debug Logging Inside the Map
                            console.log('Mapping activity item:', activity);
                            // Prepare Filename Display Logic
                            const displayFilename = activity.original_filename ? activity.original_filename : '-';
                            return (
                                <tr key={activity.id}> 
                                    {/* Update the Table Cell (td) for Filename */}
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white truncate max-w-xs" title={displayFilename}>
                                        {displayFilename}
                                    </td> 
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap"> <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusBadgeClass(activity.status)}`}> {activity.status || 'UNKNOWN'} </span> </td> 
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300"> {activity.score !== null && activity.score !== undefined ? `${(activity.score * 100).toFixed(1)}%` : 'N/A'} </td> 
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{activity.character_count?.toLocaleString() ?? '-'}</td> 
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{activity.word_count?.toLocaleString() ?? '-'}</td> 
                                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{formatDateTime(activity.updated_at)}</td> 
                                </tr>
                            );
                      }))
                      : ( <tr> <td colSpan="6" className="px-4 sm:px-6 py-4 text-center text-sm text-gray-500 dark:text-gray-400">No recent activity found.</td> </tr> )}
                  </tbody>
              </table>
          </div>
      </div>

    </div>
  );
}

// Export the main component
export default AnalyticsPage; 