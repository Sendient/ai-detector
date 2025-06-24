import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpTrayIcon, ArrowDownTrayIcon, XCircleIcon } from '@heroicons/react/24/outline';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useNavigate } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function BulkUploadPage() {
  const { t } = useTranslation();
  const { getToken, isAuthenticated } = useKindeAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [parsedData, setParsedData] = useState([]);
  const [uploadError, setUploadError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadResults, setUploadResults] = useState([]);
  const [uploadSummary, setUploadSummary] = useState(null);

  const handleBulkUpload = () => {
    setSelectedFile(null);
    setParsedData([]);
    setUploadResults([]);
    setUploadSummary(null);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = null;
      fileInputRef.current.click();
    }
  };

  const handleFileSelected = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (file.type !== 'text/csv' && !file.name.toLowerCase().endsWith('.csv')) {
      setUploadError(t('bulkUpload_error_notCsv', 'Please select a valid CSV file.'));
      setSelectedFile(null);
      setUploadResults([]);
      setUploadSummary(null);
      return;
    }

    setSelectedFile(file);
    setUploadError(null);
    setUploadResults([]);
    setUploadSummary(null);
    setIsProcessing(true);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const csvText = e.target.result;
        parseCSVDataAndSubmit(csvText);
      } catch (error) {
        console.error("Error parsing CSV or initiating submission:", error);
        setUploadError(t('bulkUpload_error_parsing', 'Error parsing CSV file. Please check the format.'));
        setIsProcessing(false);
      }
    };
    reader.onerror = () => {
      console.error("Error reading file:", reader.error);
      setUploadError(t('bulkUpload_error_reading', 'Error reading file.'));
      setIsProcessing(false);
    };
    reader.readAsText(file);
  };

  const parseCSVDataAndSubmit = (csvText) => {
    const lines = csvText.trim().split(/\r\n|\r|\n/);
    if (lines.length < 2) {
      setUploadError(t('bulkUpload_error_emptyCsv', 'CSV file is empty or has no data rows.'));
      setIsProcessing(false);
      return;
    }

    const headerLine = lines[0].trim();
    const headers = headerLine.split(',').map(header => header.trim());
    const expectedHeaders = [
      "Firstname",
      "Lastname",
      "Email Address",
      "External ID",
      "Descriptor",
      "Assign to Class"
    ];

    if (headers.length !== expectedHeaders.length ||
        !expectedHeaders.every((eh, i) => headers[i] === eh)) {
      setUploadError(t('bulkUpload_error_mismatchedHeaders', 'CSV headers do not match the expected template. Please download the template and try again.'));
      setIsProcessing(false);
      return;
    }

    const studentDataPayload = [];
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const values = line.split(',').map(value => value.trim());
      if (values.length === headers.length) {
        studentDataPayload.push({
          FirstName: values[0],
          LastName: values[1],
          EmailAddress: values[2] || null,
          ExternalID: values[3] || null,
          Descriptor: values[4] || null,
          AssignToClass: values[5] || null,
        });
      } else {
        console.warn(`Skipping row ${i + 1}: Mismatched number of columns.`);
      }
    }

    if (studentDataPayload.length === 0) {
      setUploadError(t('bulkUpload_error_noValidRows', 'No valid data rows found after parsing.'));
      setIsProcessing(false);
      return;
    }

    console.log("Formatted data to send:", studentDataPayload);
    submitBulkData(studentDataPayload);
  };

  const submitBulkData = async (students) => {
    if (!isAuthenticated) {
      setUploadError(t('messages_error_loginRequired', 'Please log in to upload students.'));
      setIsProcessing(false);
      return;
    }
    setIsProcessing(true);
    setUploadError(null);
    setUploadResults([]);
    setUploadSummary(null);

    try {
      const token = await getToken();
      if (!token) {
        setUploadError(t('messages_error_authTokenMissing', 'Authentication token is missing.'));
        setIsProcessing(false);
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/students/bulk-upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ students }),
      });

      const responseData = await response.json();

      if (!response.ok) {
        const errorMsg = responseData.detail || t('bulkUpload_error_apiError', 'An API error occurred.');
        throw new Error(errorMsg);
      }

      setUploadResults(responseData.results || []);
      setUploadSummary(responseData.summary || null);
      if ((responseData.results || []).length === 0) {
        setUploadError(t('bulkUpload_error_noResultsFromApi', 'The API returned no results. Check server logs.'));
      }

    } catch (error) {
      console.error("Bulk upload API error:", error);
      setUploadError(error.message || t('bulkUpload_error_unexpected', 'An unexpected error occurred during upload.'));
      setUploadResults([]);
      setUploadSummary(null);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadTemplate = () => {
    console.log("Download Template button clicked");
    const headers = [
      "Firstname",
      "Lastname",
      "Email Address",
      "External ID",
      "Descriptor",
      "Assign to Class"
    ];
    const csvContent = "data:text/csv;charset=utf-8," + headers.join(",") + "\n";
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "student_bulk_upload_template.csv");
    document.body.appendChild(link); // Required for Firefox
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-semibold text-base-content mb-6">
        {t('bulkUpload_heading', 'Bulk Student Upload')}
      </h1>

      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body items-center">
          <p className="text-base-content/80 mb-6 text-center max-w-md">
            {t('bulkUpload_description', 'Upload multiple students at once using a CSV template, or download the template to get started.')}
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4">
            <button 
              onClick={handleBulkUpload}
              className="btn btn-primary btn-lg"
              disabled={isProcessing}
            >
              {isProcessing ? (
                <>
                  <span className="loading loading-spinner loading-xs"></span>
                  {t('bulkUpload_status_processing', 'Processing...')}
                </>
              ) : (
                <>
              <ArrowUpTrayIcon className="h-5 w-5 mr-2" />
                  {t('bulkUpload_button_upload', 'Bulk Upload Students')}
                </>
              )}
            </button>
            
            <button 
              onClick={handleDownloadTemplate}
              className="btn btn-secondary btn-lg"
            >
              <ArrowDownTrayIcon className="h-5 w-5 mr-2" />
              {t('bulkUpload_button_downloadTemplate', 'Download Template')}
            </button>
          </div>

          <input 
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelected}
            accept=".csv"
            style={{ display: 'none' }}
          />

          {selectedFile && !isProcessing && (
            <div className="mt-4 text-sm text-base-content/80">
              {t('bulkUpload_status_selectedFile', 'Selected file:')}
              {selectedFile.name}
            </div>
          )}
          {uploadError && (
            <div className="mt-4 alert alert-error text-sm">
              <XCircleIcon className="h-5 w-5 mr-2 shrink-0"/> 
              <span>{uploadError}</span>
            </div>
          )}

          {uploadSummary && !isProcessing && (
            <div className="mt-6 p-4 border border-base-300 rounded-md bg-base-200 w-full max-w-xl">
              <h3 className="text-lg font-medium mb-2">{t('bulkUpload_summary_heading', 'Upload Summary')}</h3>
              <ul className="list-disc list-inside text-sm">
                <li>{t('bulkUpload_summary_processed', 'Total Records Processed:')} {uploadSummary.total_processed}</li>
                <li>{t('bulkUpload_summary_succeeded', 'Successfully Created/Updated:')} {uploadSummary.total_succeeded}</li>
                <li>{t('bulkUpload_summary_failed', 'Failed Records:')} {uploadSummary.total_failed}</li>
              </ul>
            </div>
          )}

          {uploadResults.length > 0 && !isProcessing && (
            <div className="mt-4 w-full max-w-4xl">
              <h3 className="text-lg font-medium mb-3">{t('bulkUpload_results_heading', 'Detailed Results')}</h3>
              <div className="overflow-x-auto">
                <table className="table table-zebra table-sm w-full">
                  <thead>
                    <tr>
                      <th>{t('bulkUpload_results_row', 'Row')}</th>
                      <th>{t('bulkUpload_results_name', 'Student Name')}</th>
                      <th>{t('bulkUpload_results_status', 'Status')}</th>
                      <th>{t('bulkUpload_results_class', 'Class Assigned/Attempted')}</th>
                      <th>{t('bulkUpload_results_message', 'Message')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {uploadResults.map((result, index) => (
                      <tr key={index} className={result.status === 'FAILED' ? 'bg-error/20' : ''}>
                        <td>{result.row_number}</td>
                        <td>{result.student_name}</td>
                        <td>
                          <span className={`badge ${result.status.startsWith('CREATED') ? 'badge-success' : result.status === 'FAILED' ? 'badge-error' : 'badge-warning'} badge-sm`}>
                            {result.status}
                          </span>
                        </td>
                        <td>{result.class_name_processed || t('bulkUpload_text_notApplicable', 'N/A')}</td>
                        <td className="text-xs">{result.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => navigate('/students')}
                  className="btn btn-secondary"
                >
                  {t('bulkUpload_button_backToStudents', 'Back to Students')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default BulkUploadPage; 