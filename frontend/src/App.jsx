// src/App.jsx
import React, { useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import RequireAuth from './pages/RequireAuth';

// Import pages
import DashboardPage from './pages/DashboardPage';
import DocumentsPage from './pages/DocumentsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import ClassesPage from './pages/ClassesPage';
import StudentsPage from './pages/StudentsPage';
import ProfilePage from './pages/ProfilePage';
import ExtractedTextPage from './pages/ExtractedTextPage';
import SchoolsPage from './pages/SchoolsPage';
import TeachersPage from './pages/TeachersPage';
import AssessmentPage from './pages/AssessmentPage';
import NotFoundPage from './pages/NotFoundPage';
import AIDetectionReportPage from './components/AIDetectionReportPage';
import QuickStartPage from './pages/QuickStartPage';
import IntegrationsPage from './pages/IntegrationsPage';
import BulkUploadPage from './pages/BulkUploadPage';
import PaymentSuccessPage from './pages/PaymentSuccessPage';
import PaymentCancelPage from './pages/PaymentCancelPage';
import SubscriptionsPage from './pages/SubscriptionsPage';
import ClassViewPage from './pages/ClassViewPage';

function App() {
  const { isAuthenticated, isLoading, login } = useKindeAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      login();
    }
  }, [isLoading, isAuthenticated, login]);

  if (isLoading || !isAuthenticated) {
    return <div className="flex items-center justify-center min-h-screen"><span className="loading loading-lg loading-spinner text-primary"></span></div>;
  }

  return (
    <Routes>
      {/* ===== TEST DIVS START ===== */}
      {/* <div className="p-4 m-4 border-2 border-black">
        <div className="text-custom-debug-alert p-2">This should be MAGENTA text (custom-debug-alert from theme.extend.colors)</div>
        <div className="bg-custom-debug-bg p-2 mt-2">This should have a CYAN background (custom-debug-bg from theme.extend.colors)</div>
        <div className="text-primary p-2 mt-2">This should be HOT PINK text (text-primary from DaisyUI theme)</div>
        <div className="bg-primary p-2 mt-2">This should have a HOT PINK background (bg-primary from DaisyUI theme)</div>
      </div> */}
      {/* ===== TEST DIVS END ===== */}
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/quickstart" element={<QuickStartPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/bulk-upload" element={<BulkUploadPage />} />
        <Route path="/documents/:documentId/text-view" element={<ExtractedTextPage />} />
        <Route path="/documents/:documentId/report" element={<AIDetectionReportPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/classes" element={<ClassesPage />} />
        <Route path="/classes/view/:classId" element={<ClassViewPage />} />
        <Route path="/students" element={<StudentsPage />} />
        <Route path="/assess/:documentId" element={<AssessmentPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/schools" element={<SchoolsPage />} />
        <Route path="/teachers" element={<TeachersPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/payment/success" element={<PaymentSuccessPage />} />
        <Route path="/payment/canceled" element={<PaymentCancelPage />} />
        <Route path="/subscriptions" element={<SubscriptionsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default App;