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
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/quickstart" element={<QuickStartPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId/text-view" element={<ExtractedTextPage />} />
        <Route path="/documents/:documentId/report" element={<AIDetectionReportPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/classes" element={<ClassesPage />} />
        <Route path="/students" element={<StudentsPage />} />
        <Route path="/assess/:documentId" element={<AssessmentPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/schools" element={<SchoolsPage />} />
        <Route path="/teachers" element={<TeachersPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default App;