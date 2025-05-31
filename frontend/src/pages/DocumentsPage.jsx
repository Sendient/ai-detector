import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  UserPlusIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ArrowsUpDownIcon
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
  const LIMIT_EXCEEDED_STATUS = 'LIMIT_EXCEEDED';

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
  const [reprocessingStatus, setReprocessingStatus] = useState({});

  // State for Assign Student Modal
  const [showAssignStudentModal, setShowAssignStudentModal] = useState(false);
  const [assigningDoc, setAssigningDoc] = useState(null);
  const [studentsForAssignmentList, setStudentsForAssignmentList] = useState([]);
  const [isLoadingStudentsForAssignment, setIsLoadingStudentsForAssignment] = useState(false);
  const [selectedStudentIdForAssignment, setSelectedStudentIdForAssignment] = useState('');
  const [searchTermForStudentAssignment, setSearchTermForStudentAssignment] = useState('');
  const [assignStudentModalError, setAssignStudentModalError] = useState(null);
  const [assignStudentModalSuccess, setAssignStudentModalSuccess] = useState(null);
  const [isAssigningStudent, setIsAssigningStudent] = useState(false);
  const [sortField, setSortField] = useState('upload_timestamp');
  const [sortOrder, setSortOrder] = useState('desc');

  const bulkFileInputRef = useRef(null);

  const PROXY_PATH = import.meta.env.VITE_API_PROXY_PATH || '/api/v1';
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''; // Ensure API_BASE_URL is defined if used

  // Polling interval in milliseconds
  const POLLING_INTERVAL = 5000; // 5 seconds

  const fetchResultsForDocuments = useCallback(async (docIds, token) => {
    if (!token || !docIds || docIds.length === 0) return;
    console.log(`[DocumentsPage] Fetching results for docs: ${docIds.join(', ')}`);
    const resultsPromises = docIds.map(docId =>
        fetch(`${PROXY_PATH}/results/document/${docId}`, { headers: { 'Authorization': `Bearer ${token}` } })
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
                    if (data?.status === COMPLETED_STATUS) {
                        newResults[docId] = null;
                        console.log(`[DocumentsPage] Result for doc ${docId} is COMPLETED but score is not a number (is ${data?.score}). Storing null score.`);
                    } else {
                        delete newResults[docId];
                        console.log(`[DocumentsPage] Result for doc ${docId} status is ${data?.status} (not COMPLETED with a numeric score), score not stored/updated.`);
                    }
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

  const fetchDocuments = useCallback(async (isPoll = false) => {
    if (isAuthenticated) {
      if (!isPoll) setIsLoading(true);
      if (!isPoll) setError(null);

      try {
        const token = await getToken();
        if (!token) { throw new Error(t('messages_error_authTokenMissing')); }
        const response = await fetch(`${PROXY_PATH}/documents/`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try { const errData = await response.json(); errorDetail = errData.detail || errorDetail; } catch (e) { /* Ignore */ }
            throw new Error(t('messages_docs_fetchError', { message: errorDetail }));
        }
        const data = await response.json();
        const mappedData = data.map(doc => ({ ...doc, id: doc._id || doc.id })).filter(doc => doc.id);
        console.log('[DocumentsPage] Mapped data before setting state:', mappedData);
        setDocuments(prevDocs => {
          return mappedData;
        });
        
        const completedDocIds = mappedData.filter(doc => doc.status === COMPLETED_STATUS).map(doc => doc.id);
        const currentCompletedIdsInResults = Object.keys(assessmentResults);
        const newCompletedIdsToFetchResults = completedDocIds.filter(id => !currentCompletedIdsInResults.includes(id));

        if (newCompletedIdsToFetchResults.length > 0 && token) {
            await fetchResultsForDocuments(newCompletedIdsToFetchResults, token);
        }
      } catch (err) {
        console.error("Error fetching documents:", err);
        if (!isPoll) setError(err.message || t('messages_error_unexpected'));
      } finally { 
        if (!isPoll) setIsLoading(false); 
      }
    } else {
        setDocuments([]);
        if (!isPoll) setIsLoading(false);
        if (!isAuthLoading && !isPoll) {
            setError(t('messages_error_loginRequired_viewDocs'));
        }
    }
  }, [isAuthenticated, isAuthLoading, getToken, fetchResultsForDocuments, t, COMPLETED_STATUS, assessmentResults]);

  const performUpload = async (fileToUpload, studentId, assignmentId) => {
    if (!isAuthenticated) {
      throw new Error(t('messages_error_loginRequired_upload'));
    }

    const token = await getToken();
    if (!token) {
      throw new Error(t('messages_error_authTokenMissing'));
    }

    const formData = new FormData();
    formData.append('file', fileToUpload);

    if (studentId) {
      formData.append('student_id', studentId);
    }
    if (assignmentId) {
      formData.append('assignment_id', assignmentId);
    }

    const response = await fetch(`${PROXY_PATH}/documents/upload`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });

    if (!response.ok) {
      let errorDetail = `HTTP error ${response.status}`;
      try {
        const errData = await response.json();
        errorDetail = errData.detail || errorDetail;
      } catch (e) {
        try {
            const textError = await response.text();
            errorDetail = textError || errorDetail;
        } catch (textE) {
            // keep original errorDetail
        }
      }
      throw new Error(t('messages_upload_failed_for_file', { fileName: fileToUpload.name, detail: errorDetail }));
    }
    return response.json();
  };

  const handleFileChange = (event) => {
    if (event.target.files && event.target.files[0]) {
      setSelectedFile(event.target.files[0]);
      setUploadStatus(''); 
    }
  };

  const handleSingleUploadClick = async () => {
    if (!selectedFile) {
      setUploadStatus(t('messages_upload_selectFile'));
      return;
    }
    setUploadStatus(t('common_status_uploading_file', {fileName: selectedFile.name}));
    setError(null);

    try {
      const result = await performUpload(selectedFile, null, null);
      console.log('[DocumentsPage] Single upload successful:', result);
      setUploadStatus(t('messages_upload_success', { id: result.id }));
      setSelectedFile(null); 
      const fileInput = document.getElementById('document-upload-input');
      if (fileInput) {
        fileInput.value = ''; 
      }
      setTimeout(() => { fetchDocuments(); setUploadStatus(''); }, 2000); 
    } catch (err) {
      console.error("Error uploading document:", err);
      setUploadStatus(t('messages_upload_error', { message: err.message }));
    }
  };
  
  const triggerBulkFileSelect = () => {
    if (bulkFileInputRef.current) {
      bulkFileInputRef.current.click();
    }
  };

  const handleBulkFilesSelected = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }
  
    let successCount = 0;
    let errorCount = 0;
    const totalFiles = files.length;
  
    for (let i = 0; i < totalFiles; i++) {
      const file = files[i];
      setUploadStatus(t('common_status_uploading_file_count', {fileName: file.name, current: i + 1, total: totalFiles}));
      try {
        const result = await performUpload(file, null, null);
        console.log(`[DocumentsPage] Bulk upload successful for ${file.name}:`, result);
        successCount++;
      } catch (error) {
        console.error(`[DocumentsPage] Bulk upload failed for ${file.name}:`, error.message);
        // Display the error for this specific file, then continue
        setUploadStatus(t('messages_upload_error_for_file', { fileName: file.name, message: error.message }));
        await new Promise(resolve => setTimeout(resolve, 2000)); // Pause to show error
        errorCount++;
      }
    }
  
    if (totalFiles > 0) {
      let summaryMessage = t('messages_bulk_upload_summary_succeeded', {count: successCount});
      if (errorCount > 0) {
        summaryMessage += ` ${t('messages_bulk_upload_summary_failed', {count: errorCount})}`;
      }
      setUploadStatus(summaryMessage);
    } else {
      setUploadStatus(''); 
    }
    
    if (bulkFileInputRef.current) {
      bulkFileInputRef.current.value = '';
    }
    
    setTimeout(() => {
      fetchDocuments();
      // setUploadStatus(''); // Optionally clear summary after a delay
    }, 3000); 
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
        const response = await fetch(`${PROXY_PATH}/documents/${documentId}/assess`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
        
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
            console.warn(`Assessment triggered for ${documentId}, but score missing/invalid in immediate /assess response:`, resultData);
        }
        
        // Refresh the documents list to show the updated status (e.g., PENDING, QUEUED)
        await fetchDocuments();
        
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

  const handleOpenAssignStudentModal = async (doc) => {
    setAssigningDoc(doc);
    setSearchTermForStudentAssignment('');
    setSelectedStudentIdForAssignment(doc.student_id || ''); // Pre-select if already assigned
    setAssignStudentModalError(null);
    setAssignStudentModalSuccess(null);
    await fetchStudentsForModal(); // We'll create this function next
    setShowAssignStudentModal(true);
  };

  const handleCloseAssignStudentModal = () => {
    setShowAssignStudentModal(false);
    setAssigningDoc(null);
    setStudentsForAssignmentList([]);
    setSelectedStudentIdForAssignment('');
    setSearchTermForStudentAssignment('');
    setAssignStudentModalError(null);
    setAssignStudentModalSuccess(null);
  };

  const fetchStudentsForModal = useCallback(async () => {
    if (!isAuthenticated) {
      setAssignStudentModalError(t('messages_error_loginRequired'));
      return;
    }
    setIsLoadingStudentsForAssignment(true);
    setAssignStudentModalError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      // Use API_BASE_URL here if your proxy setup is different for direct calls
      // For consistency, if PROXY_PATH is for /api/v1, then student endpoint would be /api/v1/students
      const response = await fetch(`${PROXY_PATH}/students`, { // REMOVED TRAILING SLASH HERE
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        try { const errData = await response.json(); errorDetail = errData.detail || errorDetail; } catch (e) { /* ignore */ }
        throw new Error(t('messages_students_fetchError', { detail: errorDetail }));
      }
      const data = await response.json();
      const processedStudents = data.map(student => ({ 
        ...student, 
        id: student._id || student.id 
      })).filter(student => student.id);
      setStudentsForAssignmentList(processedStudents);
    } catch (err) {
      console.error("[DocumentsPage] Error fetching students for modal:", err);
      setAssignStudentModalError(err.message || t('messages_error_unexpected'));
      setStudentsForAssignmentList([]);
    } finally {
      setIsLoadingStudentsForAssignment(false);
    }
  }, [getToken, isAuthenticated, t, PROXY_PATH]); // Added PROXY_PATH to dependencies

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
      const response = await fetch(`${PROXY_PATH}/documents/${deletingDocId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!response.ok) {
        let errorDetail = `HTTP error ${response.status}`;
        const textError = await response.text(); // Read as text first
        try {
          const errData = JSON.parse(textError); // Try to parse the text as JSON
          errorDetail = errData.detail || errorDetail;
        } catch (e) {
          // If JSON parsing fails, use the textError if it's not empty, otherwise stick to the HTTP status
          errorDetail = textError || errorDetail;
        }
        throw new Error(t('messages_delete_failed', { detail: errorDetail }));
      }
      // If response.ok, it's a 204 No Content, so no body to read.
      setDeleteSuccess(t('messages_delete_success'));
      await fetchDocuments();
      setTimeout(() => {
        setShowDeleteModal(false);
        setDeletingDocId(null);
        setDeleteSuccess(null);
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
        
        const response = await fetch(`${PROXY_PATH}/documents/${documentId}/cancel-assessment`, {
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

  const handleConfirmAssignStudent = async () => {
    if (!assigningDoc || !selectedStudentIdForAssignment) {
      setAssignStudentModalError(t('messages_error_actionFailed', { action: 'Assign Student', detail: 'Document or student not selected.'}));
      return;
    }

    setIsAssigningStudent(true);
    setAssignStudentModalError(null);
    setAssignStudentModalSuccess(null);

    console.log(`[DocumentsPage] Attempting to assign student ${selectedStudentIdForAssignment} to doc ${assigningDoc.id}`);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${PROXY_PATH}/documents/${assigningDoc.id}/assign-student`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ student_id: selectedStudentIdForAssignment }),
        }
      );

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        try { 
          const errData = await response.json(); 
          errorDetail = errData.detail || errorDetail; 
        } catch (e) { 
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        throw new Error(t('messages_assignStudent_failed', { detail: errorDetail }));
      }

      const updatedDocument = await response.json();
      
      setDocuments(prevDocs => 
        prevDocs.map(doc => 
          doc.id === updatedDocument.id 
            ? { 
                ...doc, // Spread existing doc properties
                student_id: updatedDocument.student_id, // Update student_id from response
                student_details: studentsForAssignmentList.find(s => s.id === selectedStudentIdForAssignment) // Correctly set student_details
              }
            : doc
        )
      );
      // Fetch the student name for the success message, as updatedDocument might not contain it directly
      const studentName = studentsForAssignmentList.find(s => s.id === selectedStudentIdForAssignment)?.first_name || 'Student';
      setAssignStudentModalSuccess(t('messages_assignStudent_success', { studentName: studentName, filename: assigningDoc.original_filename }));
      
      fetchDocuments(); // ADDED: Refresh documents list

      setTimeout(() => {
        handleCloseAssignStudentModal();
      }, 1500);

    } catch (error) {
      console.error("[DocumentsPage] Error assigning student:", error);
      setAssignStudentModalError(error.message || t('messages_assignStudent_failed_default'));
    } finally {
      setIsAssigningStudent(false);
    }
  };

  const getSimplifiedFileType = (mimeType, originalFilename) => {
    if (!mimeType && originalFilename) {
        const ext = originalFilename.split('.').pop().toLowerCase();
        if (ext === 'pdf') return 'PDF';
        if (ext === 'docx') return 'Word';
        if (ext === 'txt') return 'Text';
        if (['png', 'jpg', 'jpeg'].includes(ext)) return 'Image';
    }
    if (mimeType === 'application/pdf') return 'PDF';
    if (mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return 'Word';
    if (mimeType === 'text/plain') return 'Text';
    if (mimeType === 'image/png' || mimeType === 'image/jpeg') return 'Image';
    return mimeType || 'Unknown'; // Fallback to full mime type or 'Unknown'
  };

  const handleReprocessDocument = async (documentId) => {
    if (!isAuthenticated) {
      setError(t('messages_error_loginRequired_general'));
      return;
    }

    const confirmed = window.confirm(t('documentsPage_confirmReprocess'));
    if (!confirmed) {
      return;
    }

    setReprocessingStatus(prev => ({ ...prev, [documentId]: t('documentsPage_status_reprocessing') }));
    setError(null);
    let token;

    try {
      token = await getToken();
      if (!token) {
        throw new Error(t('messages_error_authTokenMissing'));
      }

      const response = await fetch(`${PROXY_PATH}/documents/${documentId}/reprocess`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        try {
          const errData = await response.json();
          errorDetail = errData.detail || errorDetail;
        } catch (e) {
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        throw new Error(t('documentsPage_reprocessFailedError', { detail: errorDetail }));
      }

      // Assuming 202 Accepted means success
      setReprocessingStatus(prev => ({ ...prev, [documentId]: t('documentsPage_status_reprocess_success') }));
      // Optimistically update document status in UI or wait for poll
      setDocuments(prevDocs => 
        prevDocs.map(doc => 
          doc.id === documentId ? { ...doc, status: QUEUED_STATUS } : doc
        )
      );
      setTimeout(() => {
        setReprocessingStatus(prev => ({ ...prev, [documentId]: null }));
        fetchDocuments(true); // Poll to get updated status
      }, 3000);

    } catch (err) {
      console.error(`Error reprocessing document ${documentId}:`, err);
      setError(err.message || t('messages_error_unexpected'));
      setReprocessingStatus(prev => ({ ...prev, [documentId]: t('documentsPage_status_reprocess_failed') }));
       setTimeout(() => {
        setReprocessingStatus(prev => ({ ...prev, [documentId]: null }));
      }, 5000);
    }
  };

  const renderDocumentActions = (doc) => {
    const isProcessing = assessmentStatus[doc.id] === 'loading';
    const isCancelling = cancellingStatus[doc.id] === 'loading';
    const isTextExtractable = doc.file_type && supportedTextTypes.includes(doc.file_type.toLowerCase());

    let statusActions = null;

    switch (doc.status) {
      case COMPLETED_STATUS:
        statusActions = (
          <button
            onClick={() => handleViewReport(doc.id)}
            className="btn btn-xs btn-primary btn-outline"
            title={t('documents_list_button_viewReport_title')}
          >
            <EyeIcon className="h-4 w-4" />
            {t('documents_list_button_report')}
          </button>
        );
        break;
      case ERROR_STATUS:
      case LIMIT_EXCEEDED_STATUS:
        statusActions = (
          <button
            onClick={() => handleAssess(doc.id)}
            className="btn btn-xs btn-warning btn-outline"
            disabled={isProcessing}
            title={doc.status === LIMIT_EXCEEDED_STATUS ? t('documents_list_button_retryAssessment_title') : t('documentsPage_tooltip_retryOnError')}
          >
            {isProcessing ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              <ArrowPathIcon className="h-4 w-4" />
            )}
            {doc.status === LIMIT_EXCEEDED_STATUS ? t('common_button_retry') : t('documentsPage_button_retryOnError')}
          </button>
        );
        break;
      case UPLOADED_STATUS:
      case QUEUED_STATUS: 
        statusActions = (
          <button
            onClick={() => handleAssess(doc.id)}
            className="btn btn-xs btn-info btn-outline"
            disabled={isProcessing}
            title={t('documents_list_button_assess_title')}
          >
            {isProcessing ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              <ArrowPathIcon className="h-4 w-4" />
            )}
            {t('documents_list_button_assess')}
          </button>
        );
        break;
      case PROCESSING_STATUS:
        statusActions = (
          <div className="flex items-center space-x-2">
            <span className="loading loading-spinner loading-xs text-info"></span>
            <span className="text-xs text-info italic">{t('documentsPage_text_processing')}</span>
            <button
                onClick={() => handleCancelAssessment(doc.id)}
                className="btn btn-xs btn-error btn-outline"
                disabled={isCancelling}
                title={t('documentsPage_tooltip_cancelAssessment')}
            >
                {isCancelling ? <span className="loading loading-spinner loading-xs"></span> : <StopCircleIcon className="h-4 w-4" />}
                {t('common_button_cancel')}
            </button>
          </div>
        );
        break;
      default:
        statusActions = <span className="text-xs italic text-gray-500">{t('documentsPage_status_unknown', { status: doc.status })}</span>;
    }

    return (
      <div className="flex items-center space-x-2">
        {statusActions}
        {doc.status !== PROCESSING_STATUS && (
            <button
                onClick={() => handleDeleteClick(doc.id)}
                className="btn btn-xs btn-error btn-outline"
                title={t('documentsPage_tooltip_deleteDocument')}
            >
                <TrashIcon className="h-4 w-4" />
            </button>
        )}
        {isTextExtractable && doc.status !== PROCESSING_STATUS && (
            <button
                onClick={() => handleViewText(doc.id)}
                className="btn btn-xs btn-ghost"
                title={t('documents_list_button_viewText_title')}
            >
                <DocumentTextIcon className="h-4 w-4" />
            </button>
        )}
        <button
          onClick={() => handleReprocessDocument(doc.id)}
          title={t('documentsPage_action_reprocess')}
          className="p-2 text-gray-600 hover:text-blue-600 transition-colors disabled:opacity-50"
          disabled={reprocessingStatus[doc.id] || isProcessing}
        >
          <ArrowPathIcon className="h-5 w-5" />
        </button>
      </div>
    );
  };

  // Effect for initial document load
  useEffect(() => {
    if (isAuthenticated && !isAuthLoading) {
      fetchDocuments();
    } else if (!isAuthenticated && !isAuthLoading) {
      setDocuments([]);
      setIsLoading(false);
      setError(t('messages_error_loginRequired_viewDocs'));
    }
  }, [isAuthenticated, isAuthLoading, fetchDocuments, t]);

  // Effect for polling
  useEffect(() => {
    if (!isAuthenticated) return;

    const activePollingDocs = () => documents.filter(doc => 
      doc.status === PROCESSING_STATUS || doc.status === QUEUED_STATUS
    ).map(doc => doc.id);

    let intervalId;

    if (activePollingDocs().length > 0) {
      intervalId = setInterval(() => {
        console.log('[DocumentsPage] Polling for active documents...');
        fetchDocuments(true); // Pass true for isPoll
      }, POLLING_INTERVAL);
    } else {
      console.log('[DocumentsPage] No active documents to poll.');
    }
    
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
        console.log('[DocumentsPage] Polling interval cleared.');
      }
    };
  }, [documents, isAuthenticated, fetchDocuments]);

  // --- Sorting Logic ---
  const handleSort = (field) => {
    const newSortOrder = sortField === field && sortOrder === 'asc' ? 'desc' : 'asc';
    setSortField(field);
    setSortOrder(newSortOrder);
  };

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
              onClick={handleSingleUploadClick}
              disabled={!selectedFile || uploadStatus.includes(t('common_status_uploading'))}
              className="btn btn-primary shrink-0"
            >
              {uploadStatus.includes(t('common_status_uploading')) && !uploadStatus.includes(t('messages_bulk_upload_summary_prefix')) ? (
                <> <span className="loading loading-spinner loading-xs"></span> {t('common_status_uploading')} </>
              ) : (
                <> <ArrowUpTrayIcon className="h-4 w-4 mr-1" /> {t('common_button_upload')} </>
              )}
            </button>
            <button
              onClick={triggerBulkFileSelect}
              className="btn btn-accent shrink-0 ml-2"
              disabled={uploadStatus.includes(t('common_status_uploading'))}
            >
              <ArrowUpTrayIcon className="h-4 w-4 mr-1" /> {t('documents_button_bulkUpload_alt', 'Bulk Upload Files')}
            </button>
          </div>
          <input 
            type="file" 
            multiple 
            ref={bulkFileInputRef} 
            onChange={handleBulkFilesSelected} 
            style={{ display: 'none' }} 
            accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
          />
          {uploadStatus && (
            <div className={`alert mt-3 ${uploadStatus.startsWith(t('messages_upload_error_prefix')) ? 'alert-error' : 'alert-success'}`}>
              {uploadStatus.startsWith(t('messages_upload_error_prefix')) ? <XCircleIcon className="h-6 w-6"/> : <CheckCircleIcon className="h-6 w-6"/>}
              <span className="text-sm">{uploadStatus}</span>
            </div>
          )}
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
                    <th className="text-sm font-semibold">
                      <button onClick={() => handleSort('original_filename')} className="btn btn-ghost btn-xs p-0 hover:bg-transparent normal-case font-semibold flex items-center">
                        {t('documents_list_header_filename')}
                        <span className="ml-2">
                          {sortField === 'original_filename' ? 
                            (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />) : 
                            <ArrowsUpDownIcon className="h-4 w-4 text-gray-400" />}
                        </span>
                      </button>
                    </th>
                    <th className="text-sm font-semibold">
                      <button onClick={() => handleSort('upload_timestamp')} className="btn btn-ghost btn-xs p-0 hover:bg-transparent normal-case font-semibold flex items-center">
                        {t('common_label_uploaded')}
                        <span className="ml-2">
                          {sortField === 'upload_timestamp' ? 
                            (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />) : 
                            <ArrowsUpDownIcon className="h-4 w-4 text-gray-400" />}
                        </span>
                      </button>
                    </th>
                    <th className="text-sm font-semibold">{t('documents_list_header_status')}</th>
                    <th className="text-sm font-semibold">{t('common_label_actions')}</th>
                    <th className="text-sm font-semibold">{t('documents_list_header_assignedStudent')}</th>
                    <th className="text-sm font-semibold">{t('documents_list_label_aiScore')}</th>
                    <th className="text-sm font-semibold">Words</th>
                    <th className="text-sm font-semibold">Characters</th>
                    <th className="text-sm font-semibold">{t('documents_list_header_type')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.sort((a, b) => {
                    if (!sortField) return 0;
                    let valA = a[sortField];
                    let valB = b[sortField];
                    if (sortField === 'upload_timestamp') {
                      valA = new Date(a.upload_timestamp || a.created_at);
                      valB = new Date(b.upload_timestamp || b.created_at);
                    }
                    if (valA < valB) return sortOrder === 'asc' ? -1 : 1;
                    if (valA > valB) return sortOrder === 'asc' ? 1 : -1;
                    return 0;
                  }).map((doc) => {
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
                    const isLimitExceeded = doc.status === LIMIT_EXCEEDED_STATUS;

                    if (isLimitExceeded) { // Diagnostic log
                        console.log(`[DocumentsPage] Rendering LIMIT_EXCEEDED status for doc ${doc.id}. Key: 'documents_list_status_limitExceeded', Translated: '${t('documents_list_status_limitExceeded')}'`);
                    }

                    let statusBadge;
                    if (isCancelling) { statusBadge = <span className="badge badge-warning badge-outline gap-1 text-xs"><span className="loading loading-spinner loading-xs"></span>Cancelling...</span>; }
                    else if (isProcessing) { statusBadge = <span className="badge badge-info badge-outline gap-1 text-xs"><span className="loading loading-spinner loading-xs"></span>{PROCESSING_STATUS}</span>; }
                    else if (hasCancelError) { statusBadge = <span className="badge badge-error badge-outline text-xs" title={currentAssessmentError}>Cancel Failed</span>; }
                    else if (isLimitExceeded) { statusBadge = <span className="badge badge-warning badge-outline text-xs">{t('documents_list_status_limitExceeded')}</span>; }
                    else if (hasFailed && !isActuallyProcessing) { statusBadge = <span className="badge badge-error badge-outline text-xs" title={currentAssessmentError || 'Document processing failed'}>{ERROR_STATUS}</span>; }
                    else if (isCompleted) { statusBadge = <span className="badge badge-success badge-outline text-xs">{COMPLETED_STATUS}</span>; }
                    else if (doc.status === UPLOADED_STATUS) { statusBadge = <span className="badge badge-ghost text-xs">{UPLOADED_STATUS}</span>; }
                    else { statusBadge = <span className="badge badge-ghost text-xs">{doc.status}</span>; }

                    return (
                      <tr key={doc.id} className="hover">
                        <td className="text-sm truncate max-w-xs" title={doc.original_filename}>{doc.original_filename}</td>
                        <td>{new Date(doc.upload_timestamp).toLocaleString()}</td>
                        <td>
                          {statusBadge}
                          {assessmentErrors[doc.id] && (
                              <div className="text-xs text-error mt-1">
                                  {assessmentErrors[doc.id]}
                              </div>
                          )}
                        </td>
                        <td className="space-x-1 whitespace-nowrap">
                          <button
                            onClick={() => handleReprocessDocument(doc.id)}
                            title={t('documentsPage_action_reprocess')}
                            className="btn btn-ghost btn-xs p-1"
                            disabled={reprocessingStatus[doc.id] || (assessmentStatus[doc.id] === 'loading' || doc.status === PROCESSING_STATUS || doc.status === QUEUED_STATUS)}
                          >
                            <ArrowPathIcon className="h-5 w-5 text-gray-600 hover:text-blue-600" />
                          </button>
                          <button
                            onClick={() => handleViewReport(doc.id)}
                            className="btn btn-ghost btn-xs p-1"
                            title={t('documents_list_button_viewReport_title')}
                          >
                            <EyeIcon className="h-5 w-5 text-blue-600 hover:text-blue-800" />
                          </button>
                          <button
                            onClick={() => handleOpenAssignStudentModal(doc)}
                            className="btn btn-ghost btn-xs p-1"
                            title={t('documents_list_button_assignStudent_title')}
                          >
                            <UserPlusIcon className="h-5 w-5 text-gray-600 hover:text-gray-800" />
                          </button>
                          <button
                            onClick={() => handleDeleteClick(doc.id)}
                            className="btn btn-ghost btn-xs p-1"
                            title={t('documentsPage_tooltip_deleteDocument')}
                          >
                            <TrashIcon className="h-5 w-5 text-red-500 hover:text-red-700" />
                          </button>
                        </td>
                        <td className="text-sm">
                          {doc.student_details 
                            ? `${doc.student_details.first_name} ${doc.student_details.last_name}` 
                            : '-'}
                        </td>
                        <td className="text-sm font-semibold">
                          {isCompleted && typeof currentResultScore === 'number' 
                            ? `${(currentResultScore > 1 ? currentResultScore : currentResultScore * 100).toFixed(1)}%` 
                            : '-'}
                        </td>
                        <td className="text-sm">{doc.word_count?.toLocaleString() ?? '-'}</td>
                        <td className="text-sm">{doc.character_count?.toLocaleString() ?? '-'}</td>
                        <td className="text-sm">{getSimplifiedFileType(doc.file_type, doc.original_filename)}</td>
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

      {/* Assign Student Modal */}
      {showAssignStudentModal && assigningDoc && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
          <div className="bg-base-100 p-6 rounded-lg shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
            <h3 className="text-xl font-semibold mb-4 text-base-content">
              {t('documents_assignModal_heading', { filename: assigningDoc.original_filename })}
            </h3>
            
            {assignStudentModalError && (
              <div className="alert alert-error mb-4">
                <XCircleIcon className="h-6 w-6" />
                <span>{assignStudentModalError}</span>
              </div>
            )}
            {assignStudentModalSuccess && (
              <div className="alert alert-success mb-4">
                <CheckCircleIcon className="h-6 w-6" />
                <span>{assignStudentModalSuccess}</span>
              </div>
            )}

            <div className="mb-4">
              <input 
                type="text"
                placeholder={t('documents_assignModal_searchPlaceholder', "Search students by name or email...")}
                value={searchTermForStudentAssignment}
                onChange={(e) => setSearchTermForStudentAssignment(e.target.value)}
                className="input input-bordered w-full input-sm"
              />
            </div>

            <div className="overflow-y-auto flex-grow mb-4 border border-base-300 rounded-md min-h-[200px]">
              {isLoadingStudentsForAssignment ? (
                <div className="flex justify-center items-center h-full">
                  <span className="loading loading-spinner loading-md"></span>
                </div>
              ) : studentsForAssignmentList.length === 0 ? (
                <p className="text-center p-4 text-base-content/70">
                  {t('documents_assignModal_noStudents', 'No students found.')}
                </p>
              ) : (
                <ul className="divide-y divide-base-200">
                  {studentsForAssignmentList
                    .filter(student => 
                      `${student.first_name} ${student.last_name} ${student.email || ''}`
                        .toLowerCase()
                        .includes(searchTermForStudentAssignment.toLowerCase())
                    )
                    .map(student => (
                      <li key={student.id} 
                          className={`p-3 hover:bg-base-200 cursor-pointer ${selectedStudentIdForAssignment === student.id ? 'bg-primary text-primary-content' : ''}`}
                          onClick={() => setSelectedStudentIdForAssignment(student.id)}
                      >
                        <div className="font-medium">{student.first_name} {student.last_name}</div>
                        <div className="text-xs opacity-70">{student.email || t('common_text_notApplicable')}</div>
                      </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex justify-end space-x-3 pt-4 border-t border-base-300">
              <button
                type="button"
                onClick={handleCloseAssignStudentModal}
                className="btn btn-ghost btn-sm"
                disabled={isAssigningStudent}
              >
                {t('common_button_cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmAssignStudent}
                className="btn btn-primary btn-sm"
                disabled={!selectedStudentIdForAssignment || isAssigningStudent}
              >
                {isAssigningStudent ? <span className="loading loading-spinner loading-xs"></span> : null}
                {t('documents_assignModal_button_assign', 'Assign Student')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentsPage; 