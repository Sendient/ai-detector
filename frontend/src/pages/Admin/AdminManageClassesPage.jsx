import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { PlusIcon, PencilSquareIcon, TrashIcon, ArrowsUpDownIcon, ChevronUpIcon, ChevronDownIcon, XCircleIcon } from '@heroicons/react/24/outline';
import { useAuth } from '../../contexts/AuthContext'; // Assuming AuthContext provides admin status

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function AdminManageClassesPage() {
  const { t } = useTranslation();
  const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const { currentUser, loading: isAuthContextLoading } = useAuth();
  const navigate = useNavigate();

  const [classes, setClasses] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortField, setSortField] = useState('class_name');
  const [sortOrder, setSortOrder] = useState('asc');

  const fetchAllClasses = useCallback(async () => {
    if (!isAuthenticated) {
      setError(t('messages_error_loginRequired'));
      setIsLoading(false);
      return;
    }
    // TODO: Add check for admin privileges from currentUser once available and confirmed
    // if (!currentUser?.is_administrator) {
    //   setError(t('messages_error_adminRequired'));
    //   setIsLoading(false);
    //   navigate('/'); // Redirect non-admins
    //   return;
    // }

    setIsLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      // This endpoint allows admins to fetch all class groups.
      const response = await fetch(`${API_BASE_URL}/api/v1/class-groups/all-admin`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        let errorDetail = response.statusText; // Default to status text
        try {
          const errData = await response.json();
          // If errData.detail is an array (FastAPI validation errors), stringify it
          if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map(e => `${e.loc?.join('->') || 'field'}: ${e.msg}`).join(', ');
          } else if (errData.detail) { // If errData.detail is a string or other primitive
            errorDetail = String(errData.detail);
          }
          // Log the raw errData as well
          console.error("Raw error data from response.json():", errData); 
        } catch (jsonParseError) {
          console.error("Failed to parse error response as JSON:", jsonParseError);
          // errorDetail remains response.statusText
        }
        throw new Error(t('messages_classes_fetchError', { detail: errorDetail }));
      }
      const data = await response.json();
      setClasses(data.map(cls => ({ ...cls, id: cls._id || cls.id })));
    } catch (err) {
      console.error("Error fetching all classes:", err);
      setError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoading(false);
    }
  }, [getToken, isAuthenticated, t, navigate, currentUser]); // Added currentUser

  useEffect(() => {
    if (!isAuthLoading && !isAuthContextLoading) {
        if (isAuthenticated && currentUser) { // Ensure currentUser is loaded
            if (currentUser.is_administrator) {
                fetchAllClasses();
            } else {
                setError(t('messages_error_adminRequired', 'Admin privileges required to view this page.'));
                setIsLoading(false);
                // navigate('/'); // Optionally redirect
            }
        } else if (!isAuthenticated) {
            setError(t('messages_error_loginRequired', 'Please log in to view this page.'));
            setIsLoading(false);
            // navigate('/login'); // Optionally redirect
        }
    }
  }, [fetchAllClasses, isAuthenticated, isAuthLoading, currentUser, isAuthContextLoading, navigate, t]);


  const handleSort = (field) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const sortedClasses = React.useMemo(() => {
    if (!classes) return [];
    return [...classes].sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      let comparison = 0;
      if (valA > valB) comparison = 1;
      else if (valA < valB) comparison = -1;
      return sortOrder === 'asc' ? comparison : comparison * -1;
    });
  }, [classes, sortField, sortOrder]);

  // Placeholder handlers for editing/deleting classes are not yet implemented.
  const handleEditClass = (classId) => console.log('Edit class:', classId);
  const handleDeleteClass = (classId) => console.log('Delete class:', classId);

  if (isAuthLoading || isAuthContextLoading || isLoading) {
    return <div className="flex justify-center items-center min-h-screen"><span className="loading loading-spinner loading-lg"></span></div>;
  }

  if (error) {
    return <div className="alert alert-error shadow-lg"><div><XCircleIcon className="h-6 w-6" /><span>{error}</span></div></div>;
  }
  
  if (!currentUser?.is_administrator && !isLoading) {
    return (
        <div className="alert alert-warning shadow-lg">
            <div>
                <span className="text-2xl">⚠️</span>
                <span>{t('adminDashboard_auth_adminRequired', 'You must be an administrator to view this page.')}</span>
            </div>
        </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold">{t('adminManageClasses_heading', 'Manage Classes (Admin)')}</h1>
      </div>

      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="overflow-x-auto">
            {sortedClasses.length === 0 && !isLoading ? (
              <p className="text-center py-4">{t('adminManageClasses_noClasses', 'No classes found.')}</p>
            ) : (
              <table className="table table-zebra w-full">
                <thead>
                  <tr>
                    <th onClick={() => handleSort('class_name')} className="cursor-pointer">
                      {t('adminManageClasses_col_className', 'Class Name')}
                      {sortField === 'class_name' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th onClick={() => handleSort('academic_year')} className="cursor-pointer">
                      {t('adminManageClasses_col_academicYear', 'Academic Year')}
                      {sortField === 'academic_year' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th>{t('adminManageClasses_col_teacher', 'Teacher')}</th>
                    <th>{t('adminManageClasses_col_students', 'Students')}</th>
                    <th>{t('adminManageClasses_col_actions', 'Actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedClasses.map((cls) => (
                    <tr key={cls.id}>
                      <td>{cls.class_name}</td>
                      <td>{cls.academic_year}</td>
                      <td>{cls.teacher_id || t('common_text_notApplicable', 'N/A')}</td> {/* TODO: This shows teacher ID. To show name, backend needs to populate it or another query is needed. */}
                      <td>{cls.student_ids?.length || 0}</td>
                      <td className="space-x-2">
                        <button onClick={() => handleEditClass(cls.id)} className="btn btn-sm btn-ghost text-info" title={t('adminManageClasses_tooltip_edit', 'Edit Class')}>
                          <PencilSquareIcon className="h-5 w-5" />
                        </button>
                        <button onClick={() => handleDeleteClass(cls.id)} className="btn btn-sm btn-ghost text-error" title={t('adminManageClasses_tooltip_delete', 'Delete Class')}>
                          <TrashIcon className="h-5 w-5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminManageClassesPage; 