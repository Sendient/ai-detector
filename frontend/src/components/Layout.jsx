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
  const { profile, isLoadingProfile, checkProfileCompletion } = useTeacherProfile();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTimeoutRef = useRef(null);
  const effectRunId = useRef(0); // For more detailed logging

  useEffect(() => {
    effectRunId.current += 1;
    const currentRunId = effectRunId.current;
    console.log(`[Layout #${currentRunId}] useEffect run START. Path:`, location.pathname);

    // Always clear any existing redirect timeout at the start of the effect.
    if (redirectTimeoutRef.current) {
      console.log(`[Layout #${currentRunId}] Clearing previous redirect timeout ID:`, redirectTimeoutRef.current);
      clearTimeout(redirectTimeoutRef.current);
      redirectTimeoutRef.current = null;
    }

    let layoutDeterminedProfileComplete = false;
    if (profile && !isLoadingProfile) {
        // If profile data exists and we are NOT loading, 
        // Layout calculates completion status directly from the profile data it has NOW.
        layoutDeterminedProfileComplete = checkProfileCompletion(profile);
    }

    console.log(`[Layout #${currentRunId}] useEffect run. Path:`, location.pathname,
                'AuthL:', isAuthLoading, 'AuthOK:', isAuthenticated,
                'ProfL:', isLoadingProfile, 'ProfData:', profile ? 'exists' : 'null',
                'LayoutDeterminedComplete:', layoutDeterminedProfileComplete);

    if (!isAuthLoading && isAuthenticated) {
      if (location.pathname !== '/profile') {
        if (isLoadingProfile) {
          if (profile === null) {
            console.log(`[Layout #${currentRunId}] CASE 1.1: Profile NULL & loading. Redirecting.`);
            redirectTimeoutRef.current = setTimeout(() => {
              console.log(`[Layout #${currentRunId}] EXECUTING redirect (profile was null and loading). Timeout ID:`, redirectTimeoutRef.current);
              navigate('/profile', { replace: true });
            }, 300);
            console.log(`[Layout #${currentRunId}] Scheduled redirect timeout ID:`, redirectTimeoutRef.current);
          } else {
            console.log(`[Layout #${currentRunId}] CASE 1.2: Profile EXISTS & reloading. Waiting...`);
            // DO NOTHING - wait for reload to finish. Effect will re-run.
          }
        } else {
          // CASE 2: Profile IS NOT loading.
          if (!layoutDeterminedProfileComplete) {
            console.log(`[Layout #${currentRunId}] CASE 2.1: Profile NOT loading, LayoutDeterminedComplete FALSE. Redirecting.`);
            // No timeout here, decision is based on current, non-loading state.
            navigate('/profile', { replace: true }); 
          } else {
            console.log(`[Layout #${currentRunId}] CASE 2.2: Profile NOT loading, LayoutDeterminedComplete TRUE. No redirect.`);
          }
        }
      } else {
        console.log(`[Layout #${currentRunId}] On /profile. No redirect.`);
        if (redirectTimeoutRef.current) {
           console.log(`[Layout #${currentRunId}] Clearing timeout because on /profile page. ID:`, redirectTimeoutRef.current);
           clearTimeout(redirectTimeoutRef.current);
           redirectTimeoutRef.current = null;
        }
      }
    } else {
      console.log(`[Layout #${currentRunId}] Not Authenticated or Auth Loading. No redirect logic.`);
    }

    console.log(`[Layout #${currentRunId}] useEffect run END.`);
    return () => {
      console.log(`[Layout #${currentRunId}] useEffect CLEANUP. Path:`, location.pathname, 'Current Timeout ID:', redirectTimeoutRef.current);
      if (redirectTimeoutRef.current) {
        console.log(`[Layout #${currentRunId}] Cleanup: Clearing redirect timeout ID:`, redirectTimeoutRef.current);
        clearTimeout(redirectTimeoutRef.current);
        redirectTimeoutRef.current = null;
      }
    };
  }, [
    isAuthenticated,
    isAuthLoading,
    profile, 
    isLoadingProfile,
    checkProfileCompletion,
    navigate,
    location.pathname
  ]);

  // Adjusted loading state display logic
  if (isAuthLoading || (profile === null && isAuthenticated && isLoadingProfile && location.pathname !== '/profile')) {
    console.log('[Layout] Displaying FULL PAGE LOADER. isAuthLoading:', isAuthLoading, 'profileNull:', profile === null, 'isAuthenticated:', isAuthenticated, 'isLoadingProfile:', isLoadingProfile, 'pathname:', location.pathname);
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="loading loading-spinner loading-lg"></div>
      </div>
    );
  }

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