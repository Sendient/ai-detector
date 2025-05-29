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
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading, getToken, user } = useKindeAuth();
  const navigate = useNavigate();
  const { currentUser, loading: authLoading } = useAuth(); // Added useAuth and authLoading

  // --- State for Dashboard Data ---
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
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

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  // Helper function to get plan display name
  const getPlanDisplayName = (planString) => {
    if (authLoading || isAuthLoading) return 'Loading...'; // Show loading state
    if (planString) {
        const formattedPlan = planString.charAt(0).toUpperCase() + planString.slice(1);
        return `${formattedPlan} Plan`;
    }
    if (isAuthenticated) { // If authenticated but no plan string, default to Free Plan
        return t('header_free_plan', 'Free Plan');
    }
    return 'Plan N/A'; // Fallback if not authenticated or no plan info
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
    if (!isAuthenticated) return;

    console.log('[Dashboard] fetchDashboardData: Function started.');
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
      const [statsResponse, distributionResponse, recentDocsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/dashboard/stats`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/dashboard/score-distribution`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/dashboard/recent`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);

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
    } catch (error) {
      if (!error.message.includes(t('messages_error_authTokenMissing'))) {
         console.error('[Dashboard] fetchDashboardData: Caught error:', error.message);
      }
      setError(error.message);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, getToken, t]);

  // Effect to fetch dashboard data - Keep simplified dependencies
  useEffect(() => {
    if (isAuthenticated && !isAuthLoading) {
      console.log('[Dashboard] useEffect trigger: Fetching data. isAuthenticated:', isAuthenticated, 'isAuthLoading:', isAuthLoading);
      fetchDashboardData();
    } else if (!isAuthLoading && !isAuthenticated) {
      console.log('[Dashboard] useEffect trigger: Not authenticated, redirecting to login.');
      navigate('/');
    }
  }, [isAuthenticated, isAuthLoading, fetchDashboardData, navigate]);

  // --- Sorting Logic ---
  const handleSort = (field) => {
    const newSortOrder = sortField === field && sortOrder === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortOrder(newSortOrder);
  };

  // Quick Start Button Handler
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

  // --- Render Login Prompt if not Authenticated ---
  if (!isAuthenticated && !isAuthLoading) {
    return <div className="alert alert-info shadow-lg">
      <div>
        <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0"/>
        <span>Please log in to view the dashboard.</span>
      </div>
    </div>;
  }

  // --- Render Loading State ---
  if (isLoading || isAuthLoading) {
    return <div className="flex items-center justify-center min-h-screen">
      <div className="loading loading-spinner loading-lg"></div>
    </div>;
  }

  // --- Render Error State ---
  if (error) {
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
    <div className="space-y-6">

      {/* --- Row 1: Welcome/QuickStart (Left) & Chart (Right) --- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Column 1: Welcome Message & Quick Start Button with Image */}
        <div 
          className="p-6 rounded-lg shadow-md border border-base-300 bg-base-100 relative overflow-hidden"
        >
          {/* Image as a layer, behind the content - REMOVED */}
          
          {/* Content - on top of the image. Added left padding to shift content right. */}
          <div className="relative z-10 space-y-4 pl-8">
            <h2 className="text-2xl font-semibold text-base-content mb-4">
              {t('dashboardPage_welcome')} {userName}
            </h2>
            {currentUser && ( // Added plan display
              <div className="text-sm text-base-content/80">
                <p>
                  You are on the '{getPlanDisplayName(currentUser.current_plan)}' plan.
                </p>
                {currentUser.current_plan !== 'schools' ? (
                  <>
                    <p>
                      You have {currentUser.current_plan_word_limit?.toLocaleString() || 'N/A'} words to assess this month.
                    </p>
                    <p>
                      You have {currentUser.remaining_words_current_cycle?.toLocaleString() || 'N/A'} words left on your plan.
                    </p>
                     <p>
                      You have processed {currentUser.documents_processed_current_cycle?.toLocaleString() || '0'} documents this cycle.
                    </p>
                  </>
                ) : (
                  <p>You have unlimited words and document processing.</p>
                )}
              </div>
            )}
            <div className="flex justify-start">
              <Link
                to="/quickstart"
                className="btn btn-primary"
              >
                <ArrowUpTrayIcon className="h-5 w-5 mr-2"/>
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
          <div className="stat-title">Total Documents</div>
          <div className="stat-value">{keyStats?.total_processed_documents || '0'}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-secondary"><ScaleIcon className="h-8 w-8"/></div>
          <div className="stat-title">Average AI Score</div>
          <div className="stat-value">{formatScore(keyStats?.avgScore)}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-accent"><CheckBadgeIcon className="h-8 w-8"/></div>
          <div className="stat-title">Flagged Recently</div>
          <div className="stat-value">{keyStats?.flaggedRecent || '0'}</div>
        </div>
        <div className="stat">
          <div className="stat-figure text-info"><ClockIcon className="h-8 w-8"/></div>
          <div className="stat-title">Pending / Processing</div>
          <div className="stat-value">{keyStats?.pending || '0'}</div>
        </div>
      </div>

      {/* --- Row 3: Recent Assessments Table (Full Width) --- */}
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h2 className="card-title text-xl">Recent Assessments</h2>
            <button className="btn btn-sm btn-ghost" onClick={() => navigate('/documents')}>View All</button>
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
                        {new Date(doc.upload_timestamp || doc.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm">
                        {getStatusBadge(doc.status)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-base-content/80">
                        {formatScore(doc.score)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => navigate(`/documents/${doc.id}/report`)}
                          className="btn btn-ghost btn-xs"
                        >
                          <EyeIcon className="h-4 w-4"/> View
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