import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import {
  ArrowPathIcon,
  PencilSquareIcon,
  TrashIcon,
  EyeIcon,
  DocumentTextIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  XCircleIcon,
  StopCircleIcon,
} from '@heroicons/react/24/outline';

function DocumentsPage() {
  const { t } = useTranslation();
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  
  const UPLOADED_STATUS = 'UPLOADED';
  const COMPLETED_STATUS = 'COMPLETED';
  const ERROR_STATUS = 'ERROR';
  const PROCESSING_STATUS = 'PROCESSING';
  const QUEUED_STATUS = 'QUEUED';

  const navigate = useNavigate();
  const [assessmentStatus, setAssessmentStatus] = useState({});
  const [assessmentResults, setAssessmentResults] = useState({});
  const [assessmentErrors, setAssessmentErrors] = useState({});
  const supportedTextTypes = ['pdf', 'docx', 'txt', 'text'];
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [deleteSuccess, setDeleteSuccess] = useState(null);
  const [cancellingStatus, setCancellingStatus] = useState({});

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  const fetchResultsForDocuments = useCallback(async (docIds, token) => {
    if (!token || !docIds || docIds.length === 0) return;
    console.log(`[DocumentsPage] Fetching results for docs: ${docIds.join(', ')}`);
    const resultsPromises = docIds.map(docId =>
        fetch(`${API_BASE_URL}/api/v1/results/document/${docId}`, { headers: { 'Authorization': `Bearer ${token}` } })
            .then(async res => {
                if (!res.ok) {
                    let detail = `Status: ${res.status}`;
                    try { const errData = await res.json(); detail = errData.detail || detail; } catch (e) { /* Ignore */ }
                    console.warn(`Failed to fetch result for doc ${docId}: ${detail}`);
                    return { docId, status: 'failed', error: res.status };
                }
                const resultData = await res.json();
                return { docId, status: 'fulfilled', data: resultData };
            })
            .catch(err => {
                console.error(`Network or other error fetching result for doc ${docId}:`, err);
                return { docId, status: 'failed', error: err.message || 'Network error' };
            })
    );
    const resultsSettled = await Promise.allSettled(resultsPromises);
    setAssessmentResults(prevResults => {
        const newResults = { ...prevResults };
        resultsSettled.forEach(promiseResult => {
            if (promiseResult.status === 'fulfilled' && promiseResult.value?.status === 'fulfilled') {
                const { docId, data } = promiseResult.value;
                if (data?.status === COMPLETED_STATUS && typeof data?.score === 'number') {
                    newResults[docId] = data.score;
                    console.log(`[DocumentsPage] Stored score ${data.score} for completed doc ${docId}`);
                } else {
                    delete newResults[docId];
                    console.log(`[DocumentsPage] Result for doc ${docId} status is ${data?.status}, score not stored/updated.`);
                }
            } else if (promiseResult.status === 'fulfilled' && promiseResult.value?.status === 'failed') {
                const { docId } = promiseResult.value;
                delete newResults[docId];
                console.log(`[DocumentsPage] Fetch failed for result of doc ${docId}. Status: ${promiseResult.value?.error}`);
            } else if (promiseResult.status === 'rejected') {
                 console.error("[DocumentsPage] Promise rejected while fetching results:", promiseResult.reason);
            }
        });
        return newResults;
    });
  }, [COMPLETED_STATUS]);

  const fetchDocuments = useCallback(async () => {
    if (isAuthenticated) {
      setIsLoading(true); setError(null);
      try {
        const token = await getToken();
        if (!token) { throw new Error(t('messages_error_authTokenMissing')); }
        const response = await fetch(`${API_BASE_URL}/api/v1/documents/`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try { const errData = await response.json(); errorDetail = errData.detail || errorDetail; } catch (e) { /* Ignore */ }
            throw new Error(t('messages_docs_fetchError', { message: errorDetail }));
        }
        const data = await response.json();
        const mappedData = data.map(doc => ({ ...doc, id: doc._id || doc.id })).filter(doc => doc.id);
        console.log('[DocumentsPage] Mapped data before setting state:', mappedData);
        setDocuments(mappedData);
        const completedDocIds = mappedData.filter(doc => doc.status === COMPLETED_STATUS).map(doc => doc.id);
        if (completedDocIds.length > 0 && token) {
            await fetchResultsForDocuments(completedDocIds, token);
        }
      } catch (err) {
        console.error("Error fetching documents:", err);
        setError(err.message || t('messages_error_unexpected'));
      } finally { setIsLoading(false); }
    } else {
        setDocuments([]);
        setIsLoading(false);
        if (!isAuthLoading) {
            setError(t('messages_error_loginRequired_viewDocs'));
        }
    }
  }, [isAuthenticated, isAuthLoading, getToken, fetchResultsForDocuments, t, COMPLETED_STATUS]);

  const handleFileChange = (event) => {
    if (event.target.files && event.target.files[0]) { setSelectedFile(event.target.files[0]); setUploadStatus(''); }
  };

  const handleUpload = async () => {
    const uploadingStatusText = 'Uploading';
    if (!selectedFile) { setUploadStatus(t('messages_upload_selectFile')); return; }
    if (!isAuthenticated) { setUploadStatus(t('messages_error_loginRequired_upload')); return; }
    setUploadStatus(uploadingStatusText);
    setError(null);
    const placeholderStudentId = "00000000-0000-0000-0000-000000000001";
    const placeholderAssignmentId = "00000000-0000-0000-0000-000000000002";

    try {
        const token = await getToken();
        if (!token) { throw new Error(t('messages_error_authTokenMissing')); }
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('student_id', placeholderStudentId);
        formData.append('assignment_id', placeholderAssignmentId);
        const response = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData });
        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try { const errData = await response.json(); console.error('[DocumentsPage] Upload Error Response Body:', errData); errorDetail = errData.detail || errorDetail; } catch (e) { const textError = await response.text(); console.error('[DocumentsPage] Upload Error Response Text:', textError); errorDetail = textError || errorDetail; }
            throw new Error(t('messages_upload_failed', { detail: errorDetail }));
        }
        const result = await response.json();
        console.log('[DocumentsPage] Upload successful:', result);
        setUploadStatus(t('messages_upload_success', { id: result.id }));
        setSelectedFile(null);
        const fileInput = document.getElementById('document-upload-input');
        if (fileInput) { fileInput.value = ''; }
        setTimeout(() => { fetchDocuments(); setUploadStatus(''); }, 1000);
    } catch (err) {
        console.error("Error uploading document:", err);
        setUploadStatus(t('messages_upload_error', { message: err.message }));
    }
  };

  const handleAssess = async (documentId) => {
    if (!isAuthenticated) {
        console.error("Assessment failed: User not authenticated.");
        setError(t('messages_error_loginRequired_assess'));
        return;
    }
    console.log(`[DocumentsPage] Initiating assessment for document ID: ${documentId}`);
    setAssessmentStatus(prev => ({ ...prev, [documentId]: 'loading' }));
    setAssessmentErrors(prev => { const newErrors = {...prev}; delete newErrors[documentId]; return newErrors; });
    setError(null);

    try {
        const token = await getToken();
        if (!token) { throw new Error(t('messages_error_authTokenMissing')); }
        const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/assess`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
        
        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try { 
                const errData = await response.json(); 
                errorDetail = errData.detail || errorDetail; 
            } catch (e) { 
                const textError = await response.text(); 
                errorDetail = textError || errorDetail; 
            }
            throw new Error(t('messages_assessment_failed', { detail: errorDetail }));
        }
        
        const resultData = await response.json();
        console.log(`[DocumentsPage] Assessment successful for ${documentId}:`, resultData);
        setAssessmentStatus(prev => ({ ...prev, [documentId]: 'success' }));
        
        if (resultData && typeof resultData.score === 'number') {
            setAssessmentResults(prev => ({ ...prev, [documentId]: resultData.score }));
        } else {
            console.warn(`Assessment completed for ${documentId}, but score missing/invalid in response:`, resultData);
        }
        
        // Wait for the document status to update
        await fetchDocuments();
        
        // Automatically navigate to the report page
        navigate(`/documents/${documentId}/report`);
        
    } catch (err) {
        const errorMessage = err.message || t('messages_assessment_errorUnknown');
        console.error(`Error assessing document ${documentId}:`, errorMessage);
        setError(null);
        setAssessmentStatus(prev => ({ ...prev, [documentId]: 'error' }));
        setAssessmentErrors(prev => ({ ...prev, [documentId]: errorMessage }));
    }
  };

  const handleViewText = (documentId) => { navigate(`/documents/${documentId}/text-view`); };
  const handleViewReport = (documentId) => { navigate(`/documents/${documentId}/report`); };

  const handleDeleteClick = (docId) => {
    setDeletingDocId(docId);
    setShowDeleteModal(true);
    setDeleteError(null);
    setDeleteSuccess(null);
  };

  const handleConfirmDelete = async () => {
    if (!deletingDocId) return;
    setDeleteLoading(true);
    setDeleteError(null);
    setDeleteSuccess(null);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${API_BASE_URL}/api/v1/documents/${deletingDocId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!response.ok) {
        let errorDetail = `HTTP error ${response.status}`;
        try { const errData = await response.json(); errorDetail = errData.detail || errorDetail; } catch (e) { const textError = await response.text(); errorDetail = textError || errorDetail; }
        throw new Error(t('messages_delete_failed', { detail: errorDetail }));
      }
      setDeleteSuccess(t('messages_delete_success'));
      setTimeout(() => {
        setShowDeleteModal(false);
        setDeletingDocId(null);
        setDeleteSuccess(null);
        fetchDocuments();
      }, 1000);
    } catch (err) {
      setDeleteError(err.message || t('messages_delete_failed_default'));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setShowDeleteModal(false);
    setDeletingDocId(null);
    setDeleteError(null);
    setDeleteSuccess(null);
  };

  const handleCancelAssessment = async (documentId) => {
    if (!isAuthenticated) {
        console.error("Cancellation failed: User not authenticated.");
        return;
    }
    console.log(`[DocumentsPage] Initiating cancellation for document ID: ${documentId}`);
    setCancellingStatus(prev => ({ ...prev, [documentId]: 'loading' }));
    setAssessmentErrors(prev => { const newErrors = {...prev}; delete newErrors[documentId]; return newErrors; });
    setError(null);

    try {
        const token = await getToken();
        if (!token) { throw new Error(t('messages_error_authTokenMissing')); }
        
        const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/cancel`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try {
                const errData = await response.json();
                errorDetail = errData.detail || errorDetail;
            } catch (e) {
                const textError = await response.text();
                errorDetail = textError || errorDetail;
            }
            setAssessmentErrors(prev => ({ ...prev, [documentId]: t('messages_cancel_failed', { detail: errorDetail }) }));
            console.error(`Failed to cancel assessment for ${documentId}: ${errorDetail}`);
        } else {
            const resultData = await response.json();
            console.log(`[DocumentsPage] Cancellation successful for ${documentId}:`, resultData);
            setDocuments(prevDocs => prevDocs.map(doc => 
                doc.id === documentId ? { ...doc, status: ERROR_STATUS } : doc
            ));
        }

    } catch (err) {
        const errorMessage = err.message || t('messages_cancel_errorUnknown');
        console.error(`Error cancelling assessment ${documentId}:`, errorMessage);
        setAssessmentErrors(prev => ({ ...prev, [documentId]: errorMessage }));
    } finally {
        setCancellingStatus(prev => {
            const newStatus = { ...prev };
            delete newStatus[documentId];
            return newStatus;
        });
    }
  };

  useEffect(() => {
    if (!isAuthLoading && isAuthenticated) { fetchDocuments(); }
    else if (!isAuthLoading && !isAuthenticated) { setDocuments([]); setError(null); }
  }, [isAuthenticated, isAuthLoading, fetchDocuments]);

  return (
    <div>
      <h1 className="text-3xl font-semibold text-base-content mb-4">{t('documents_heading')}</h1>

      {/* Upload Section */}
      <div className="card bg-base-100 shadow-md border border-base-300 mb-6">
        <div className="card-body">
          <h2 className="card-title text-xl font-medium">{t('documents_upload_heading')}</h2>
          <div className="flex flex-col sm:flex-row items-center space-y-3 sm:space-y-0 sm:space-x-4">
            <input
              id="document-upload-input"
              type="file"
              onChange={handleFileChange}
              className="file-input file-input-bordered file-input-primary w-full max-w-xs"
              accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
            />
            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploadStatus === 'Uploading'}
              className="btn btn-primary shrink-0"
            >
              {uploadStatus === 'Uploading' ? (
                <> <span className="loading loading-spinner loading-xs"></span> {t('common_status_uploading')} </>
              ) : (
                <> <ArrowUpTrayIcon className="h-4 w-4 mr-1" /> {t('common_button_upload')} </>
              )}
            </button>
            <button
              onClick={() => navigate('/bulk-upload')}
              className="btn btn-secondary shrink-0"
            >
              {t('documents_button_bulkUpload', 'Bulk Upload')}
            </button>
          </div>
          {uploadStatus && uploadStatus !== 'Uploading' && (
            <div className={`alert mt-3 ${uploadStatus.startsWith(t('messages_upload_error_prefix')) ? 'alert-error' : 'alert-success'}`}>
              {uploadStatus.startsWith(t('messages_upload_error_prefix')) ? <XCircleIcon className="h-6 w-6"/> : <CheckCircleIcon className="h-6 w-6"/>}
              <span className="text-sm">{uploadStatus}</span>
            </div>
          )}
          <p className="text-xs text-base-content/70 mt-2">{t('documents_upload_note_placeholders')}</p>
        </div>
      </div>

      {/* Document List */}
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <h2 className="card-title text-xl font-medium mb-3">{t('documents_list_heading')}</h2>
          {isLoading && <div className="flex justify-center py-4"><span className="loading loading-lg loading-spinner text-primary"></span><p className="ml-2">{t('documents_list_status_loading')}</p></div>}
          {error && ( <div className="alert alert-error"> <XCircleIcon className="h-6 w-6"/> <span>{t('common_error_prefix')} {error}</span> </div> )}

          {!isLoading && !error && documents.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th className="text-sm font-semibold">{t('common_label_filename')}</th>
                    <th className="text-sm font-semibold">{t('common_label_type')}</th>
                    <th className="text-sm font-semibold">Status</th>
                    <th className="text-sm font-semibold">{t('common_label_uploaded')}</th>
                    <th className="text-sm font-semibold">{t('documents_list_label_aiScore')}</th>
                    <th className="text-sm font-semibold">Characters</th>
                    <th className="text-sm font-semibold">Words</th>
                    <th className="text-sm font-semibold">{t('common_label_actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => {
                    const currentAssessmentStatus = assessmentStatus[doc.id];
                    const currentResultScore = assessmentResults[doc.id];
                    const currentAssessmentError = assessmentErrors[doc.id];
                    const isCancelling = cancellingStatus[doc.id] === 'loading';

                    const canAssess = doc.status === UPLOADED_STATUS || doc.status === ERROR_STATUS;
                    const isActuallyProcessing = doc.status === PROCESSING_STATUS || doc.status === QUEUED_STATUS;
                    const isProcessing = isActuallyProcessing || currentAssessmentStatus === 'loading';
                    const isCompleted = doc.status === COMPLETED_STATUS;
                    const hasFailed = currentAssessmentStatus === 'error' || doc.status === ERROR_STATUS;
                    const hasCancelError = !!currentAssessmentError;

                    let statusBadge;
                    if (isCancelling) { statusBadge = <span className="badge badge-warning badge-outline gap-1 text-xs"><span className="loading loading-spinner loading-xs"></span>Cancelling...</span>; }
                    else if (isProcessing) { statusBadge = <span className="badge badge-info badge-outline gap-1 text-xs"><span className="loading loading-spinner loading-xs"></span>{PROCESSING_STATUS}</span>; }
                    else if (hasCancelError) { statusBadge = <span className="badge badge-error badge-outline text-xs" title={currentAssessmentError}>Cancel Failed</span>; }
                    else if (hasFailed && !isActuallyProcessing) { statusBadge = <span className="badge badge-error badge-outline text-xs" title={currentAssessmentError || 'Document processing failed'}>{ERROR_STATUS}</span>; }
                    else if (isCompleted) { statusBadge = <span className="badge badge-success badge-outline text-xs">{COMPLETED_STATUS}</span>; }
                    else if (doc.status === UPLOADED_STATUS) { statusBadge = <span className="badge badge-ghost text-xs">{UPLOADED_STATUS}</span>; }
                    else { statusBadge = <span className="badge badge-ghost text-xs">{doc.status}</span>; }

                    return (
                      <tr key={doc.id} className="hover">
                        <td className="text-sm truncate max-w-xs" title={doc.original_filename}>{doc.original_filename}</td>
                        <td className="text-sm">{doc.file_type}</td>
                        <td>{statusBadge}</td>
                        <td className="text-xs">{new Date(doc.upload_timestamp).toLocaleString()}</td>
                        <td className="text-sm font-semibold">
                          {isCompleted && typeof currentResultScore === 'number' 
                            ? `${(currentResultScore > 1 ? currentResultScore : currentResultScore * 100).toFixed(1)}%` 
                            : '-'}
                        </td>
                        <td className="text-sm">{doc.character_count?.toLocaleString() ?? '-'}</td>
                        <td className="text-sm">{doc.word_count?.toLocaleString() ?? '-'}</td>
                        <td className="space-x-1 whitespace-nowrap">
                          {canAssess && !isProcessing && !hasFailed && (
                            <button onClick={() => handleAssess(doc.id)} disabled={currentAssessmentStatus === 'loading' || isCancelling} title={t('documents_list_button_assess_title')} className="btn btn-primary btn-xs">
                              {t('documents_list_button_assess')}
                            </button>
                          )}
                          {isProcessing && !isCancelling && (
                             <button disabled title={t('documents_list_button_assessing_title')} className="btn btn-disabled btn-xs">
                               <span className="loading loading-spinner loading-xs"></span> Assessing...
                             </button>
                          )}
                          {isCancelling && (
                             <button disabled title="Cancelling assessment..." className="btn btn-disabled btn-xs">
                                <span className="loading loading-spinner loading-xs"></span> Cancelling...
                             </button>
                          )}
                          {isActuallyProcessing && !isCancelling && (
                             <button 
                                onClick={() => handleCancelAssessment(doc.id)} 
                                title="Cancel this assessment" 
                                className="btn btn-warning btn-outline btn-xs"
                                disabled={isCancelling}
                              >
                               <StopCircleIcon className="h-3 w-3 mr-1"/> Cancel
                             </button>
                          )}
                          {(isCompleted || (hasFailed && !isProcessing)) && !isCancelling && (
                            <button onClick={() => handleAssess(doc.id)} disabled={currentAssessmentStatus === 'loading' || isCancelling} title={hasFailed ? t('documents_list_button_retryAssessment_title') : t('documents_list_button_reassess_title')} className={`btn ${hasFailed ? 'btn-error' : 'btn-warning'} btn-xs`}>
                              <ArrowPathIcon className="h-3 w-3 mr-1"/> {hasFailed ? t('common_button_retry') : t('documents_list_button_reassess')}
                            </button>
                          )}
                          {doc.file_type && supportedTextTypes.includes(doc.file_type.toLowerCase()) && (
                            <button onClick={() => handleViewText(doc.id)} title={t('documents_list_button_viewText_title')} className="btn btn-info btn-outline btn-xs">
                              <DocumentTextIcon className="h-3 w-3 mr-1"/> {t('documents_list_button_viewText')}
                            </button>
                          )}
                          {isCompleted && (
                            <button onClick={() => handleViewReport(doc.id)} title={t('documents_list_button_viewReport_title')} className="btn btn-accent btn-outline btn-xs">
                              <EyeIcon className="h-3 w-3 mr-1"/> {t('documents_list_button_report')}
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteClick(doc.id)}
                            className="btn btn-ghost btn-xs text-error"
                            title={t('common_button_delete')}
                            disabled={deleteLoading && deletingDocId === doc.id}
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {!isLoading && !error && documents.length === 0 && ( <p className="text-base-content/70 text-center py-4">{t('documents_list_status_noDocuments')}</p> )}
        </div>
      </div>

      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-base-100 p-6 rounded-lg shadow-xl max-w-md w-full">
            <h3 className="text-lg font-medium mb-4 text-error">{t('documents_delete_modal_heading', { filename: documents.find(d => d.id === deletingDocId)?.original_filename || '' })}</h3>
            <p className="mb-4">{t('documents_delete_modal_confirm')}</p>
            {deleteError && (
              <div className="alert alert-error mb-2">
                <XCircleIcon className="h-6 w-6" />
                <span>{t('common_error_prefix')} {deleteError}</span>
              </div>
            )}
            {deleteSuccess && (
              <div className="alert alert-success mb-2">
                <CheckCircleIcon className="h-6 w-6" />
                <span>{deleteSuccess}</span>
              </div>
            )}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={handleCancelDelete}
                className="btn btn-ghost btn-sm"
                disabled={deleteLoading}
              >
                {t('common_button_cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="btn btn-error btn-sm"
                disabled={deleteLoading}
              >
                {deleteLoading ? (
                  <><span className="loading loading-spinner loading-xs"></span>{t('common_status_deleting')}</>
                ) : (
                  t('common_button_delete')
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentsPage; 