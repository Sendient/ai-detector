import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { XCircleIcon } from '@heroicons/react/24/outline';

function ExtractedTextPage() {
  const { t } = useTranslation();
  const { documentId } = useParams();
  const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const [extractedText, setExtractedText] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [documentFilename, setDocumentFilename] = useState('...');
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  const fetchDocumentMetadata = useCallback(async () => {
    const idToFetch = documentId;
    if (!isAuthenticated || !idToFetch || idToFetch === 'undefined') {
      if (idToFetch === 'undefined') setDocumentFilename('ID: undefined');
      return;
    }
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${API_BASE_URL}/api/v1/documents/${idToFetch}`, {
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
  }, [documentId, isAuthenticated, getToken, t, API_BASE_URL]);

  const fetchExtractedText = useCallback(async () => {
    const idToFetch = documentId;
    if (isAuthenticated && idToFetch && idToFetch !== 'undefined') {
      setIsLoading(true);
      setError(null);
      setExtractedText('');
      try {
        const token = await getToken();
        if (!token) {
          throw new Error(t('messages_error_authTokenMissing'));
        }
        const response = await fetch(`${API_BASE_URL}/api/v1/documents/${idToFetch}/text`, {
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
          if (response.status === 404) errorDetail = t('messages_text_notFound');
          if (response.status === 415) errorDetail = t('messages_text_unsupported');
          throw new Error(t('messages_text_fetchError', { detail: errorDetail }));
        }
        const textData = await response.text();
        setExtractedText(textData);
      } catch (err) {
        let displayError = t('messages_error_unexpected');
        if (err instanceof Error) {
          displayError = err.message;
        } else if (typeof err === 'string') {
          displayError = err;
        }
        if (!(displayError === t('messages_text_notFound') ||
            displayError === t('messages_text_unsupported') ||
            displayError.startsWith(t('messages_text_fetchError', { detail: '' }).split(':')[0]))) {
          displayError = t('messages_text_fetchError', { detail: displayError });
        }
        setError(displayError);
      } finally {
        setIsLoading(false);
      }
    } else {
      setIsLoading(false);
      if (!isAuthLoading && !isAuthenticated) {
        setError(t('messages_error_loginRequired_viewText'));
      } else if (!idToFetch || idToFetch === 'undefined') {
        setError(t('messages_text_missingId'));
      }
    }
  }, [documentId, isAuthenticated, isAuthLoading, getToken, t, API_BASE_URL]);

  useEffect(() => {
    if (!isAuthLoading && isAuthenticated) {
      fetchDocumentMetadata();
      fetchExtractedText();
    } else if (!isAuthLoading && !isAuthenticated) {
      setError(t('messages_error_loginRequired_viewText'));
      setIsLoading(false);
    }
  }, [documentId, isAuthLoading, isAuthenticated, fetchDocumentMetadata, fetchExtractedText, t, API_BASE_URL]);

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