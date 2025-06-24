// src/pages/DashboardPage.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import MainCardBackground2Image from '../img/maincard2.png'; // Import the new background image maincard2.png
import { useAuth } from '../contexts/AuthContext'; // Corrected import path

// --- Import Icons ---
import {
  ArrowUpTrayIcon,
  ChartBarIcon,
  TableCellsIcon,
  DocumentDuplicateIcon,
  CheckBadgeIcon,
  ScaleIcon,
  ClockIcon,
  EyeIcon,
  XCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ArrowsUpDownIcon
} from '@heroicons/react/24/outline';

// Define the default ranges outside components
const DEFAULT_RANGES = [
  { range: '0-20', count: 0 },
  { range: '21-40', count: 0 },
  { range: '41-60', count: 0 },
  { range: '61-80', count: 0 },
  { range: '81-100', count: 0 }
];

// Memoize the ScoreDistributionChart component
const ScoreDistributionChart = React.memo(function ScoreDistributionChart({ data }) {
  if (!Array.isArray(data) || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-base-200 rounded-box text-base-content/50">
        <span>No assessment data available.</span>
      </div>
    );
  }

  // Ensure data has the correct structure
  const chartData = data.map(item => ({
    range: item.range,
    count: item.count || 0,
    fill: (() => {
      switch(item.range) {
        case '0-20': return '#4ade80';
        case '21-40': return '#86efac';
        case '41-60': return '#fbbf24';
        case '61-80': return '#fb923c';
        case '81-100': return '#f87171';
        default: return '#4ade80';
      }
    })()
  }));

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart 
          data={chartData} 
          margin={{ top: 20, right: 30, left: 40, bottom: 25 }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="range" 
            tick={{ fontSize: 12 }}
            label={{ value: 'AI Score Range (%)', position: 'bottom', offset: 15 }}
          />
          <YAxis 
            tick={{ fontSize: 12 }}
            label={{ 
              value: 'Number of Documents', 
              angle: -90, 
              position: 'insideLeft', 
              offset: 10,
              style: { textAnchor: 'middle' }
            }}
          />
          <Tooltip 
            formatter={(value) => [`${value} documents`, 'Count']}
            labelFormatter={(label) => `Score Range: ${label}`}
            contentStyle={{ fontSize: '12px' }}
          />
          <Bar 
            dataKey="count" 
            radius={[4, 4, 0, 0]}
            fillOpacity={0.8}
            fill={(entry) => entry.fill}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
});

// Moved outside the component
const processDistributionData = (data) => {
  if (!Array.isArray(data)) return DEFAULT_RANGES;
  return data.map(item => ({
    range: item.range,
    count: item.count || 0
  }));
};

