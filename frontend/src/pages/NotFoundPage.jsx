import React from 'react';
import { useTranslation } from 'react-i18next';

function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div>
      <h1 className="text-3xl font-semibold text-base-content mb-4">{t('notFound_heading')}</h1>
      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <p className="text-base-content">{t('notFound_message')}</p>
        </div>
      </div>
    </div>
  );
}

export default NotFoundPage; 