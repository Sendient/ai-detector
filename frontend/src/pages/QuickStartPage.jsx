import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { ArrowUpTrayIcon, XMarkIcon, DocumentIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline';

function QuickStartPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { getToken, isAuthenticated } = useKindeAuth();
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [batchId, setBatchId] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);

  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles(prevFiles => [...prevFiles, ...droppedFiles]);
  }, []);

  const handleFileInput = useCallback((e) => {
    const selectedFiles = Array.from(e.target.files);
    setFiles(prevFiles => [...prevFiles, ...selectedFiles]);
  }, []);

  const removeFile = useCallback((indexToRemove) => {
    setFiles(prevFiles => prevFiles.filter((_, index) => index !== indexToRemove));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!isAuthenticated) {
      setUploadStatus(t('messages_error_loginRequired_upload'));
      return;
    }

    if (files.length === 0) {
      setUploadStatus(t('messages_upload_selectFile'));
      return;
    }

    setIsUploading(true);
    setUploadStatus(t('common_status_uploading'));
    setUploadProgress(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error(t('messages_error_authTokenMissing'));
      }

      // Placeholder UUIDs
      const placeholderStudentId = '00000000-0000-0000-0000-000000000001';
      const placeholderAssignmentId = '00000000-0000-0000-0000-000000000002';

      // Actual IDs to be sent - use empty string if they are placeholders, otherwise use the actual ID.
      // This assumes that in the future, studentId and assignmentId might come from state/props.
      let studentIdToSend = ''; // Default to empty string for 'unassigned'
      let assignmentIdToSend = ''; // Default to empty string for 'unassigned'

      // Example: If you had actual state for these, you might do:
      // const actualStudentIdFromState = someStateValueForStudentId;
      // const actualAssignmentIdFromState = someStateValueForAssignmentId;
      // studentIdToSend = actualStudentIdFromState && actualStudentIdFromState !== placeholderStudentId ? actualStudentIdFromState : '';
      // assignmentIdToSend = actualAssignmentIdFromState && actualAssignmentIdFromState !== placeholderAssignmentId ? actualAssignmentIdFromState : '';
      
      // For now, since they are always placeholders, they will become empty strings.
      // This part is more for future-proofing if dynamic IDs are introduced.
      const currentStudentId = '00000000-0000-0000-0000-000000000001'; // Simulating current value
      const currentAssignmentId = '00000000-0000-0000-0000-000000000002'; // Simulating current value

      if (currentStudentId !== placeholderStudentId) {
        studentIdToSend = currentStudentId;
      }
      if (currentAssignmentId !== placeholderAssignmentId) {
        assignmentIdToSend = currentAssignmentId;
      }

      console.log('Using IDs to send:', {
        student_id: studentIdToSend,
        assignment_id: assignmentIdToSend
      });

      const formData = new FormData();
      // Only append if they are not empty, letting backend handle None/null if not present
      if (studentIdToSend) {
        formData.append('student_id', studentIdToSend);
      }
      if (assignmentIdToSend) {
        formData.append('assignment_id', assignmentIdToSend);
      }
      
      // Log the files being uploaded
      console.log('Files being uploaded:', files.map(f => ({ name: f.name, size: f.size, type: f.type })));
      
      // Append each file to the formData
      files.forEach((file, index) => {
        console.log(`Adding file ${index + 1}/${files.length}:`, file.name);
        formData.append('files', file);
      });

      // Log the FormData contents for debugging
      console.log('FormData contents:');
      for (let [key, value] of formData.entries()) {
        if (value instanceof File) {
          console.log(`${key}: File(name=${value.name}, type=${value.type}, size=${value.size})`);
        } else {
          console.log(`${key}: ${value}`);
        }
      }

      // Set default priority
      formData.append('priority', 'NORMAL');
      
      console.log('Making API request to /api/v1/documents/batch');
      const response = await fetch('/api/v1/documents/batch', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      console.log('Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        let errorDetail = `HTTP error ${response.status}`;
        try {
          // For 500 errors, try to get text first
          if (response.status === 500) {
            const textResponse = await response.text();
            console.error('Server error response:', textResponse);
            errorDetail = 'Server error: Please try again later or contact support if the issue persists.';
            throw new Error(errorDetail);
          }

          const errData = await response.json();
          console.error('Error response data:', errData);
          console.error('Error response structure:', {
            type: typeof errData,
            hasDetail: 'detail' in errData,
            detailType: errData.detail ? typeof errData.detail : 'undefined',
            isDetailArray: Array.isArray(errData.detail),
            keys: Object.keys(errData),
            fullError: JSON.stringify(errData, null, 2)
          });
          
          // Handle array of error details
          if (errData.detail) {
            if (Array.isArray(errData.detail)) {
              errorDetail = errData.detail.map(err => 
                typeof err === 'object' ? JSON.stringify(err) : err
              ).join(', ');
            } else if (typeof errData.detail === 'object') {
              errorDetail = JSON.stringify(errData.detail);
            } else {
              errorDetail = errData.detail;
            }
          } else if (errData.message) {
            errorDetail = errData.message;
          } else {
            errorDetail = JSON.stringify(errData);
          }
          
        } catch (e) {
          console.error('Error parsing error response:', e);
          if (response.status === 500) {
            errorDetail = 'Server error: Please try again later or contact support if the issue persists.';
          } else {
            errorDetail = response.statusText || errorDetail;
          }
        }
        throw new Error(errorDetail);
      }

      const result = await response.json();
      console.log('Success response:', result);
      
      setBatchId(result.batch_id);
      setUploadStatus(t('messages_upload_success', { id: result.batch_id }));
      setUploadProgress({
        total_files: result.total_files,
        status: result.status,
        document_ids: result.document_ids
      });

      // Clear the file input and list after successful upload
      setFiles([]);
      const fileInput = document.getElementById('file-upload');
      if (fileInput) {
        fileInput.value = '';
      }

      // Navigate to documents page after a short delay
      setTimeout(() => {
        navigate('/documents');
      }, 2000);

    } catch (err) {
      console.error("Error uploading batch:", err);
      console.error("Error details:", {
        message: err.message,
        stack: err.stack,
        name: err.name
      });
      
      // Format the error message for display
      let errorMessage;
      try {
        errorMessage = err.message && err.message !== '[object Object]'
          ? err.message
          : typeof err === 'object' 
            ? JSON.stringify(err)
            : 'An error occurred while uploading files. Please try again.';
      } catch (e) {
        errorMessage = 'An error occurred while uploading files. Please try again.';
      }
      
      setUploadStatus(`Upload failed: ${errorMessage}`);
      setUploadProgress(null);
    } finally {
      setIsUploading(false);
    }
  }, [files, isAuthenticated, getToken, navigate, t]);

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <h1 className="text-3xl font-semibold mb-8">{t('quickstart_title', 'Quick Start Assessment')}</h1>
      
      {/* Upload Area */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center ${
          isDragging ? 'border-primary bg-primary/5' : 'border-base-300'
        } transition-colors duration-200`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <ArrowUpTrayIcon className="mx-auto h-12 w-12 text-base-content/50 mb-4" />
        <h2 className="text-xl font-medium mb-2">
          {t('quickstart_drop_title', 'Drop your files here')}
        </h2>
        <p className="text-base-content/70 mb-4">
          {t('quickstart_drop_subtitle', 'or click to select files')}
        </p>
        <input
          type="file"
          multiple
          className="hidden"
          id="file-upload"
          onChange={handleFileInput}
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
        />
        <label
          htmlFor="file-upload"
          className="btn btn-primary"
        >
          {t('quickstart_select_files', 'Select Files')}
        </label>
      </div>

      {/* Selected Files List */}
      {files.length > 0 && (
        <div className="mt-8">
          <h3 className="text-lg font-medium mb-4">
            {t('quickstart_selected_files', 'Selected Files')} ({files.length})
          </h3>
          <div className="space-y-2">
            {files.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center justify-between p-3 bg-base-200 rounded-lg"
              >
                <div className="flex items-center space-x-3">
                  <DocumentIcon className="h-5 w-5 text-primary" />
                  <span className="text-sm">{file.name}</span>
                  <span className="text-xs text-base-content/50">
                    ({(file.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                </div>
                <button
                  onClick={() => removeFile(index)}
                  className="btn btn-ghost btn-sm btn-circle"
                  title={t('quickstart_remove_file', 'Remove file')}
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload Status */}
      {uploadStatus && (
        <div className={`alert mt-4 ${uploadStatus.includes('Error') ? 'alert-error' : 'alert-success'}`}>
          <div className="flex items-center">
            {uploadStatus.includes('Error') ? (
              <XCircleIcon className="h-6 w-6 mr-2" />
            ) : (
              <CheckCircleIcon className="h-6 w-6 mr-2" />
            )}
            <span>{uploadStatus}</span>
          </div>
          {uploadProgress && (
            <div className="text-sm mt-2">
              <p>Batch ID: {batchId}</p>
              <p>Total Files: {uploadProgress.total_files}</p>
              <p>Status: {uploadProgress.status}</p>
            </div>
          )}
        </div>
      )}

      {/* Submit Button */}
      {files.length > 0 && (
        <div className="mt-8 flex justify-end">
          <button
            onClick={handleSubmit}
            className="btn btn-primary"
            disabled={isUploading || files.length === 0}
          >
            {isUploading ? (
              <>
                <span className="loading loading-spinner loading-xs mr-2"></span>
                {t('common_status_uploading')}
              </>
            ) : (
              <>
                <ArrowUpTrayIcon className="h-5 w-5 mr-2" />
                {t('quickstart_submit', 'Submit for Assessment')}
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

export default QuickStartPage; 