// --- Dashboard Page Component ---
function DashboardPage() {
  console.log('[DashboardPage] Component rendering/mounting. Timestamp:', new Date().toISOString());
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading, getToken, user } = useKindeAuth();
  const navigate = useNavigate();
  const { currentUser, loading: authLoading } = useAuth();

  // --- State for Dashboard Data ---
  const [isLoading, setIsLoading] = useState(false); // Start with false instead of true
  const [error, setError] = useState(null);
  const [dataLoaded, setDataLoaded] = useState(false); // Add separate flag for data loaded
  const [keyStats, setKeyStats] = useState({
    current_documents: 0,
    deleted_documents: 0,
    total_processed_documents: 0,
    avgScore: null,
    flaggedRecent: 0,
    pending: 0
  });
  const [chartData, setChartData] = useState(DEFAULT_RANGES);
  const [recentAssessments, setRecentAssessments] = useState([]);
  const [debugInfo, setDebugInfo] = useState({});
  const [userName, setUserName] = useState('');
  const [sortField, setSortField] = useState('upload_timestamp');
  const [sortOrder, setSortOrder] = useState('desc');

  // Add ref to track fetch state
  const isFetchingRef = React.useRef(false);
  const hasDataRef = React.useRef(false);
  const hasStartedFetchRef = React.useRef(false); // Track if we've started fetching

  // Debug: Track isLoading changes
  useEffect(() => {
    console.log('[DashboardPage] isLoading changed to:', isLoading, 'at timestamp:', new Date().toISOString());
  }, [isLoading]);

  // Debug: Track dataLoaded changes
  useEffect(() => {
    console.log('[DashboardPage] dataLoaded changed to:', dataLoaded, 'at timestamp:', new Date().toISOString());
  }, [dataLoaded]);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  // Helper function to get plan display name
  const getPlanDisplayName = (planString) => {
    if (authLoading || isAuthLoading) return 'Loading...';
    if (planString) {
        const formattedPlan = planString.charAt(0).toUpperCase() + planString.slice(1);
        return `${formattedPlan} Plan`;
    }
    if (isAuthenticated) {
        return t('header_free_plan', 'Free Plan');
    }
    return 'Plan N/A';
  };

  // --- Effect to update user name from Kinde auth ---
  useEffect(() => {
    if (user?.givenName) {
      const capitalizedName = user.givenName.charAt(0).toUpperCase() + user.givenName.slice(1);
      setUserName(capitalizedName);
    }
  }, [user]);

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    console.log('[DashboardPage] fetchDashboardData called. Timestamp:', new Date().toISOString());
    
    if (!isAuthenticated) {
      console.log('[DashboardPage] fetchDashboardData: Not authenticated, returning early.');
      return;
    }

    if (isFetchingRef.current) {
      console.log('[DashboardPage] fetchDashboardData: Already fetching, skipping this call.');
      return;
    }

    console.log('[Dashboard] fetchDashboardData: Function started.');
    isFetchingRef.current = true;
    setIsLoading(true);
    setError(null);
    setKeyStats({
        current_documents: 0,
        deleted_documents: 0,
        total_processed_documents: 0,
        avgScore: null,
        flaggedRecent: 0,
        pending: 0
    });

    try {
      const token = await getToken();
      if (!token) {
        console.error('[Dashboard] fetchDashboardData: Failed to obtain token: Authentication token not available.');
        throw new Error(t('messages_error_authTokenMissing'));
      }
      console.log('[Dashboard] fetchDashboardData: Token obtained successfully.');

      console.log('[Dashboard] fetchDashboardData: Initiating fetch for dashboard data.');
      
      // Add timeout to prevent hanging
      const fetchWithTimeout = (promise, timeout = 10000) => {
        return Promise.race([
          promise,
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error(`Timeout after ${timeout}ms`)), timeout)
          )
        ]);
      };

      const [statsResponse, distributionResponse, recentDocsResponse] = await fetchWithTimeout(
        Promise.all([
        fetch(`${API_BASE_URL}/api/v1/dashboard/stats`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/dashboard/score-distribution`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/dashboard/recent`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        ])
      );

      console.log('[Dashboard] fetchDashboardData: Received response for /recent. Status:', recentDocsResponse.status, 'OK:', recentDocsResponse.ok);

      // Handle Stats Response
      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        setKeyStats({
            current_documents: statsData.current_documents || 0,
            deleted_documents: statsData.deleted_documents || 0,
            total_processed_documents: statsData.total_processed_documents || 0,
            avgScore: statsData.avgScore,
            flaggedRecent: statsData.flaggedRecent || 0,
            pending: statsData.pending || 0
        });
      } else {
        console.warn(`[Dashboard] Fetch failed for /api/v1/dashboard/stats. Status: ${statsResponse.status}`);
      }

      // Handle Distribution Response
      if (distributionResponse.ok) {
        const responseData = await distributionResponse.json();
        setDebugInfo(prev => ({
          ...prev,
          distributionResponse: responseData,
          lastFetch: new Date().toISOString()
        }));
        if (responseData && Array.isArray(responseData.distribution)) {
          const processedData = processDistributionData(responseData.distribution);
          setChartData(processedData);
          setDebugInfo(prev => ({
            ...prev,
            processedData
          }));
        } else {
          console.warn('[Dashboard] Score distribution response missing expected \'distribution\' array:', responseData);
          setChartData(DEFAULT_RANGES);
        }
      } else {
        console.warn(`[Dashboard] Fetch failed for /api/v1/dashboard/score-distribution. Status: ${distributionResponse.status}`);
        setChartData(DEFAULT_RANGES);
      }

      // Handle Recent Documents Response
      if (recentDocsResponse.ok) {
        try {
          const recentDocs = await recentDocsResponse.json();
          console.log('[Dashboard] fetchDashboardData: Parsed JSON from /recent:', recentDocs);

          if (Array.isArray(recentDocs)) {
            const validDocs = recentDocs.filter(doc => doc && (doc.id || doc._id));
            if (validDocs.length !== recentDocs.length) {
               console.warn("[Dashboard] Some recent documents were missing an ID and filtered out.");
            }
            console.log('[Dashboard] fetchDashboardData: Setting recentAssessments state with:', validDocs);
            setRecentAssessments(validDocs);
          } else {
            console.warn("[Dashboard] /api/v1/dashboard/recent did not return an array:", recentDocs);
            console.log('[Dashboard] fetchDashboardData: Setting recentAssessments state with: [] (due to non-array response)');
            setRecentAssessments([]);
          }
        } catch (jsonError) {
           console.error('[Dashboard] Error parsing JSON from /api/v1/dashboard/recent:', jsonError);
           console.log('[Dashboard] fetchDashboardData: Setting recentAssessments state with: [] (due to JSON parse error)');
           setRecentAssessments([]);
        }
      } else {
         console.warn(`[Dashboard] Fetch failed for /api/v1/dashboard/recent. Status: ${recentDocsResponse.status}`);
         console.log('[Dashboard] fetchDashboardData: Setting recentAssessments state with: [] (due to fetch failure)');
         setRecentAssessments([]);
      }

      // Check for any errors *after* processing all responses
      if (!statsResponse.ok || !distributionResponse.ok || !recentDocsResponse.ok) {
        // Construct a more informative error message
        const errors = [];
        if (!statsResponse.ok) errors.push(`Stats (${statsResponse.status})`);
        if (!distributionResponse.ok) errors.push(`Score Distribution (${distributionResponse.status})`);
        if (!recentDocsResponse.ok) errors.push(`Recent Docs (${recentDocsResponse.status})`);
        throw new Error(`Failed to fetch some dashboard data: ${errors.join(', ')}`);
      }
    } catch (e) {
      console.error('[Dashboard] fetchDashboardData: An error occurred:', e);
      setError(e.message || t('messages_error_dataFetchFailed'));
    } finally {
      console.log('[Dashboard] fetchDashboardData: Finally block executing - setting isLoading to false');
      setIsLoading(false);
      isFetchingRef.current = false;
      hasDataRef.current = true; // Mark that we've fetched data
      console.log('[Dashboard] fetchDashboardData: Finally block completed');
    }
  }, [isAuthenticated, t, API_BASE_URL]); // Removed getToken from dependencies to make function more stable

  // --- Simple useEffect for Data Fetching ---
  useEffect(() => {
    const loadData = async () => {
      if (!isAuthenticated || isAuthLoading) {
        console.log('[DashboardPage] loadData: Not ready to load - isAuthenticated:', isAuthenticated, 'isAuthLoading:', isAuthLoading);
        return;
      }
      
      if (hasStartedFetchRef.current) {
        console.log('[DashboardPage] loadData: Already started fetching, skipping');
        return;
      }
      
      console.log('[DashboardPage] loadData: Starting data fetch');
      hasStartedFetchRef.current = true;
      setIsLoading(true);
      
      try {
        console.log('[DashboardPage] loadData: About to call getToken()');
        
        // Add timeout to getToken call
        const getTokenWithTimeout = () => {
          return Promise.race([
            getToken(),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('getToken timeout after 3 seconds')), 3000)
            )
          ]);
        };
        
        const token = await getTokenWithTimeout();
        console.log('[DashboardPage] loadData: getToken() completed, token length:', token ? token.length : 'null');
        
        if (!token) {
          console.log('[DashboardPage] loadData: No token, returning');
          return;
        }
        
        console.log('[DashboardPage] loadData: Fetching recent data only (simplified)');
        
        // Add timeout to prevent hanging
        const fetchWithTimeout = (url, options, timeout = 5000) => {
          return Promise.race([
            fetch(url, options),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error(`Timeout after ${timeout}ms`)), timeout)
            )
          ]);
        };
        
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/v1/dashboard/recent`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
          const data = await response.json();
          console.log('[DashboardPage] loadData: Got recent data:', data);
          setRecentAssessments(Array.isArray(data) ? data : []);
          hasDataRef.current = true; // Mark successful data fetch
          console.log('[DashboardPage] loadData: Set hasDataRef.current to true');
          setDataLoaded(true); // Force re-render with state update
          console.log('[DashboardPage] loadData: Set dataLoaded to true');
          
          // Force immediate re-render by updating isLoading right after dataLoaded
          setTimeout(() => {
            console.log('[DashboardPage] loadData: Forcing isLoading false via setTimeout');
            setIsLoading(false);
          }, 0);
        } else {
          console.log('[DashboardPage] loadData: Response not OK, status:', response.status);
        }
      } catch (error) {
        console.error('[DashboardPage] loadData: Error:', error);
        setError(error.message);
      } finally {
        console.log('[DashboardPage] loadData: Finally block (not setting isLoading here anymore)');
      }
    };
    
    // Only run if authenticated and ready
    if (isAuthenticated && !isAuthLoading) {
      loadData();
    }
  }, []); // Empty dependency array - only run once on mount

  // --- Sorting Logic ---
  const handleSort = (field) => {
    const newSortOrder = sortField === field && sortOrder === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortOrder(newSortOrder);
  };

  // Quick Start Button Handler (navigates to /quickstart)
  // Kept for potential future use if a button needs this specific handler,
  // but the restored card uses <Link>.
  const handleQuickStart = () => {
    navigate('/quickstart');
  };

  // Helper to format score for table
  const formatScore = (score) => {
    if (typeof score !== 'number' || isNaN(score)) {
        return 'N/A';
    }
    // If score is already in percentage form (>1), use as is
    // If score is in decimal form (<1), multiply by 100
    const normalizedScore = score > 1 ? score : score * 100;
    return `${normalizedScore.toFixed(1)}%`;
  };

  // Helper for status badge in table
  const getStatusBadge = (status) => {
     switch(status?.toUpperCase()) {
       case 'COMPLETED': return <span className="badge badge-success badge-outline text-xs">{status}</span>;
       case 'PROCESSING':
       case 'QUEUED': return <span className="badge badge-info badge-outline text-xs">{status}</span>;
       case 'ERROR': return <span className="badge badge-error badge-outline text-xs">{status}</span>;
       case 'UPLOADED': return <span className="badge badge-ghost text-xs">{status}</span>;
       default: return <span className="badge badge-ghost text-xs">{status || 'N/A'}</span>;
     }
  };

  // --- Main Render ---
  if (isAuthLoading) {
    console.log('[DashboardPage] Render: Kinde is loading (isAuthLoading). Timestamp:', new Date().toISOString());
    return <div className="flex items-center justify-center min-h-screen">
      <div className="loading loading-spinner loading-lg"></div>
    </div>;
  }

  // --- Render Login Prompt if not Authenticated ---
  if (!isAuthenticated && !isAuthLoading) {
    console.log('[DashboardPage] Render: Not authenticated and Kinde not loading. Timestamp:', new Date().toISOString());
    return <div className="alert alert-info shadow-lg">
      <div>
        <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0"/>
        <span>Please log in to view the dashboard.</span>
      </div>
    </div>;
  }

  // --- Render Loading State ---
  const shouldShowLoading = authLoading; // Only show loading for auth loading
  console.log('[DashboardPage] Render condition check - isLoading:', isLoading, 'authLoading:', authLoading, 'dataLoaded:', dataLoaded, 'shouldShowLoading:', shouldShowLoading);
  
  if (shouldShowLoading) { // Only show loading for auth
    console.log('[DashboardPage] Render: authLoading is true. Timestamp:', new Date().toISOString());
    return <div className="flex items-center justify-center min-h-screen">
      <div className="loading loading-spinner loading-lg"></div>
    </div>;
  }

  // --- Render Error State ---
  if (error) {
    console.log('[DashboardPage] Render: Error state. Error:', error, '. Timestamp:', new Date().toISOString());
    return <div className="alert alert-error shadow-lg">
      <div>
        <ExclamationTriangleIcon className="h-6 w-6 stroke-current shrink-0"/>
        <span>{error}</span>
      </div>
    </div>;
  }

  console.log('[Dashboard] Rendering component. Current recentAssessments state:', recentAssessments);

  // --- Render Dashboard Grid ---
  console.log('[DashboardPage] Rendering. Current keyStats:', keyStats);
  console.log('[DashboardPage] Render: Main content. Timestamp:', new Date().toISOString());

  const sortedAssessments = [...recentAssessments].sort((a, b) => {
    if (!sortField) return 0;

    let valA = a[sortField];
    let valB = b[sortField];

    // Handle date sorting for upload_timestamp
    if (sortField === 'upload_timestamp') {
      valA = new Date(a.upload_timestamp || a.created_at);
      valB = new Date(b.upload_timestamp || b.created_at);
    }

    if (valA < valB) {
      return sortOrder === 'asc' ? -1 : 1;
    }
    if (valA > valB) {
      return sortOrder === 'asc' ? 1 : -1;
    }
    return 0;
  });

  return (
    <div className="space-y-6 container mx-auto p-4 md:p-6">

      {/* --- Row 1: Welcome/QuickStart (Left) & Chart (Right) --- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Column 1: Welcome Message & Quick Start Button */}
        <div 
          className="p-6 rounded-lg shadow-md border border-base-300 bg-base-100 relative overflow-hidden flex flex-col"
        >
          <div className="relative z-10 flex flex-col flex-grow space-y-3">
            <div className="flex-grow">
              <h2 className="text-2xl font-semibold text-base-content mb-2">
                {t('dashboardPage_welcome')} {userName || 'User'}!
          </h2>
              <div className="my-3 border-t border-base-content/20"></div>

              {!authLoading && currentUser ? (
                <div className="text-lg text-base-content/90 space-y-1">
                  <p>
                    {t('dashboardPage_plan_prefix', 'You are on the ')} 
                    <span className="font-semibold">{getPlanDisplayName(currentUser.current_plan)}</span>.
                  </p>
                  {currentUser.current_plan !== 'SCHOOLS' && (
                    <>
                      <p>
                        {t('dashboardPage_wordLimit_prefix', 'Monthly limit: ')}
                        <span className="font-semibold">{currentUser.current_plan_word_limit?.toLocaleString() || t('common_text_notApplicable')}</span> 
                        {t('dashboardPage_wordLimit_suffix', ' words.')}
                      </p>
                      <p>
                        {t('dashboardPage_wordsRemaining_prefix', 'Words remaining: ')}
                        <span className="font-semibold">
                          {(currentUser.current_plan_word_limit - currentUser.words_used_current_cycle) > 0 
                            ? (currentUser.current_plan_word_limit - currentUser.words_used_current_cycle)?.toLocaleString() 
                            : 0
                          }
                        </span>.
                      </p>
                    </>
                  )}
                  <p>
                    {t('dashboardPage_docsProcessed_prefix', 'Documents processed this cycle: ')}
                    <span className="font-semibold">{currentUser.documents_processed_current_cycle || 0}</span>.
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  {[...Array(3)].map((_, i) => (
                      <div key={i} className="h-4 bg-gray-300 rounded w-3/4 animate-pulse"></div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-auto flex justify-end pt-2">
            <Link
              to="/quickstart"
                className="btn btn-primary btn-md group"
            >
                <ArrowUpTrayIcon className="w-5 h-5 mr-2 transition-transform duration-300 ease-in-out group-hover:-translate-y-0.5" />
              {t('dashboardPage_button_quickStart')}
            </Link>
            </div>
          </div>
        </div>

        {/* Column 2: Score Distribution Chart */}
        <div className="card bg-base-100 shadow-md border border-base-300">
          <div className="card-body">
            <h2 className="card-title text-xl mb-4">{t('dashboardPage_chart_heading')}</h2>
            <ScoreDistributionChart data={chartData} />
          </div>
        </div>
      </div>

      {/* --- Row 2: Key Stats (Full Width) --- */}
      <div className="stats shadow w-full">
        <div className="stat">
          <div className="stat-figure text-primary"><DocumentDuplicateIcon className="h-8 w-8"/></div>
          <div className="stat-title">{t('dashboard_stat_totalDocuments', 'Total Documents')}</div>
          <div className="stat-value">{keyStats?.total_processed_documents || '0'}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-secondary"><ScaleIcon className="h-8 w-8"/></div>
          <div className="stat-title">{t('dashboard_stat_avgScore', 'Average AI Score')}</div>
          <div className="stat-value">{formatScore(keyStats?.avgScore)}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-accent"><CheckBadgeIcon className="h-8 w-8"/></div>
          <div className="stat-title">{t('dashboard_stat_flaggedRecent', 'Flagged Recently')}</div>
          <div className="stat-value">{keyStats?.flaggedRecent || '0'}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-info"><ClockIcon className="h-8 w-8"/></div>
          <div className="stat-title">{t('dashboard_stat_pendingProcessing', 'Pending / Processing')}</div>
          <div className="stat-value">{keyStats?.pending || '0'}</div>
        </div>
      </div>

      {/* --- Row 3: Recent Assessments Table (Full Width) --- */}
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h2 className="card-title text-xl">{t('dashboard_table_heading_recent', 'Recent Assessments')}</h2>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate('/documents')}>{t('common_button_viewAll', 'View All')}</button>
          </div>
          <div className="overflow-x-auto">
            {sortedAssessments.length > 0 ? (
              <table className="min-w-full divide-y divide-base-300">
                <thead className="bg-base-200">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-base-content uppercase tracking-wider">
                      <button onClick={() => handleSort('original_filename')} className="btn btn-ghost btn-xs p-0 hover:bg-transparent normal-case font-medium flex items-center">
                        {t('dashboard_table_filename')}
                        <span className="ml-2">
                          {sortField === 'original_filename' ? 
                            (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />) : 
                            <ArrowsUpDownIcon className="h-4 w-4 text-gray-400" />}
                        </span>
                      </button>
                    </th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-base-content uppercase tracking-wider">
                       <button onClick={() => handleSort('upload_timestamp')} className="btn btn-ghost btn-xs p-0 hover:bg-transparent normal-case font-medium flex items-center">
                        {t('dashboard_table_date')}
                        <span className="ml-2">
                          {sortField === 'upload_timestamp' ? 
                            (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />) : 
                            <ArrowsUpDownIcon className="h-4 w-4 text-gray-400" />}
                        </span>
                      </button>
                    </th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-base-content uppercase tracking-wider">{t('dashboard_table_status')}</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-base-content uppercase tracking-wider">{t('dashboard_table_ai_score')}</th>
                    <th scope="col" className="relative px-4 py-3">
                      <span className="sr-only">{t('dashboard_table_view')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-base-100 divide-y divide-base-300">
                  {sortedAssessments.map((doc) => (
                    <tr key={doc.id || doc._id} className="hover:bg-base-200 transition-colors duration-150">
                      <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-base-content truncate max-w-xs" title={doc.original_filename}>
                        {doc.original_filename}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-base-content/80">
                        {new Date(doc.upload_timestamp || doc.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm">
                        {getStatusBadge(doc.status)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-base-content/80">
                        {formatScore(doc.score)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => navigate(`/documents/${doc.id || doc._id}/report`)}
                          className="btn btn-ghost btn-xs"
                        >
                          <EyeIcon className="h-4 w-4"/> {t('common_button_view', 'View')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-center py-4 text-base-content/70">
                {t('dashboardPage_noAssessments')}
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}

export default DashboardPage;