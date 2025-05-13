// src/components/AIDetectionReportPage.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';

// --- Import specific icons ---
import {
  ArrowLeftIcon, // For Back link
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon
} from '@heroicons/react/24/outline';
// -----------------------------

// --- Import useTranslation if needed for this component's text ---
// import { useTranslation } from 'react-i18next';
// -----------------------------------------------------------------

// Get API base URL from environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

// Helper function to format score as percentage
const formatScore = (score) => {
    if (typeof score !== 'number' || isNaN(score)) {
        return 'N/A';
    }
    // Handle both decimal and percentage scores
    const normalizedScore = score > 1 ? score : score * 100;
    return `${normalizedScore.toFixed(1)}%`;
};

// Helper function to format boolean values
const formatBoolean = (value) => {
    if (typeof value !== 'boolean') {
        return 'N/A';
    }
    // Using DaisyUI badge styling for boolean might be clearer
    return value
      ? <span className="badge badge-error badge-sm">Yes</span> // Assuming 'Yes' for AI is the 'alert' state
      : <span className="badge badge-success badge-sm">No</span>; // And 'No' is the 'success' state (Human)
    // Alternatively, simple text: return value ? 'Yes' : 'No';
};

// --- Updated Helper function to determine highlight class using DaisyUI/Theme colors ---
const getHighlightClass = (label) => {
    // Highlight if label indicates AI generation (case-insensitive)
    if (label && typeof label === 'string' && label.toLowerCase().includes('ai-generated')) {
        return 'bg-error text-error-content p-1 rounded'; // Changed to use full opacity and text-error-content
    }
    // Example: Highlight human-written text differently (Optional)
    // if (label && typeof label === 'string' && label.toLowerCase().includes('human-written')) {
    //     return 'bg-success/20 p-1 rounded'; // Example: Light green background
    // }

    // Default: Apply padding for consistent spacing even if not highlighted
    return 'p-1'; // Restored default padding
};


