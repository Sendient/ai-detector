// src/components/Layout.jsx
import React, { useEffect } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { useTeacherProfile } from '../hooks/useTeacherProfile.js';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

// --- Import Icons ---
import { InformationCircleIcon } from '@heroicons/react/24/outline';
// --------------------

function Layout({ children }) {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const { profile, isLoadingProfile } = useTeacherProfile();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!isAuthLoading && isAuthenticated && !isLoadingProfile) {
      if (profile === null && location.pathname !== '/profile') {
        navigate('/profile');
      }
    }
  }, [isAuthenticated, isAuthLoading, profile, isLoadingProfile, navigate, location.pathname]);

  // Show loading state (check both auth and profile loading)
  if (isAuthLoading || (isAuthenticated && isLoadingProfile)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="loading loading-spinner loading-lg"></div>
      </div>
    );
  }

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="alert alert-info shadow-lg">
        <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0" />
        <div>
          <h3 className="font-bold">{t('common_login_required_heading')}</h3>
          <div className="text-xs">{t('common_login_required_message')}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-base-200">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-base-200 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default Layout;