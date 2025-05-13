import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

function AssessmentPage() {
  const { t } = useTranslation();
  const { documentId } = useParams();
  return (
    <div>
      <h1 className="text-3xl font-semibold text-base-content mb-4">{t('assessment_heading')}</h1>
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <p className="text-base-content">{t('assessment_placeholder_content1', { documentId: documentId })}</p>
          <p className="text-base-content">{t('assessment_placeholder_content2')}</p>
        </div>
      </div>
    </div>
  );
}

export default AssessmentPage; 