function AIDetectionReportPage() {
    // const { t } = useTranslation(); // Uncomment if using translations here
    const { documentId } = useParams();
    const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();

    const [reportData, setReportData] = useState(null);
    const [documentInfo, setDocumentInfo] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    // Fetch document metadata (Callback logic unchanged)
    const fetchDocumentInfo = useCallback(async (token) => {
        if (!documentId || !token) return;
        try {
            const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (!response.ok) { console.error(`Failed to fetch document info: ${response.status}`); return; }
            const data = await response.json(); setDocumentInfo(data);
        } catch (err) { console.error("Error fetching document info:", err); }
    }, [documentId]);

    // Fetch the detailed AI detection result data (Callback logic unchanged)
    const fetchReportData = useCallback(async (token) => {
        if (!documentId || !token) return;
        setIsLoading(true); setError(null); setReportData(null);
        try {
            const response = await fetch(`${API_BASE_URL}/results/document/${documentId}`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (!response.ok) {
                let errorDetail = `HTTP error ${response.status}`;
                try { const errData = await response.json(); errorDetail = errData.detail || `Status ${response.status}`; } catch (e) { const textError = await response.text(); errorDetail = textError || `Status ${response.status}`; }
                if (response.status === 404) { errorDetail = "No assessment result found for this document."; }
                throw new Error(errorDetail);
            }
            const data = await response.json();
            if (data && data.status === 'COMPLETED') {
                if (!Array.isArray(data.paragraph_results)) { console.warn("Paragraph results missing or not an array:", data); data.paragraph_results = []; }
                setReportData(data);
            } else { setError(`Assessment status is ${data?.status || 'Unknown'}. Report is only available when completed.`); setReportData(null); }
        } catch (err) { console.error("Error fetching AI detection report:", err); setError(err.message || "An unknown error occurred while fetching the report."); setReportData(null); }
        finally { setIsLoading(false); }
    }, [documentId]);

    // Effect to fetch data (Effect logic unchanged)
    useEffect(() => {
        if (!isAuthLoading && isAuthenticated) {
            getToken().then(token => {
                if (token) { Promise.all([ fetchDocumentInfo(token), fetchReportData(token) ]); }
                else { setError("Authentication token not available."); setIsLoading(false); }
            }).catch(err => { setError("Failed to get authentication token."); setIsLoading(false); console.error("Kinde getToken error:", err); });
        } else if (!isAuthLoading && !isAuthenticated) { setError("Please log in to view the report."); setIsLoading(false); }
    }, [documentId, isAuthenticated, isAuthLoading, getToken, fetchDocumentInfo, fetchReportData]);

    // --- Render Logic ---

    // Loading State UI - Using DaisyUI Loader
    if (isLoading) {
        return (
            <div className="flex justify-center items-center h-48">
                <span className="loading loading-lg loading-spinner text-primary"></span>
                <span className="ml-3 text-base-content">Loading AI Detection Report...</span> {/* Use text-base-content */}
            </div>
        );
    }

    // Error State UI - Using DaisyUI Alert
    if (error) {
        return (
            <div>
                {/* Using H2 style */}
                <h1 className="text-3xl font-semibold text-base-content mb-4">AI Detection Report</h1>
                {/* Using DaisyUI Alert */}
                <div role="alert" className="alert alert-error mb-4">
                    <XCircleIcon className="h-6 w-6"/>
                    <div>
                        <h3 className="font-bold">Error loading report</h3>
                        <div className="text-xs">{error}</div>
                    </div>
                </div>
                {/* Using DaisyUI Link */}
                <Link to="/documents" className="link link-primary link-hover text-sm inline-flex items-center">
                    <ArrowLeftIcon className="h-4 w-4 mr-1"/> Back to Documents
                </Link>
            </div>
        );
    }

    // No Data State - Using DaisyUI Alert (Warning)
    if (!reportData) {
        return (
            <div>
                <h1 className="text-3xl font-semibold text-base-content mb-4">AI Detection Report</h1>
                <div role="alert" className="alert alert-warning mb-4">
                    <ExclamationTriangleIcon className="h-6 w-6"/>
                    <span>No report data available. The assessment might still be pending or encountered an issue.</span>
                </div>
                <Link to="/documents" className="link link-primary link-hover text-sm inline-flex items-center">
                    <ArrowLeftIcon className="h-4 w-4 mr-1"/> Back to Documents
                </Link>
            </div>
        );
    }

    // Success State - Display Report - Using DaisyUI Card, Stats, Text styles
    return (
        <div>
            {/* Header - Using H2 style, Body Small style */}
            <h1 className="text-3xl font-semibold text-base-content mb-1">AI Detection Report</h1>
            <p className="text-sm text-base-content/70 mb-6">
                Document: <span className="font-medium">{documentInfo?.original_filename || `ID: ${documentId}`}</span>
            </p>

            {/* Main Content Card */}
            <div className="card bg-base-100 shadow-xl border border-base-300">
                <div className="card-body">

                    {/* Summary Section - Using H3 style, DaisyUI Stats component */}
                    <h2 className="card-title text-xl font-medium text-base-content mb-4 border-b border-base-300 pb-2">Summary</h2>
                    <div className="stats stats-vertical lg:stats-horizontal shadow mb-6 bg-base-200">
                        {/* Score Stat */}
                        <div className="stat">
                            <div className="stat-title text-sm">Overall AI Probability</div>
                            {/* Using primary color for score */}
                            <div className="stat-value text-primary">{formatScore(reportData.score)}</div>
                            <div className="stat-desc text-xs">(Higher score = higher likelihood)</div>
                        </div>
                        {/* Label Stat */}
                        <div className="stat">
                            <div className="stat-title text-sm">Overall Classification</div>
                            {/* Using secondary or info color */}
                            <div className="stat-value text-info text-2xl">{reportData.label || 'N/A'}</div>
                        </div>
                    </div>

                    {/* Additional Metadata - Using Body Small style */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 mb-6 text-sm">
                        <div>
                            <span className="text-base-content/70">Likely AI Generated (Overall):</span>
                            <span className="font-medium ml-2">{formatBoolean(reportData.ai_generated)}</span>
                        </div>
                        <div>
                            <span className="text-base-content/70">Likely Human Generated (Overall):</span>
                            <span className="font-medium ml-2">{formatBoolean(reportData.human_generated)}</span>
                        </div>
                        <div>
                            <span className="text-base-content/70">Assessment Timestamp:</span>
                            <span className="text-base-content ml-2">
                                {reportData.result_timestamp ? new Date(reportData.result_timestamp).toLocaleString() : 'N/A'}
                            </span>
                        </div>
                        <div>
                            <span className="text-base-content/70">Result ID:</span>
                            <span className="text-base-content text-xs font-mono ml-2">{reportData.id}</span>
                        </div>
                        {/* Added Character Count */}
                        <div>
                            <span className="text-base-content/70">Character Count:</span>
                            <span className="text-base-content ml-2">
                                {documentInfo?.character_count?.toLocaleString() ?? 'N/A'}
                            </span>
                        </div>
                        {/* Added Word Count */}
                        <div>
                            <span className="text-base-content/70">Word Count:</span>
                            <span className="text-base-content ml-2">
                                {documentInfo?.word_count?.toLocaleString() ?? 'N/A'}
                            </span>
                        </div>
                    </div>

                    {/* Detailed Analysis Section - Using H3 style */}
                    <h2 className="card-title text-xl font-medium text-base-content mb-4 border-b border-base-300 pb-2 mt-8">Detailed Analysis (Highlighted Text)</h2>
                    {reportData.paragraph_results && reportData.paragraph_results.length > 0 ? (
                        <div className="space-y-4 bg-base-200 p-4 rounded border border-base-300 max-h-[60vh] overflow-y-auto text-base-content leading-relaxed">
                            {reportData.paragraph_results.map((paraResult, index) => {
                                // If paraResult.spans exists, use it to highlight only AI-generated text
                                if (Array.isArray(paraResult.spans)) {
                                    return (
                                        <div key={index} className="pb-2 mb-2 border-b border-base-300 last:border-b-0">
                                            <p className="text-sm whitespace-pre-wrap">
                                                {paraResult.spans.map((span, i) => {
                                                    const highlight = span.label && span.label.toLowerCase().includes('ai-generated');
                                                    return (
                                                        <span key={i} className={highlight ? 'bg-error text-error-content p-1 rounded' : ''}>
                                                            {span.text}
                                                        </span>
                                                    );
                                                })}
                                            </p>
                                        </div>
                                    );
                                }
                                // Fallback: highlight the whole paragraph if no spans
                                return (
                                    <div key={index} className="pb-2 mb-2 border-b border-base-300 last:border-b-0">
                                        <p className={`text-sm whitespace-pre-wrap ${getHighlightClass(paraResult.label)}`}>
                                            {paraResult.paragraph || '[Empty Paragraph Content]'}
                                        </p>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <p className="text-sm text-base-content/70 italic mt-4">No paragraph-level analysis results available.</p>
                    )}

                    {/* Footer Navigation */}
                    <div className="card-actions justify-start mt-6 pt-4 border-t border-base-300">
                        <Link to="/documents" className="link link-primary link-hover text-sm inline-flex items-center">
                            <ArrowLeftIcon className="h-4 w-4 mr-1"/> Back to Documents List
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default AIDetectionReportPage;