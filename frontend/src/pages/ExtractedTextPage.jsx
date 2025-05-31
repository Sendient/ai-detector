import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { XCircleIcon } from '@heroicons/react/24/outline';
import { HOST_URL, API_PREFIX } from '../services/apiService';

function ExtractedTextPage() {
  const { t } = useTranslation();
  const { documentId } = useParams();
  const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const [extractedText, setExtractedText] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [documentFilename, setDocumentFilename] = useState('...');

  const fetchDocumentMetadata = useCallback(async () => {
    const idToFetch = documentId;
    if (!isAuthenticated || !idToFetch || idToFetch === 'undefined') {
      if (idToFetch === 'undefined') setDocumentFilename('ID: undefined');
      return;
    }
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${HOST_URL}${API_PREFIX}/documents/${idToFetch}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) {
        setDocumentFilename(`ID: ${idToFetch}`);
        return;
      }
      const data = await response.json();
      setDocumentFilename(data.original_filename);
    } catch (err) {
      setDocumentFilename(`ID: ${idToFetch}`);
    }
  }, [documentId, isAuthenticated, getToken, t]);

  const fetchExtractedText = useCallback(async () => {
    if (!isAuthenticated || !documentId || documentId === 'undefined') {
      if (documentId === 'undefined') setError(t('messages_error_invalidId'));
      return;
    }
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${HOST_URL}${API_PREFIX}/documents/${documentId}/text`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || t('messages_error_fetchFailed'));
      }
      const data = await response.json();
      setExtractedText(data.text || '');
    } catch (err) {
      console.error("Error fetching extracted text:", err);
      setError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoading(false);
    }
  }, [documentId, isAuthenticated, getToken, t]);

  useEffect(() => {
    fetchDocumentMetadata();
    fetchExtractedText();
  }, [fetchDocumentMetadata, fetchExtractedText]);

  return (
    <div>
      <h1 className="text-3xl font-semibold text-base-content mb-1">{t('extractedText_heading')}</h1>
      <p className="text-sm text-base-content/70 mb-4">{t('common_label_document')} <span className="font-medium">{documentFilename}</span></p>
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body min-h-[200px] max-h-[70vh] overflow-y-auto">
          {isLoading && (
            <div className="flex justify-center py-4">
              <span className="loading loading-lg loading-spinner text-primary"></span>
              <p className="ml-2">{t('extractedText_status_loading')}</p>
            </div>
          )}
          {error && (
            <div className="alert alert-error">
              <XCircleIcon className="h-6 w-6"/>
              <span>{t('common_error_prefix')} {error}</span>
            </div>
          )}
          {!isLoading && !error && (
            <pre className="text-sm whitespace-pre-wrap break-words font-mono">
              {extractedText ? extractedText : t('extractedText_status_noText')}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

export default ExtractedTextPage; 