import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext'; // Assuming AuthContext provides user info
import { useNavigate, Link } from 'react-router-dom';
import { ShieldCheckIcon, EyeIcon, ChevronUpIcon, ChevronDownIcon, ArrowsUpDownIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react'; // Added for getToken
// You might want to create a specific API service for admin actions
// import adminApiService from '../services/adminApiService'; 

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// Small, reusable table component for admin dashboard previews
const PreviewTable = ({ headers, data, renderRow, isLoading, error, noDataMessage, viewAllLink, viewAllText, sortConfig, requestSort }) => {
  const { t } = useTranslation();
  if (isLoading) return <div className="flex justify-center items-center p-4"><span className="loading loading-spinner loading-sm"></span></div>;
  if (error) return <div className="alert alert-error text-xs p-2"><div><span>{error}</span></div></div>;
  if (data.length === 0) return <p className="text-center py-4 text-sm">{noDataMessage}</p>;

  const getSortIcon = (headerKey) => {
    if (sortConfig && sortConfig.key === headerKey) {
      if (sortConfig.direction === 'ascending') {
        return <ChevronUpIcon className="h-4 w-4 ml-1 inline-block text-primary" />;
      }
      return <ChevronDownIcon className="h-4 w-4 ml-1 inline-block text-primary" />;
    }
    // If the column is sortable (requestSort is provided) but not the active sort column, show a neutral icon
    if (requestSort) {
      return <ArrowsUpDownIcon className="h-4 w-4 ml-1 inline-block text-gray-400 hover:text-gray-500" />;
    }
    return null; // No icon if not sortable
  };

  return (
    <div className="overflow-x-auto">
      <table className="table table-sm w-full">
        <thead>
          <tr>
            {headers.map(header => (
              <th key={header.key} onClick={() => requestSort && requestSort(header.key)} className={requestSort ? "cursor-pointer select-none" : ""}>
                {header.label}
                {requestSort && getSortIcon(header.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(item => renderRow(item))}
        </tbody>
      </table>
      {viewAllLink && (
        <div className="card-actions justify-end mt-4">
          <Link to={viewAllLink} className="btn btn-ghost btn-sm text-primary">
            <EyeIcon className="h-4 w-4 mr-1" />
            {viewAllText || t('common_button_viewAll', 'View All')}
          </Link>
        </div>
      )}
    </div>
  );
};

const AdminPage = () => {
    const { currentUser, loading: isAuthContextLoading } = useAuth();
    const { getToken, isAuthenticated, isLoading: isKindeAuthLoading } = useKindeAuth(); // For fetching teachers
    const navigate = useNavigate();
    const [adminData, setAdminData] = useState(null);
    const [error, setError] = useState('');
    const { t } = useTranslation();

    // State for teachers table in the card
    const [teachers, setTeachers] = useState([]);
    const [teachersLoading, setTeachersLoading] = useState(true);
    const [teachersError, setTeachersError] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'created_at', direction: 'descending' });

    const fetchLimitedTeachers = useCallback(async () => {
      if (!isAuthenticated || !currentUser?.is_administrator) {
        // Don't set error here, as main page might still be accessible for other cards
        setTeachersLoading(false);
        return;
      }
      setTeachersLoading(true);
      setTeachersError(null);
      try {
        const token = await getToken();
        if (!token) throw new Error(t('messages_error_authTokenMissing'));

        // Fetch, for example, top 5 teachers, ordered by a relevant field if API supports
        // Or fetch all and slice. For now, assume API might support limit or we slice.
        // Using the same endpoint as the full page for now.
        const response = await fetch(`${API_BASE_URL}/api/v1/admin/teachers/all?limit=5`, { // Added limit=5
          headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!response.ok) {
          let errorDetail = response.statusText;
          try {
            const errData = await response.json();
            errorDetail = errData.detail || response.statusText;
          } catch (_) { /* Do nothing if parsing fails */ }
          throw new Error(t('adminManageTeachers_error_fetch', { detail: errorDetail }));
        }
        const data = await response.json();
        // If the limit=5 is not supported by backend, slice here.
        setTeachers(data.slice(0, 5).map(teacher => ({ ...teacher, id: teacher._id || teacher.id })));
      } catch (err) {
        console.error("Error fetching teachers for admin dashboard card:", err);
        setTeachersError(err.message || t('messages_error_unexpected'));
      } finally {
        setTeachersLoading(false);
      }
    }, [getToken, isAuthenticated, currentUser, t]);

    useEffect(() => {
        // Redirect if not admin or still loading
        if (!isKindeAuthLoading && !isAuthContextLoading) {
            if (!currentUser || !currentUser.is_administrator) {
                if (isAuthenticated) navigate('/'); 
                // else if not authenticated, Kinde usually handles redirect via its own hooks/router guards if setup
                return;
            }
            if (currentUser && currentUser.is_administrator) {
                setAdminData({ overview: "Welcome to the Admin Dashboard." }); // Simplified placeholder
                fetchLimitedTeachers(); // Fetch teachers for the card
            }
        }
    }, [currentUser, isAuthContextLoading, isKindeAuthLoading, navigate, fetchLimitedTeachers, isAuthenticated]);

    const requestSort = (key) => {
      let direction = 'ascending';
      if (sortConfig.key === key && sortConfig.direction === 'ascending') {
        direction = 'descending';
      } else if (sortConfig.key === key && sortConfig.direction === 'descending') {
        // Optional: Third click could reset sort or remove it. For now, just toggle.
        // Or revert to a default sort like by name ascending if toggling off current sort.
        // For simplicity, we'll just toggle. A third click on 'descending' will make it 'ascending'.
         direction = 'ascending'; 
      }
      setSortConfig({ key, direction });
    };

    const sortedTeachers = useMemo(() => {
      let sortableItems = [...teachers];
      if (sortConfig.key !== null) {
        sortableItems.sort((a, b) => {
          const aValue = a[sortConfig.key];
          const bValue = b[sortConfig.key];

          // Handle undefined or null values by pushing them to the end
          if (aValue == null && bValue == null) return 0;
          if (aValue == null) return sortConfig.direction === 'ascending' ? 1 : -1;
          if (bValue == null) return sortConfig.direction === 'ascending' ? -1 : 1;
          
          // Date sorting
          if (['created_at', 'updated_at', 'pro_plan_activated_at'].includes(sortConfig.key)) {
            const dateA = new Date(aValue).getTime();
            const dateB = new Date(bValue).getTime();
            if (dateA < dateB) return sortConfig.direction === 'ascending' ? -1 : 1;
            if (dateA > dateB) return sortConfig.direction === 'ascending' ? 1 : -1;
            return 0;
          }

          // Boolean sorting (true comes before false in ascending)
          if (typeof aValue === 'boolean' && typeof bValue === 'boolean') {
            if (aValue === bValue) return 0;
            if (sortConfig.direction === 'ascending') {
              return aValue ? -1 : 1; // true first
            }
            return aValue ? 1 : -1; // false first
          }
          
          // Numeric sorting
          if (typeof aValue === 'number' && typeof bValue === 'number') {
            if (aValue < bValue) return sortConfig.direction === 'ascending' ? -1 : 1;
            if (aValue > bValue) return sortConfig.direction === 'ascending' ? 1 : -1;
            return 0;
          }

          // String sorting (case-insensitive)
          if (typeof aValue === 'string' && typeof bValue === 'string') {
            const comparison = aValue.toLowerCase().localeCompare(bValue.toLowerCase());
            return sortConfig.direction === 'ascending' ? comparison : -comparison;
          }
          
          return 0; // Default no change
        });
      }
      return sortableItems;
    }, [teachers, sortConfig]);

    if (isKindeAuthLoading || isAuthContextLoading) {
        return <div className="p-8 text-center">{t('adminPage_loading', 'Loading admin dashboard...')}</div>;
    }

    // Check if user is not an admin after loading is complete.
    if (!currentUser || !currentUser.is_administrator) {
        // This case should ideally be handled by redirection in useEffect, but as a fallback:
        return <div className="p-8 text-center">{t('adminPage_notAdmin', 'You do not have administrator privileges.')}</div>;
    }

    // Placeholder data for cards - you can expand this later
    const adminCards = [
        {
            id: 'students',
            titleKey: 'admin_card_students_title', // e.g., "Manage Students"
            descriptionKey: 'admin_card_students_description', // e.g., "View, edit, or manage student accounts."
            // icon: Users, // Example icon
            linkTo: '/admin/students' // Example link
        },
        {
            id: 'classes',
            titleKey: 'admin_card_classes_title', // e.g., "Manage Classes"
            descriptionKey: 'admin_card_classes_description', // e.g., "Administer class sections and enrollments."
            // icon: Library, // Example icon
            linkTo: '/admin/manage-classes' // Changed from /admin/classes
        },
        {
            id: 'documents',
            titleKey: 'admin_card_documents_title', // e.g., "Manage Documents"
            descriptionKey: 'admin_card_documents_description', // e.g., "Oversee all submitted documents and reports."
            // icon: FileText, // Example icon
            linkTo: '/admin/documents' // Example link
        }
    ];
    
    const teacherTableHeaders = [
      { key: '_id', label: t('adminManageTeachers_col_teacherId', 'Teacher ID') },
      { key: 'kinde_id', label: t('adminManageTeachers_col_kindeId', 'Kinde ID') },
      { key: 'first_name', label: t('adminManageTeachers_col_firstName', 'First Name') },
      { key: 'last_name', label: t('adminManageTeachers_col_lastName', 'Last Name') },
      { key: 'email', label: t('adminManageTeachers_col_email', 'Email') },
      { key: 'school_name', label: t('adminManageTeachers_col_schoolName', 'School') },
      { key: 'role', label: t('adminManageTeachers_col_role', 'Role') },
      { key: 'is_administrator', label: t('adminManageTeachers_col_isAdministrator', 'Admin?') },
      { key: 'current_plan', label: t('adminManageTeachers_col_currentPlan', 'Plan') },
      { key: 'current_plan_word_limit', label: t('adminManageTeachers_col_wordLimit', 'Word Limit (Cycle)') },
      { key: 'words_used_current_cycle', label: t('adminManageTeachers_col_wordsUsed', 'Words Used (Cycle)') },
      { key: 'remaining_words_current_cycle', label: t('adminManageTeachers_col_wordsRemaining', 'Words Rem. (Cycle)') },
      { key: 'documents_processed_current_cycle', label: t('adminManageTeachers_col_docsProcessed', 'Docs Proc. (Cycle)') },
      { key: 'is_active', label: t('adminManageTeachers_col_isActive', 'Active') },
      { key: 'is_deleted', label: t('adminManageTeachers_col_isDeleted', 'Deleted?') },
      { key: 'country', label: t('adminManageTeachers_col_country', 'Country') },
      { key: 'state_county', label: t('adminManageTeachers_col_stateCounty', 'State/County') },
      { key: 'how_did_you_hear', label: t('adminManageTeachers_col_howDidYouHear', 'Heard Via') },
      { key: 'description', label: t('adminManageTeachers_col_description', 'Description') },
      { key: 'stripe_customer_id', label: t('adminManageTeachers_col_stripeCustomerId', 'Stripe CID') },
      { key: 'subscription_status', label: t('adminManageTeachers_col_subscriptionStatus', 'Sub Status') },
      { key: 'pro_plan_activated_at', label: t('adminManageTeachers_col_proPlanActivatedAt', 'Pro Since') },
      { key: 'created_at', label: t('adminManageTeachers_col_createdAt', 'Created At') },
      { key: 'updated_at', label: t('adminManageTeachers_col_updatedAt', 'Updated At') },
    ];

    const formatDate = (dateString) => {
      if (!dateString) return '';
      try {
        return new Date(dateString).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      } catch (e) {
        return dateString;
      }
    };

    const renderTeacherRow = (teacher) => (
      <tr key={teacher.id || teacher._id}> {/* Use teacher.id (which is mapped from _id) or _id directly */}
        <td>{teacher._id || ''}</td>
        <td>{teacher.kinde_id || ''}</td>
        <td>{teacher.first_name || ''}</td>
        <td>{teacher.last_name || ''}</td>
        <td>{teacher.email || ''}</td>
        <td>{teacher.school_name || ''}</td>
        <td>{teacher.role || ''}</td>
        <td>
          <span className={`badge badge-sm ${teacher.is_administrator ? 'badge-info' : 'badge-ghost'}`}>
            {teacher.is_administrator ? 'Yes' : 'No'}
          </span>
        </td>
        <td>{teacher.current_plan || ''}</td>
        <td>{typeof teacher.current_plan_word_limit === 'number' ? teacher.current_plan_word_limit.toLocaleString() : (teacher.current_plan === 'SCHOOLS' ? t('common_text_unlimited') : '')}</td>
        <td>{typeof teacher.words_used_current_cycle === 'number' ? teacher.words_used_current_cycle.toLocaleString() : ''}</td>
        <td>{typeof teacher.remaining_words_current_cycle === 'number' ? teacher.remaining_words_current_cycle.toLocaleString() : (teacher.current_plan === 'SCHOOLS' ? t('common_text_unlimited') : '')}</td>
        <td>{typeof teacher.documents_processed_current_cycle === 'number' ? teacher.documents_processed_current_cycle.toLocaleString() : ''}</td>
        <td>
          <span className={`badge badge-sm ${teacher.is_active ? 'badge-success' : 'badge-error'}`}>
            {teacher.is_active ? t('adminManageTeachers_status_active', 'Active') : t('adminManageTeachers_status_inactive', 'Inactive')}
          </span>
        </td>
        <td>
          <span className={`badge badge-sm ${teacher.is_deleted ? 'badge-warning' : 'badge-ghost'}`}>
            {teacher.is_deleted ? 'Yes' : 'No'}
          </span>
        </td>
        <td>{teacher.country || ''}</td>
        <td>{teacher.state_county || ''}</td>
        <td>{teacher.how_did_you_hear || ''}</td>
        <td>{teacher.description || ''}</td>
        <td>{teacher.stripe_customer_id || ''}</td>
        <td>{teacher.subscription_status || ''}</td>
        <td>{formatDate(teacher.pro_plan_activated_at)}</td>
        <td>{formatDate(teacher.created_at)}</td>
        <td>{formatDate(teacher.updated_at)}</td>
      </tr>
    );

    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8 text-primary">{t('admin_page_title', 'Admin Dashboard')}</h1>
            
            {error && (
                <div className="alert alert-error shadow-lg mb-6">
                    <div>
                        <ShieldCheckIcon className="h-6 w-6" /> 
                        <span>{t('adminPage_error_main', 'Error loading admin data: {{message}}', { message: error })}</span>
                    </div>
                </div>
            )}

            {adminData && <p className="mb-6">{adminData.overview}</p>} 

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {adminCards.map((card) => (
                    <div key={card.id} className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow duration-300">
                        {/* Card Icon (optional) - uncomment and style if you add icons
                        {card.icon && (
                            <figure className="px-10 pt-10">
                                <card.icon size={48} className="text-primary" />
                            </figure>
                        )}
                        */}
                        <div className="card-body">
                            <h2 className="card-title text-xl font-semibold">{t(card.titleKey, `Manage ${card.id.charAt(0).toUpperCase() + card.id.slice(1)}`)}</h2>
                            <p className="text-sm text-base-content/80">{t(card.descriptionKey, `Manage all ${card.id}.`)}</p>
                            <div className="card-actions justify-end mt-4">
                                <Link to={card.linkTo} className="btn btn-primary btn-sm">
                                    {t('admin_card_button_go', 'Go to ' + card.id)}
                                </Link>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Manage Teachers Card with Embedded Table */}
            <div className="card col-span-1 md:col-span-3 bg-base-100 shadow-xl my-6">
                <div className="card-body">
                    <h2 className="card-title mb-4">{t('adminDashboard_title_manageTeachers', 'Manage Teachers')}</h2>
                    <PreviewTable 
                        headers={teacherTableHeaders}
                        data={sortedTeachers}
                        renderRow={renderTeacherRow}
                        isLoading={teachersLoading}
                        error={teachersError}
                        noDataMessage={t('adminManageTeachers_info_noTeachersFoundCard', 'No teachers to display in preview.')}
                        sortConfig={sortConfig}
                        requestSort={requestSort}
                    />
                </div>
            </div>

        </div>
    );
};

export default AdminPage; 