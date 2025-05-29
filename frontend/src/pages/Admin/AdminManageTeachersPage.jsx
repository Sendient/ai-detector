import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { PencilSquareIcon, TrashIcon, ArrowsUpDownIcon, ChevronUpIcon, ChevronDownIcon, XCircleIcon, UserPlusIcon } from '@heroicons/react/24/outline';
import { useAuth } from '../../contexts/AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function AdminManageTeachersPage() {
  const { t } = useTranslation();
  const { getToken, isAuthenticated, isLoading: isAuthLoading } = useKindeAuth();
  const { currentUser, loading: isAuthContextLoading } = useAuth();
  const navigate = useNavigate();

  const [teachers, setTeachers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortField, setSortField] = useState('last_name'); // Default sort by last name
  const [sortOrder, setSortOrder] = useState('asc');

  const fetchAllTeachersAdmin = useCallback(async () => {
    if (!isAuthenticated || !currentUser?.is_administrator) {
      setError(t('messages_error_adminRequired'));
      setIsLoading(false);
      if (!isAuthenticated) navigate('/login');
      else if (!currentUser?.is_administrator) navigate('/');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      // Placeholder endpoint - needs to be created on the backend
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/teachers/all`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        let errorDetail = response.statusText;
        try {
          const errData = await response.json();
          if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map(e => `${e.loc?.join('->') || 'field'}: ${e.msg}`).join(', ');
          } else if (errData.detail) {
            errorDetail = String(errData.detail);
          }
          console.error("Raw error data from fetchAllTeachersAdmin:", errData);
        } catch (jsonParseError) {
          console.error("Failed to parse error response as JSON in fetchAllTeachersAdmin:", jsonParseError);
        }
        throw new Error(t('adminManageTeachers_error_fetch', { detail: errorDetail }));
      }
      const data = await response.json();
      // Assuming data is an array of teacher objects
      // Ensure each teacher has a unique 'id' field, mapping from '_id' if necessary
      setTeachers(data.map(teacher => ({ ...teacher, id: teacher._id || teacher.id }))); 
    } catch (err) {
      console.error("Error fetching all teachers for admin:", err);
      setError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoading(false);
    }
  }, [getToken, isAuthenticated, currentUser, t, navigate]);

  useEffect(() => {
    if (!isAuthLoading && !isAuthContextLoading) {
      if (isAuthenticated && currentUser) {
        if (currentUser.is_administrator) {
          fetchAllTeachersAdmin();
        } else {
          setError(t('messages_error_adminRequired', 'Admin privileges required to view this page.'));
          setIsLoading(false);
          // navigate('/'); // Optionally redirect non-admins
        }
      } else if (!isAuthenticated) {
        setError(t('messages_error_loginRequired', 'Please log in to view this page.'));
        setIsLoading(false);
        // navigate('/login'); // Optionally redirect to login
      }
    }
  }, [fetchAllTeachersAdmin, isAuthenticated, isAuthLoading, currentUser, isAuthContextLoading, navigate, t]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const sortedTeachers = React.useMemo(() => {
    if (!teachers) return [];
    return [...teachers].sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      let comparison = 0;
      if (valA === null || valA === undefined) comparison = -1; // Handle null/undefined values
      else if (valB === null || valB === undefined) comparison = 1;
      else if (typeof valA === 'string' && typeof valB === 'string') {
        comparison = valA.localeCompare(valB);
      } else {
        if (valA > valB) comparison = 1;
        else if (valA < valB) comparison = -1;
      }
      return sortOrder === 'asc' ? comparison : comparison * -1;
    });
  }, [teachers, sortField, sortOrder]);

  // Placeholder handlers
  const handleAddTeacher = () => console.log('Add new teacher clicked'); // For potential future use
  const handleEditTeacher = (teacherId) => console.log('Edit teacher:', teacherId);
  const handleDeleteTeacher = (teacherId) => console.log('Delete teacher:', teacherId);

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
        <h1 className="text-2xl font-semibold">{t('adminManageTeachers_heading', 'Manage Teachers (Admin)')}</h1>
        {/* Add button can be re-enabled if needed, e.g., for inviting new teachers */}
        {/* <button onClick={handleAddTeacher} className="btn btn-primary">
          <UserPlusIcon className="h-5 w-5 mr-2" />
          {t('adminManageTeachers_button_addTeacher', 'Add New Teacher')}
        </button> */}
      </div>

      <div className="card bg-base-100 shadow-xl w-full"> {/* Ensure full width for the table card */}
        <div className="card-body">
          <div className="overflow-x-auto">
            {sortedTeachers.length === 0 && !isLoading ? (
              <p className="text-center py-4">{t('adminManageTeachers_noTeachers', 'No teachers found.')}</p>
            ) : (
              <table className="table table-zebra w-full">
                <thead>
                  <tr>
                    <th onClick={() => handleSort('last_name')} className="cursor-pointer">
                      {t('adminManageTeachers_col_lastName', 'Last Name')}
                      {sortField === 'last_name' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th onClick={() => handleSort('first_name')} className="cursor-pointer">
                      {t('adminManageTeachers_col_firstName', 'First Name')}
                      {sortField === 'first_name' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th onClick={() => handleSort('email')} className="cursor-pointer">
                      {t('adminManageTeachers_col_email', 'Email')}
                      {sortField === 'email' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th onClick={() => handleSort('school_name')} className="cursor-pointer">
                      {t('adminManageTeachers_col_schoolName', 'School')}
                      {sortField === 'school_name' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                     <th onClick={() => handleSort('current_plan')} className="cursor-pointer">
                      {t('adminManageTeachers_col_currentPlan', 'Plan')}
                      {sortField === 'current_plan' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th onClick={() => handleSort('is_active')} className="cursor-pointer">
                      {t('adminManageTeachers_col_isActive', 'Active')}
                      {sortField === 'is_active' ? (sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1"/> : <ChevronDownIcon className="h-4 w-4 inline ml-1"/>) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400"/>}
                    </th>
                    <th>{t('adminManageTeachers_col_actions', 'Actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTeachers.map((teacher) => (
                    <tr key={teacher.id}>
                      <td>{teacher.last_name || t('common_text_notApplicable', 'N/A')}</td>
                      <td>{teacher.first_name || t('common_text_notApplicable', 'N/A')}</td>
                      <td>{teacher.email || t('common_text_notApplicable', 'N/A')}</td>
                      <td>{teacher.school_name || t('common_text_notApplicable', 'N/A')}</td>
                      <td>{teacher.current_plan || t('common_text_notApplicable', 'N/A')}</td>
                      <td>
                        <span className={`badge ${teacher.is_active ? 'badge-success' : 'badge-error'}`}>
                          {teacher.is_active ? t('adminManageTeachers_status_active', 'Active') : t('adminManageTeachers_status_inactive', 'Inactive')}
                        </span>
                      </td>
                      <td className="space-x-2">
                        <button onClick={() => handleEditTeacher(teacher.id)} className="btn btn-sm btn-ghost text-info" title={t('adminManageTeachers_tooltip_edit', 'Edit Teacher')}>
                          <PencilSquareIcon className="h-5 w-5" />
                        </button>
                        {/* Delete teacher might be a more sensitive operation, consider a soft delete or confirmation */}
                        <button onClick={() => handleDeleteTeacher(teacher.id)} className="btn btn-sm btn-ghost text-error" title={t('adminManageTeachers_tooltip_delete', 'Delete Teacher')}>
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

export default AdminManageTeachersPage; 