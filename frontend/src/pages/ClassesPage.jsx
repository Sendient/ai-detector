import React, { useState, useEffect, useCallback } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
// import { toast } from 'sonner'; // Removed sonner
import {
    PencilSquareIcon,
    TrashIcon,
    EyeIcon,
    ArrowPathIcon // Assuming this is for the refresh button, keep if used elsewhere
} from '@heroicons/react/24/outline';

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

    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    const clearPageMessage = () => setTimeout(() => setPageMessage({ text: '', type: '' }), 5000);

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
        setIsLoading(true);
        setPageMessage({ text: '', type: '' }); // Clear previous messages
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
            const response = await fetch(`${API_URL}/api/v1/class-groups`, {
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
            setError(err.message);
            setPageMessage({ text: err.message, type: 'error' });
            clearPageMessage();
            setClassGroups([]);
        } finally {
            setIsLoading(false);
            setIsLoadingInitial(false);
        }
    }, [API_URL, getToken, isAuthenticated, authLoading, t]);

    useEffect(() => {
        fetchClassGroups();
    }, [fetchClassGroups]);

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
            ? `${API_URL}/api/v1/class-groups/${editingClassGroup.id}`
            : `${API_URL}/api/v1/class-groups`;

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
            const response = await fetch(`${API_URL}/api/v1/class-groups/${classId}`, {
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
                                <thead className="bg-base-200">
                                    <tr>
                                        <th>{t('common_label_className')}</th>
                                        <th>{t('common_label_academicYear')}</th>
                                        <th>{t('common_label_studentsCount')}</th>
                                        <th>{t('common_label_actions')}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {classGroups.map(cg => {
                                        console.log(`Rendering row for class: ${cg.class_name}, ID: ${cg._id}, Type: ${typeof cg._id}`); 
                                        return (
                                            <tr key={cg._id} className="hover">
                                                <td>{cg.class_name}</td>
                                                <td>{cg.academic_year || t('common_text_notApplicable')}</td>
                                                <td>{cg.student_ids ? cg.student_ids.length : (cg.student_count !== undefined ? cg.student_count : t('common_text_notApplicable' ))}</td>
                                                <td className="text-right">
                                                    <div className="flex justify-end space-x-1">
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
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
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