import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import {
  ArrowPathIcon,
  PencilSquareIcon,
  TrashIcon,
  PlusIcon,
  CheckCircleIcon,
  XCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';

function ClassesPage() {
  const { t } = useTranslation();
  const { user, isAuthenticated, isLoading: isAuthLoading, getToken } = useKindeAuth();
  const navigate = useNavigate();
  const [classGroups, setClassGroups] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [editingClassGroup, setEditingClassGroup] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [formError, setFormError] = useState(null);
  const [formSuccess, setFormSuccess] = useState(null);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  const fetchClassGroups = useCallback(async () => {
    if (isAuthenticated) {
      setError(null);
      setIsLoading(true);
      try {
        const token = await getToken();
        if (!token) throw new Error(t('messages_error_authTokenMissing'));
        const response = await fetch(`${API_BASE_URL}/api/v1/classgroups/`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
          let errorDetail = `HTTP error ${response.status}`;
          try {
            const errData = await response.json();
            errorDetail = errData.detail || errorDetail;
          } catch (e) { /* Ignore */ }
          throw new Error(errorDetail);
        }
        const data = await response.json();
        const mappedData = data.map(cg => ({ ...cg, id: cg._id || cg.id })).filter(cg => cg.id);
        setClassGroups(mappedData);
      } catch (err) {
        console.error("Error fetching class groups:", err);
        setError(t('messages_classes_fetchError', { message: err.message || t('messages_error_unexpected')}));
      } finally {
        setIsLoading(false);
      }
    } else {
      setClassGroups([]);
      setIsLoading(false);
      if (!isAuthLoading) {
        setError(t('messages_error_loginRequired_viewClasses'));
      }
    }
  }, [isAuthenticated, isAuthLoading, getToken, t]);

  useEffect(() => {
    if (isAuthenticated && !isAuthLoading) {
      fetchClassGroups();
    }
  }, [isAuthenticated, isAuthLoading, fetchClassGroups]);

  const resetForms = () => {
    setShowCreateForm(false);
    setShowEditForm(false);
    setEditingClassGroup(null);
    setFormError(null);
    setFormSuccess(null);
    setIsProcessing(false);
  };

  const handleInputChange = (event) => {
    const { name, value } = event.target;
    setFormData(prevData => ({ ...prevData, [name]: value }));
    setFormError(null);
    setFormSuccess(null);
  };

  const handleShowCreateForm = async () => {
    resetForms();
    const schoolId = user?.school_id;
    if (!user || !schoolId) {
      setFormError(t('messages_classes_create_error_missingProfile'));
      return;
    }
    setFormData(prev => ({
      ...prev,
      school_id: schoolId,
      teacher_id: user?.id || ''
    }));
    setShowCreateForm(true);
  };

  const handleShowEditForm = (classGroupToEdit) => {
    resetForms();
    setEditingClassGroup(classGroupToEdit);
    setFormData({
      class_name: classGroupToEdit.class_name || '',
      academic_year: classGroupToEdit.academic_year || '',
      school_id: classGroupToEdit.school_id,
      teacher_id: classGroupToEdit.teacher_id,
    });
    setShowEditForm(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isAuthenticated) {
      setFormError(t('messages_error_loginRequired_form'));
      return;
    }
    if (!formData.class_name || !formData.academic_year) {
      setFormError(t('messages_classes_form_fieldsRequired'));
      return;
    }
    if (!formData.school_id) {
      setFormError(t('messages_classes_form_missingSchoolId'));
      return;
    }

    setIsProcessing(true);
    setFormError(null);
    setFormSuccess(null);

    const isEditing = !!editingClassGroup;
    const classIdForUrl = isEditing ? editingClassGroup?.id : null;
    const url = isEditing ? `${API_BASE_URL}/api/v1/classgroups/${classIdForUrl}` : `${API_BASE_URL}/api/v1/classgroups/`;
    const method = isEditing ? 'PUT' : 'POST';
    const logAction = isEditing ? 'Updating' : 'Creating';
    const payload = { ...formData };

    if (!isEditing) {
      delete payload.teacher_id;
    }

    if (!payload.school_id) {
      setFormError(t('messages_classes_form_internalMissingSchoolId'));
      setIsProcessing(false);
      return;
    }

    try {
      if (isEditing && !classIdForUrl) {
        throw new Error(t('messages_classes_form_missingClassId'));
      }
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(url, {
        method: method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let errorDetail = `HTTP error ${response.status}`;
        try {
          const errData = await response.json();
          if (typeof errData.detail === 'string') {
            errorDetail = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map(e => `${e.loc.join('.')} - ${e.msg}`).join('; ');
          } else {
            errorDetail = `Server error: ${JSON.stringify(errData.detail || errData)}`;
          }
        } catch (e) {
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        if (response.status === 404 && isEditing) errorDetail = t('messages_error_notFound', { item: 'Class group' });
        if (response.status === 422) errorDetail = t('messages_error_validation', { detail: errorDetail });
        throw new Error(errorDetail);
      }

      const resultData = await response.json();
      console.log(`[ClassesPage] Class group ${logAction} successful:`, resultData);
      setFormSuccess(isEditing ? t('messages_classes_form_updateSuccess') : t('messages_classes_form_createSuccess'));
      resetForms();
      fetchClassGroups();
      setTimeout(() => setFormSuccess(null), 3000);
    } catch (err) {
      console.error(`Error ${logAction.toLowerCase()} class group:`, err);
      setFormError(err.message || t('messages_error_actionFailed', {
        action: logAction.toLowerCase(),
        detail: t('messages_error_unexpected')
      }));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDelete = async (classId, className) => {
    if (!isAuthenticated) {
      setError(t('messages_classes_delete_error_loginRequired'));
      return;
    }
    if (!window.confirm(t('messages_classes_delete_confirm', { className: className, classId: classId }))) {
      return;
    }
    setIsProcessing(true);
    setError(null);
    setFormSuccess(null);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/classgroups/${classId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok || response.status === 204) {
        setFormSuccess(t('messages_classes_delete_success'));
        fetchClassGroups();
        setTimeout(() => setFormSuccess(null), 3000);
      } else {
        let errorDetail = `HTTP error ${response.status}`;
        try {
          const errData = await response.json();
          errorDetail = errData.detail || errorDetail;
        } catch (e) {
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        if (response.status === 404) errorDetail = t('messages_error_notFound', { item: 'Class group' });
        throw new Error(t('messages_classes_delete_failed', { message: errorDetail }));
      }
    } catch (err) {
      console.error(`Error deleting class group ${classId}:`, err);
      setError(t('messages_classes_delete_failed', { message: err.message }));
      setTimeout(() => setError(null), 5000);
    } finally {
      setIsProcessing(false);
    }
  };

  const initialClassData = { class_name: '', academic_year: '', school_id: '', teacher_id: '' };
  const [formData, setFormData] = useState(initialClassData);

  if (!isAuthenticated && !isAuthLoading) {
    return <div className="alert alert-info shadow-lg">
      <div>
        <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0"/>
        <span>Please log in to view classes.</span>
      </div>
    </div>;
  }

  if (isLoading || isAuthLoading) {
    return <div className="flex items-center justify-center min-h-screen">
      <div className="loading loading-spinner loading-lg"></div>
    </div>;
  }

  if (error) {
    return <div className="alert alert-error shadow-lg">
      <div>
        <ExclamationTriangleIcon className="h-6 w-6 stroke-current shrink-0"/>
        <span>{error}</span>
      </div>
    </div>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold text-base-content">{t('classes_heading')}</h1>

      <div className="card bg-base-100 shadow-md border border-base-300">
        <div className="card-body">
          <div className="card-actions justify-between items-center mb-4">
            <h2 className="text-xl font-medium">{t('classes_list_heading')}</h2>
            <div className="flex items-center space-x-2">
              <button
                onClick={fetchClassGroups}
                disabled={isLoading || isProcessing}
                className="btn btn-ghost btn-square btn-sm"
                title={t('common_button_refreshList_title')}
              >
                <ArrowPathIcon className="h-5 w-5"/>
              </button>
              {!showCreateForm && !showEditForm && (
                <button
                  onClick={handleShowCreateForm}
                  disabled={isProcessing}
                  className="btn btn-success btn-sm"
                >
                  <PlusIcon className="h-4 w-4 mr-1"/> {t('classes_button_addNewClass')}
                </button>
              )}
            </div>
          </div>

          {formSuccess && (
            <div className="alert alert-success mb-4">
              <CheckCircleIcon className="h-6 w-6"/>
              <span>{formSuccess}</span>
            </div>
          )}

          {formError && (showCreateForm || showEditForm) && (
            <div className="alert alert-error mb-4">
              <XCircleIcon className="h-6 w-6"/>
              <span>{t('common_error_prefix')} {formError}</span>
            </div>
          )}

          {(showCreateForm || showEditForm) && (
            <div className="mb-6 p-4 border border-base-300 rounded-md bg-base-200">
              <h3 className="text-lg font-medium mb-3">
                {showEditForm
                  ? `${t('classes_form_heading_editPrefix')} ${editingClassGroup?.class_name}`
                  : t('classes_form_heading_create')}
              </h3>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="form-control w-full">
                    <label className="label" htmlFor="class_name">
                      <span className="label-text text-sm">
                        {t('classes_form_label_className')} <span className="text-error">{t('common_required_indicator')}</span>
                      </span>
                    </label>
                    <input
                      type="text"
                      name="class_name"
                      id="class_name"
                      required
                      value={formData.class_name}
                      onChange={handleInputChange}
                      className="input input-bordered w-full"
                    />
                  </div>
                  <div className="form-control w-full">
                    <label className="label" htmlFor="academic_year">
                      <span className="label-text text-sm">
                        {t('classes_form_label_academicYear')} <span className="text-error">{t('common_required_indicator')}</span>
                      </span>
                    </label>
                    <input
                      type="text"
                      name="academic_year"
                      id="academic_year"
                      required
                      value={formData.academic_year}
                      onChange={handleInputChange}
                      placeholder={t('classes_form_placeholder_academicYear')}
                      className="input input-bordered w-full"
                    />
                  </div>
                </div>
                <div className="text-xs text-base-content/70 mt-2">
                  {t('classes_form_label_schoolId')} {formData.school_id || t('common_text_notApplicable')} |{' '}
                  {t('classes_form_label_teacherId')} {formData.teacher_id || t('common_text_notApplicable')}
                  {showEditForm && ` (${t('classes_form_label_notEditable')})`}
                </div>
                <div className="flex justify-end space-x-3 pt-2">
                  <button
                    type="button"
                    onClick={resetForms}
                    disabled={isProcessing}
                    className="btn btn-ghost btn-sm"
                  >
                    {t('common_button_cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={isProcessing}
                    className="btn btn-primary btn-sm"
                  >
                    {isProcessing ? (
                      <><span className="loading loading-spinner loading-xs"></span>{t('common_status_saving')}</>
                    ) : (
                      showEditForm ? t('classes_form_button_update') : t('classes_form_button_save')
                    )}
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="mt-4">
            {isLoading && (
              <div className="flex items-center justify-center py-4">
                <span className="loading loading-lg loading-spinner text-primary"></span>
              </div>
            )}
            {!isLoading && !error && classGroups.length > 0 && (
              <div className="overflow-x-auto">
                <table className="table w-full">
                  <thead>
                    <tr>
                      <th className="text-sm font-semibold">{t('common_label_className')}</th>
                      <th className="text-sm font-semibold">{t('common_label_academicYear')}</th>
                      <th className="text-sm font-semibold">{t('common_label_studentsCount')}</th>
                      <th className="text-sm font-semibold">{t('common_label_actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classGroups.map((cg) => (
                      <tr key={cg.id} className="hover">
                        <td className="text-sm font-medium">{cg.class_name}</td>
                        <td className="text-sm">{cg.academic_year || t('common_text_notApplicable')}</td>
                        <td className="text-sm">{cg.student_ids?.length ?? 0}</td>
                        <td className="space-x-1">
                          <button
                            onClick={() => handleShowEditForm(cg)}
                            disabled={isProcessing || showCreateForm || showEditForm}
                            title={t('classes_list_button_edit_title')}
                            className="btn btn-ghost btn-xs text-info"
                          >
                            <PencilSquareIcon className="h-4 w-4 mr-1"/> {t('common_button_edit')}
                          </button>
                          <button
                            onClick={() => handleDelete(cg.id, cg.class_name)}
                            disabled={isProcessing || showCreateForm || showEditForm}
                            title={t('classes_list_button_delete_title')}
                            className="btn btn-ghost btn-xs text-error"
                          >
                            <TrashIcon className="h-4 w-4 mr-1"/> {t('common_button_delete')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!isLoading && !error && classGroups.length === 0 && (
              <p className="text-base-content/70 text-center py-4">{t('classes_list_status_noClassGroups')}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ClassesPage; 