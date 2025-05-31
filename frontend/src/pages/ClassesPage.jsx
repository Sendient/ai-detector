import React, { useState, useEffect, useCallback } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import {
    PencilSquareIcon,
    TrashIcon,
    EyeIcon,
    ArrowPathIcon // Assuming this is for the refresh button, keep if used elsewhere
} from '@heroicons/react/24/outline';
import { ChevronUpIcon, ChevronDownIcon, ArrowsUpDownIcon } from '@heroicons/react/20/solid'; // <-- Import sorting icons
import { useAuth } from '../contexts/AuthContext'; // Assuming AuthContext provides getCurrentUser

// VITE_API_BASE_URL will be like http://localhost:8000 (without /api/v1)
const HOST_URL = import.meta.env.VITE_API_BASE_URL;
console.log("ClassesPage: HOST_URL initialized to:", HOST_URL); // Added for debugging
const API_PREFIX = '/api/v1';

function ClassesPage() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { user, isAuthenticated, isLoading: authLoading, getToken } = useKindeAuth();
    const [classGroups, setClassGroups] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isLoadingInitial, setIsLoadingInitial] = useState(true);
    const [error, setError] = useState(null); // For general fetch errors
    const [pageMessage, setPageMessage] = useState({ text: '', type: '' }); // For success/error messages
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [editingClassGroup, setEditingClassGroup] = useState(null);
    const [formData, setFormData] = useState({ class_name: '', academic_year: '' });
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [selectedClassForView, setSelectedClassForView] = useState(null); 

    // Sorting state
    const [sortField, setSortField] = useState('class_name'); // Default sort field
    const [sortOrder, setSortOrder] = useState('asc'); // Default sort order

    const clearPageMessage = () => setTimeout(() => setPageMessage({ text: '', type: '' }), 5000);

    const handleSort = (field) => {
        if (sortField === field) {
            setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            // Default sort order for new field:
            // 'asc' for text fields like class_name, academic_year
            // Potentially 'desc' for date fields if any were added
            setSortOrder('asc');
        }
    };

    const fetchClassGroups = useCallback(async () => {
        if (!isAuthenticated) {
            if (!authLoading) {
                setError(t('messages_error_loginRequired_viewClasses'));
                setPageMessage({ text: t('messages_error_loginRequired_viewClasses'), type: 'error' });
                clearPageMessage();
            }
            setIsLoadingInitial(false);
            return;
        }
        // console.log("ClassesPage: Fetching class groups from URL:", `${HOST_URL}${API_PREFIX}/class-groups`); // Original log
        setIsLoading(true);
        setPageMessage({ text: '', type: '' }); // Clear previous messages
        
        const urlToFetch = `${HOST_URL}${API_PREFIX}/class-groups`; // Define URL variable
        console.log("[VERY PRECISE LOG] ClassesPage: Exactly this URL is being passed to fetch for class groups:", urlToFetch);

        try {
            const token = await getToken();
            if (!token) {
                const msg = t('messages_error_authTokenMissing');
                setError(msg);
                setPageMessage({ text: msg, type: 'error' });
                clearPageMessage();
                setIsLoading(false);
                setIsLoadingInitial(false);
                return;
            }
            const response = await fetch(urlToFetch, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                const msg = errorData.detail || t('messages_classes_fetchError', { message: response.statusText });
                throw new Error(msg);
            }
            const data = await response.json();
            console.log("Fetched Class Groups Data:", JSON.stringify(data, null, 2)); // Log fetched data
            setClassGroups(data || []);
            setError(null); // Clear general error on success
        } catch (err) {
            console.error("[VERY PRECISE LOG] ClassesPage: Fetch failed for URL:", urlToFetch, "Error:", err, "Error message:", err.message, "Error stack:", err.stack);
            setError(err.message);
            setPageMessage({ text: err.message, type: 'error' });
            clearPageMessage();
            setClassGroups([]);
        } finally {
            setIsLoading(false);
            setIsLoadingInitial(false);
        }
    }, [HOST_URL, API_PREFIX, getToken, isAuthenticated, authLoading, t]);

    useEffect(() => {
        fetchClassGroups();
    }, [fetchClassGroups]);

    // Sort classGroups before rendering
    const sortedClassGroups = React.useMemo(() => {
        if (!classGroups || classGroups.length === 0) return [];
        return [...classGroups].sort((a, b) => {
            const fieldA = a[sortField];
            const fieldB = b[sortField];

            // Handle null or undefined values, placing them at the end for asc, start for desc
            if (fieldA == null && fieldB == null) return 0;
            if (fieldA == null) return sortOrder === 'asc' ? 1 : -1;
            if (fieldB == null) return sortOrder === 'asc' ? -1 : 1;

            let comparison = 0;
            if (typeof fieldA === 'string' && typeof fieldB === 'string') {
                comparison = fieldA.localeCompare(fieldB);
            } else {
                // Basic comparison for numbers or other types
                if (fieldA < fieldB) comparison = -1;
                if (fieldA > fieldB) comparison = 1;
            }
            return sortOrder === 'asc' ? comparison : comparison * -1;
        });
    }, [classGroups, sortField, sortOrder]);

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleShowCreateForm = () => {
        if (!user || !user.id) {
            const msg = t('messages_classes_modal_create_error_missingProfile');
            setPageMessage({ text: msg, type: 'error' });
            clearPageMessage();
            return;
        }
        setFormData({ class_name: '', academic_year: '' });
        setEditingClassGroup(null);
        setShowCreateModal(true);
        setPageMessage({ text: '', type: '' }); // Clear message when opening modal
    };

    const handleShowEditForm = (classGroup) => {
        setEditingClassGroup(classGroup);
        setFormData({ class_name: classGroup.class_name, academic_year: classGroup.academic_year || '' });
        setShowEditModal(true);
        setPageMessage({ text: '', type: '' }); // Clear message when opening modal
    };
    
    const handleShowView = (classGroup) => {
        console.log("handleShowView called with classGroup._id:", classGroup._id, "Type:", typeof classGroup._id);
        if (!classGroup || !classGroup._id || classGroup._id === "undefined") {
            console.error("Attempted to view class with invalid ID:", classGroup._id);
            setPageMessage({ text: t('messages_error_invalidId', {item: t('common_label_class')}), type: 'error' });
            clearPageMessage();
            return;
        }
        navigate(`/classes/view/${classGroup._id}`);
    };

    const handleCloseModals = () => {
        setShowCreateModal(false);
        setShowEditModal(false);
        setEditingClassGroup(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!formData.class_name) {
            const msg = t('classes_form_label_className') + " " + t('common_required_indicator');
            setPageMessage({ text: msg, type: 'error' });
            clearPageMessage();
            return;
        }

        setIsSubmitting(true);
        setPageMessage({ text: '', type: '' });
        const method = editingClassGroup ? 'PUT' : 'POST';
        const url = editingClassGroup
            ? `${HOST_URL}${API_PREFIX}/class-groups/${editingClassGroup._id}`
            : `${HOST_URL}${API_PREFIX}/class-groups`;
        console.log("ClassesPage: Submitting form to URL:", url); // Added for debugging

        const payload = {
            class_name: formData.class_name,
            academic_year: formData.academic_year || null,
        };

        try {
            const token = await getToken();
            if (!token) throw new Error(t('messages_error_authTokenMissing'));
            const response = await fetch(url, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(payload),
            });

            const resData = await response.json().catch(() => null); 

            if (!response.ok) {
                const errorDetail = resData?.detail || response.statusText;
                throw new Error(
                    editingClassGroup 
                        ? t('messages_error_actionFailed', { action: t('common_button_update'), detail: errorDetail })
                        : t('messages_classes_modal_create_error_failed', { detail: errorDetail })
                );
            }
            
            const successMsg = editingClassGroup ? t('messages_classes_form_updateSuccess') : t('messages_classes_form_createSuccess');
            setPageMessage({ text: successMsg, type: 'success' });
            clearPageMessage();
            fetchClassGroups();
            handleCloseModals();
        } catch (err) {
            setError(err.message); // Keep general error for top display if needed
            setPageMessage({ text: err.message, type: 'error' });
            clearPageMessage();
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleDelete = async (classId, className) => {
        if (!window.confirm(t('messages_classes_delete_confirm', { className, classId }))) {
            return;
        }
        setIsSubmitting(true);
        setPageMessage({ text: '', type: '' });
        try {
            const token = await getToken();
            if (!token) throw new Error(t('messages_error_authTokenMissing'));
            console.log("ClassesPage: Deleting class group from URL:", `${HOST_URL}${API_PREFIX}/class-groups/${classId}`); // Added for debugging
            const response = await fetch(`${HOST_URL}${API_PREFIX}/class-groups/${classId}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                const msg = t('messages_classes_delete_failed', { message: errorData.detail || response.statusText });
                throw new Error(msg);
            }
            setPageMessage({ text: t('messages_classes_delete_success'), type: 'success' });
            clearPageMessage();
            fetchClassGroups();
        } catch (err) {
            setError(err.message); // Keep general error for top display if needed
            setPageMessage({ text: err.message, type: 'error' });
            clearPageMessage();
        } finally {
            setIsSubmitting(false);
        }
    };

    if (authLoading || isLoadingInitial) {
        return <div className="p-4 flex justify-center items-center min-h-screen"><span className="loading loading-spinner loading-lg"></span></div>;
    }

    // if (!isAuthenticated) { // This is handled by fetchClassGroups setting an error message
    //     return <div className="p-4">{t('messages_error_loginRequired_viewClasses')}</div>;
    // }

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-semibold mb-6">{t('classes_heading')}</h1>

            {/* Display Page Messages */}
            {pageMessage.text && (
                <div role="alert" className={`alert ${pageMessage.type === 'success' ? 'alert-success' : 'alert-error'} mb-4 shadow-lg`}>
                    <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                        {pageMessage.type === 'success' ? (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        ) : (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        )}
                    </svg>
                    <span>{pageMessage.text}</span>
                </div>
            )}
            
            {/* General error for initial load if not authenticated, distinct from pageMessage */}
            {error && !isLoading && !classGroups.length && (
                 <div role="alert" className="alert alert-error mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    <span>{error}</span>
                </div>
            )}

            <div className="card bg-base-100 shadow-xl mb-6">
                <div className="card-body">
                    <div className="flex flex-col sm:flex-row items-center justify-between mb-4">
                        <h2 className="card-title text-xl mb-3 sm:mb-0">{t('classes_list_heading')}</h2>
                        <div className="flex items-center">
                            <button onClick={fetchClassGroups} className="btn btn-ghost btn-square btn-sm me-2" title={t('common_button_refreshList_title')} disabled={isLoading || isSubmitting}>
                                <ArrowPathIcon className="w-5 h-5" />
                            </button>
                            <button onClick={handleShowCreateForm} className="btn btn-primary btn-sm" disabled={isSubmitting}>
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 me-2">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                                </svg>
                                {t('classes_button_addNewClass')}
                            </button>
                        </div>
                    </div>

                    {isLoading && !isLoadingInitial && <div className="flex justify-center"><span className="loading loading-spinner loading-md"></span></div>}
                    {!isLoading && !error && classGroups.length === 0 && (
                        <p className="text-center py-4">{t('classes_list_status_noClassGroups')}</p>
                    )}
                    {!isLoading && !error && classGroups.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="table w-full">
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th className="cursor-pointer" onClick={() => handleSort('class_name')}>
                                            {t('classes_form_label_className')}
                                            {sortField === 'class_name' ? (
                                                sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1" /> : <ChevronDownIcon className="h-4 w-4 inline ml-1" />
                                            ) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400" />}
                                        </th>
                                        <th className="cursor-pointer" onClick={() => handleSort('academic_year')}>
                                            {t('classes_form_label_academicYear')}
                                            {sortField === 'academic_year' ? (
                                                sortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1" /> : <ChevronDownIcon className="h-4 w-4 inline ml-1" />
                                            ) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400" />}
                                        </th>
                                        <th>{t('classes_column_studentCount')}</th>
                                        <th>{t('common_label_actions')}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {isLoading ? (
                                        <tr><td colSpan="5" className="text-center"><span className="loading loading-dots loading-md"></span></td></tr>
                                    ) : !sortedClassGroups || sortedClassGroups.length === 0 ? (
                                        <tr><td colSpan="5" className="text-center py-4">{error ? error : t('messages_classes_noClasses')}</td></tr>
                                    ) : (
                                        sortedClassGroups.map((cg, index) => (
                                            <tr key={cg.id || index} className="hover">
                                                <td>{index + 1}</td>
                                                <td>{cg.class_name}</td>
                                                <td>{cg.academic_year || 'N/A'}</td>
                                                <td>{cg.student_ids ? cg.student_ids.length : 0}</td>
                                                <td className="space-x-2 whitespace-nowrap">
                                                    <button 
                                                        onClick={() => handleShowEditForm(cg)}
                                                        title={t('classes_list_button_edit_title')}
                                                        disabled={isSubmitting}
                                                        className="btn btn-ghost btn-xs p-1"
                                                    >
                                                        <PencilSquareIcon className="w-5 h-5" />
                                                    </button>
                                                    <button 
                                                        onClick={() => handleDelete(cg._id, cg.class_name)}
                                                        title={t('classes_list_button_delete_title')}
                                                        disabled={isSubmitting}
                                                        className="btn btn-ghost btn-xs p-1"
                                                    >
                                                        <TrashIcon className="w-5 h-5 text-red-500 hover:text-red-700" />
                                                    </button>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            {(showCreateModal || showEditModal) && (
                <dialog id="class_modal" className={`modal ${showCreateModal || showEditModal ? 'modal-open' : ''}`}>
                    <div className="modal-box w-11/12 max-w-lg">
                        <h3 className="font-bold text-lg mb-4">
                            {editingClassGroup 
                                ? `${t('classes_form_heading_editPrefix')} ${editingClassGroup.class_name}`
                                : t('classes_form_heading_create')}
                        </h3>
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label htmlFor="class_name" className="label">
                                    <span className="label-text">{t('classes_form_label_className')} <span className="text-error">{t('common_required_indicator')}</span></span>
                                </label>
                                <input 
                                    type="text" 
                                    id="class_name" 
                                    name="class_name" 
                                    value={formData.class_name} 
                                    onChange={handleInputChange} 
                                    required 
                                    disabled={isSubmitting}
                                    className="input input-bordered w-full"
                                />
                            </div>
                            <div>
                                <label htmlFor="academic_year" className="label">
                                   <span className="label-text">{t('classes_form_label_academicYear')}</span>
                                </label>
                                <input 
                                    type="text" 
                                    id="academic_year" 
                                    name="academic_year" 
                                    value={formData.academic_year} 
                                    onChange={handleInputChange} 
                                    placeholder={t('classes_form_placeholder_academicYear')} 
                                    disabled={isSubmitting}
                                    className="input input-bordered w-full"
                                />
                            </div>
                            
                            <div className="modal-action mt-6">
                                <button type="button" className="btn btn-ghost me-2" onClick={handleCloseModals} disabled={isSubmitting}>{t('common_button_cancel')}</button>
                                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                                    {isSubmitting 
                                        ? <span className="loading loading-spinner loading-xs"></span>
                                        : (editingClassGroup ? t('classes_form_button_update') : t('classes_form_button_save'))}
                                </button>
                            </div>
                        </form>
                    </div>
                    <form method="dialog" className="modal-backdrop">
                        <button onClick={handleCloseModals}>close</button>
                    </form>
                </dialog>
            )}
        </div>
    );
}

export default ClassesPage; 