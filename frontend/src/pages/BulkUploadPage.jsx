import React from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpTrayIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline';

function BulkUploadPage() {
  const { t } = useTranslation();

  const handleBulkUpload = () => {
    // TODO: Implement actual bulk upload logic (e.g., open file dialog, API call)
    console.log("Bulk Upload button clicked");
    // For now, you might want to navigate to a different page or show a modal
  };

  const handleDownloadTemplate = () => {
    // TODO: Implement template download logic (e.g., trigger API download or link to static file)
    console.log("Download Template button clicked");
    // Example: window.location.href = '/path/to/template.csv';
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
            >
              <ArrowUpTrayIcon className="h-5 w-5 mr-2" />
              {t('bulkUpload_button_upload', 'Bulk Upload Files')}
            </button>
            
            <button 
              onClick={handleDownloadTemplate}
              className="btn btn-secondary btn-lg"
            >
              <ArrowDownTrayIcon className="h-5 w-5 mr-2" />
              {t('bulkUpload_button_downloadTemplate', 'Download Template')}
            </button>
          </div>

          {/* Optional: Add a section for file drop zone or file list later */}
        </div>
      </div>
    </div>
  );
}

export default BulkUploadPage; 