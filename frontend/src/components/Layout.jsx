// src/components/Layout.jsx
import React, { useEffect, useRef } from 'react';
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
  const { profile, isLoadingProfile, isProfileComplete } = useTeacherProfile();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTimeoutRef = useRef(null);

  useEffect(() => {
    console.log('[Layout] useEffect - Path:', location.pathname, 'AuthLoading:', isAuthLoading, 'Authenticated:', isAuthenticated, 'ProfileLoading:', isLoadingProfile, 'ProfileComplete:', isProfileComplete);
    
    if (redirectTimeoutRef.current) {
      clearTimeout(redirectTimeoutRef.current);
      redirectTimeoutRef.current = null;
    }
    
    if (!isAuthLoading && isAuthenticated) {
      // Redirect if:
      // 1. We are not already on the profile page.
      // 2. AND (EITHER the profile is still loading (optimistic redirect for new users)
      // OR the profile has finished loading and is confirmed incomplete).
      if (location.pathname !== '/profile' && (isLoadingProfile || !isProfileComplete)) {
        console.log(`[Layout] Redirect condition met: path=${location.pathname}, isLoadingProfile=${isLoadingProfile}, isProfileComplete=${isProfileComplete}. Scheduling redirect to /profile.`);
        redirectTimeoutRef.current = setTimeout(() => {
          console.log('[Layout] Executing delayed redirect to /profile (due to loading or incomplete status)');
          navigate('/profile', { replace: true });
        }, 300); // 300ms delay 
      }
    }
    
    return () => {
      if (redirectTimeoutRef.current) {
        clearTimeout(redirectTimeoutRef.current);
      }
    };
  }, [isAuthenticated, isAuthLoading, isLoadingProfile, isProfileComplete, navigate, location.pathname]);

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
          {/* ===== TEST DIVS START ===== */}
          {/*
          <div className="p-4 m-4 border-2 border-black bg-white">
            <div className="text-custom-debug-alert p-2">This should be MAGENTA text (custom-debug-alert from theme.extend.colors)</div>
            <div className="bg-custom-debug-bg p-2 mt-2">This should have a CYAN background (custom-debug-bg from theme.extend.colors)</div>
            <div className="text-primary p-2 mt-2">This should be HOT PINK text (text-primary from DaisyUI theme)</div>
            <div className="bg-primary p-2 mt-2">This should have a HOT PINK background (bg-primary from DaisyUI theme)</div>
            <p className="mt-2">Regular text for contrast.</p>
          </div>
          */}
          {/* ===== TEST DIVS END ===== */}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default Layout;