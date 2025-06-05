// src/components/Layout.jsx
import React, { useEffect, useRef } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

// --- Import Icons ---
import { InformationCircleIcon } from '@heroicons/react/24/outline';
// --------------------

// Helper function to determine profile completion
const isProfileEffectivelyComplete = (user) => {
  if (!user) return false;
  // Check for actual values, not just presence, and exclude placeholders
  const isComplete = !!(
    user.first_name?.trim() && user.first_name !== 'Not Specified' &&
    user.last_name?.trim() && user.last_name !== 'Not Specified' &&
    user.school_name?.trim() && user.school_name !== 'Not Specified' &&
    user.role && // Assuming role doesn't have a 'Not Specified' placeholder from Kinde/initial setup
    user.country && user.country !== 'Not Specified' &&
    user.state_county?.trim() && user.state_county !== 'Not Specified'
  );
  console.log('[Layout] isProfileEffectivelyComplete check for user:', user, 'Result:', isComplete);
  return isComplete;
};

function Layout({ children }) {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const { currentUser, loading: authContextLoading, error: authContextError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const effectRunId = useRef(0); // For more detailed logging

  useEffect(() => {
    effectRunId.current += 1;
    const currentRunId = effectRunId.current;
    // console.log(`[Layout #${currentRunId}] useEffect run START. Path:`, location.pathname);
    // console.log(`[Layout #${currentRunId}] States: isAuthLoading: ${isAuthLoading}, isAuthenticated: ${isAuthenticated}, authContextLoading: ${authContextLoading}, currentUser:`, currentUser ? 'exists' : 'null', `Path: ${location.pathname}`);

    // No redirects if Kinde auth is still loading or if AuthContext is still loading its data
    if (isAuthLoading || authContextLoading) {
      // console.log(`[Layout #${currentRunId}] Auth loading (Kinde: ${isAuthLoading}, Context: ${authContextLoading}). No redirect actions yet.`);
      return;
    }

    if (isAuthenticated) {
      // console.log(`[Layout #${currentRunId}] Authenticated. CurrentUser:`, currentUser);
      if (location.pathname !== '/profile') {
        const profileComplete = isProfileEffectivelyComplete(currentUser);
        // console.log(`[Layout #${currentRunId}] Profile complete status: ${profileComplete}`);
        if (!profileComplete) {
          // console.log(`[Layout #${currentRunId}] Profile NOT complete. Redirecting to /profile.`);
          navigate('/profile', { replace: true });
        } else {
          // console.log(`[Layout #${currentRunId}] Profile complete. No redirect needed.`);
        }
      } else {
        // console.log(`[Layout #${currentRunId}] Currently on /profile page. No redirect needed.`);
        // If they are on /profile and profile becomes complete, they can navigate away freely.
        // No action needed here to force them off /profile.
      }
    } else {
      // console.log(`[Layout #${currentRunId}] Not authenticated. No redirect logic for profile completion.`);
      // Handle unauthenticated users if necessary (e.g., redirect to login), though Kinde typically handles this.
    }

    // console.log(`[Layout #${currentRunId}] useEffect run END.`);
  }, [
    isAuthenticated,
    isAuthLoading,
    currentUser,
    authContextLoading,
    navigate,
    location.pathname
  ]);

  // Display full-page loader if Kinde is authenticating OR (if authenticated and AuthContext is still loading profile data)
  if (isAuthLoading || (isAuthenticated && authContextLoading)) {
    // console.log('[Layout] Displaying FULL PAGE LOADER. isAuthLoading:', isAuthLoading, 'isAuthenticated:', isAuthenticated, 'authContextLoading:', authContextLoading);
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="loading loading-spinner loading-lg"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // This part can remain, it handles the case where Kinde confirms the user is not authenticated.
    // console.log('[Layout] User NOT authenticated (and not loading). Showing login required message.');
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