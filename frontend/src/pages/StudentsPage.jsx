import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import {
  PencilSquareIcon,
  TrashIcon,
  PlusIcon,
  CheckCircleIcon,
  XCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function StudentsPage() {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading, getToken, user } = useKindeAuth();
  const navigate = useNavigate();
  
  const [students, setStudents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [classGroups, setClassGroups] = useState([]);
  const [isLoadingClasses, setIsLoadingClasses] = useState(false);
  const [classFetchError, setClassFetchError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [editingStudent, setEditingStudent] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [formError, setFormError] = useState(null);
  const [formSuccess, setFormSuccess] = useState(null);
  const [selectedClassGroupId, setSelectedClassGroupId] = useState('');
  const [initialClassGroupId, setInitialClassGroupId] = useState('');
  const [showCreateClassModal, setShowCreateClassModal] = useState(false);
  const [newClassName, setNewClassName] = useState('');
  const [newClassYear, setNewClassYear] = useState('');
  const [isCreatingClass, setIsCreatingClass] = useState(false);
  const [createClassError, setCreateClassError] = useState(null);

  const initialStudentData = {
    first_name: '',
    last_name: '',
    email: '',
    external_student_id: '',
    descriptor: '',
    year_group: ''
  };

  const [formData, setFormData] = useState(initialStudentData);

  const fetchStudents = useCallback(async () => {
    if (!isAuthenticated) {
      setStudents([]);
      setIsLoading(false);
      if (!isAuthLoading) {
        setError(t('messages_error_loginRequired_viewStudents'));
      }
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/students/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        let errorDetail = `HTTP error ${response.status}`;
        try {
          const errData = await response.json();
          errorDetail = errData.detail || errorDetail;
        } catch (e) {
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        throw new Error(t('messages_students_fetchError', { detail: errorDetail }));
      }

      const data = await response.json();
      console.log('API Response Data:', data);
      const processedData = data.map(student => ({
        ...student,
        id: student._id || student.id
      })).filter(student => student.id);
      setStudents(processedData);
    } catch (err) {
      console.error("Error fetching students:", err);
      setError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, isAuthLoading, getToken, t]);

  const fetchClassGroupsForDropdown = useCallback(async () => {
    if (!isAuthenticated) return [];
    
    setIsLoadingClasses(true);
    setClassFetchError(null);
    let fetchedClasses = [];

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${API_BASE_URL}/api/v1/classgroups/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) {
        throw new Error(t('messages_error_fetchFailed', { detail: `class groups: ${response.status}` }));
      }
      const data = await response.json();
      const processedClasses = data
        .map(cg => {
          if (!cg.id && cg._id) {
            return { ...cg, id: cg._id };
          }
          return cg;
        })
        .filter(cg => cg.id);
      setClassGroups(processedClasses);
      fetchedClasses = processedClasses;
    } catch (err) {
      setClassFetchError(err.message || t('messages_error_fetchFailed', { detail: "class groups" }));
      setClassGroups([]);
    } finally {
      setIsLoadingClasses(false);
    }
    return fetchedClasses;
  }, [isAuthenticated, getToken, t]);

  useEffect(() => {
    if (isAuthenticated) {
      console.log('isAuthenticated:', isAuthenticated);
      console.log('isLoading:', isLoading);
      console.log('error:', error);
      console.log('students.length:', students.length);
      fetchStudents();
      fetchClassGroupsForDropdown();
    }
  }, [isAuthenticated, fetchStudents, fetchClassGroupsForDropdown]);

  const resetForms = () => {
    setShowCreateForm(false);
    setShowEditForm(false);
    setEditingStudent(null);
    setFormData(initialStudentData);
    setFormError(null);
    setFormSuccess(null);
    setIsProcessing(false);
    setSelectedClassGroupId('');
    setInitialClassGroupId('');
    setShowCreateClassModal(false);
    setNewClassName('');
    setNewClassYear('');
    setIsCreatingClass(false);
    setCreateClassError(null);
  };

  const handleInputChange = (event) => {
    const { name, value } = event.target;
    setFormData(prevData => ({ ...prevData, [name]: value }));
    setFormError(null);
    setFormSuccess(null);
  };

  const handleClassChange = (event) => {
    const value = event.target.value;
    if (value === 'CREATE_NEW_CLASS') {
      setSelectedClassGroupId('');
      handleOpenCreateClassModal();
    } else {
      setSelectedClassGroupId(value);
    }
  };

  const handleOpenCreateClassModal = () => {
    setCreateClassError(null);
    setShowCreateClassModal(true);
  };

  const handleCloseCreateClassModal = () => {
    setShowCreateClassModal(false);
    setNewClassName('');
    setNewClassYear('');
    setIsCreatingClass(false);
    setCreateClassError(null);
    setSelectedClassGroupId(initialClassGroupId || '');
  };

  const handleCreateClassSubmit = async (event) => {
    event.preventDefault();
    if (!newClassName.trim() || !newClassYear.trim()) {
      setCreateClassError(t('messages_classes_modal_error_fieldsRequired'));
      return;
    }
    if (!isAuthenticated || !user?.id) {
      setCreateClassError(t('messages_classes_modal_error_missingTeacher'));
      return;
    }
    setIsCreatingClass(true);
    setCreateClassError(null);
    const payload = {
      class_name: newClassName.trim(),
      academic_year: newClassYear.trim(),
      teacher_id: user.id
    };
    let newClass = null;
    let token = null;
    let studentAssigned = false;
    const studentIdToAssign = editingStudent?.id;

    try {
      token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${API_BASE_URL}/api/v1/classgroups/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        let specificErrorMessage = null;

        try {
          const errData = await response.json();
          if (typeof errData.detail === 'string') {
            errorDetail = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map(e => `${e.loc.join('.')} - ${e.msg}`).join('; ');
          } else if (errData.detail) {
            errorDetail = `Server error: ${JSON.stringify(errData.detail)}`;
          } else if (errData.message) {
            errorDetail = errData.message;
          }
        } catch (e) {
          try {
            const textError = await response.text();
            errorDetail = textError || errorDetail;
          } catch (textErr) {}
        }

        if (response.status === 409) {
          specificErrorMessage = t('messages_error_conflict', { defaultValue: `Conflict detected. A class with this information might already exist. Detail: ${errorDetail}` });
        } else if (isCreatingClass && response.status === 404) {
          specificErrorMessage = t('messages_error_notFound', { item: 'Class', defaultValue: `Class not found. Detail: ${errorDetail}` });
        } else if (response.status === 422) {
          specificErrorMessage = t('messages_error_validation', { detail: errorDetail, defaultValue: `Validation error: ${errorDetail}` });
        } else {
          specificErrorMessage = t('messages_classes_modal_error_createFailed', { detail: errorDetail });
        }

        throw new Error(specificErrorMessage);
      }

      newClass = await response.json();
      if (!newClass.id && newClass._id) {
        newClass = { ...newClass, id: newClass._id };
      }

      if (studentIdToAssign) {
        const postUrl = `${API_BASE_URL}/api/v1/classgroups/${newClass.id}/students/${studentIdToAssign}`;
        const postResponse = await fetch(postUrl, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!postResponse.ok) {
          console.warn(`Failed to assign student to new class: ${postResponse.status}`);
        } else {
          studentAssigned = true;
        }
      }

      setClassGroups(prev => [...prev, newClass]);
      setSelectedClassGroupId(newClass.id);
      setFormSuccess(t('messages_classes_modal_success_created'));
      handleCloseCreateClassModal();
      await fetchStudents();
    } catch (err) {
      setCreateClassError(err.message || t('messages_classes_modal_error_unexpected'));
    } finally {
      setIsCreatingClass(false);
    }
  };

  const handleShowCreateForm = () => {
    resetForms();
    setShowCreateForm(true);
  };

  const handleShowEditForm = async (studentToEdit) => {
    resetForms();
    setEditingStudent(studentToEdit);
    setFormData({
      first_name: studentToEdit.first_name || '',
      last_name: studentToEdit.last_name || '',
      email: studentToEdit.email || '',
      external_student_id: studentToEdit.external_student_id || '',
      descriptor: studentToEdit.descriptor || '',
      year_group: studentToEdit.year_group || ''
    });
    const currentClassGroups = await fetchClassGroupsForDropdown();
    let foundClassId = '';
    if (Array.isArray(currentClassGroups)) {
      for (const cg of currentClassGroups) {
        if (cg.student_ids?.includes(studentToEdit.id)) {
          foundClassId = cg.id;
          break;
        }
      }
    }
    setSelectedClassGroupId(foundClassId);
    setInitialClassGroupId(foundClassId);
    setShowEditForm(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isAuthenticated || !user) {
      setFormError(t('messages_error_loginRequired_form'));
      return;
    }
    if (!formData.first_name || !formData.last_name) {
      setFormError(t('messages_students_form_fieldsRequired'));
      return;
    }
    setIsProcessing(true);
    setFormError(null);
    setFormSuccess(null);
    const isEditing = !!editingStudent;
    const studentIdForUrl = isEditing ? editingStudent?.id : null;
    const url = isEditing ? `${API_BASE_URL}/api/v1/students/${studentIdForUrl}` : `${API_BASE_URL}/api/v1/students/`;
    const method = isEditing ? 'PUT' : 'POST';
    const logAction = isEditing ? 'Updating' : 'Creating';
    let savedStudentId = null;
    let token = null;

    try {
      if (isEditing && !studentIdForUrl) {
        throw new Error(t('messages_students_form_missingStudentId'));
      }
      token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const payload = {};
      for (const key in formData) {
        if (formData[key] !== '' && formData[key] !== null) {
          payload[key] = formData[key];
        }
      }
      if (!payload.first_name) payload.first_name = formData.first_name;
      if (!payload.last_name) payload.last_name = formData.last_name;
      if (!isEditing && user?.id) {
        payload.teacher_id = user.id;
      }
      const response = await fetch(url, {
        method: method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        let specificErrorMessage = null;

        try {
          const errData = await response.json();
          if (typeof errData.detail === 'string') {
            errorDetail = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map(e => `${e.loc.join('.')} - ${e.msg}`).join('; ');
          } else if (errData.detail) {
            errorDetail = `Server error: ${JSON.stringify(errData.detail)}`;
          } else if (errData.message) {
            errorDetail = errData.message;
          }
        } catch (e) {
          try {
            const textError = await response.text();
            errorDetail = textError || errorDetail;
          } catch (textErr) {}
        }

        if (response.status === 409) {
          specificErrorMessage = t('messages_error_conflict', { defaultValue: `Conflict detected. A student with this information might already exist. Detail: ${errorDetail}` });
        } else if (isEditing && response.status === 404) {
          specificErrorMessage = t('messages_error_notFound', { item: 'Student', defaultValue: `Student not found. Detail: ${errorDetail}` });
        } else if (response.status === 422) {
          specificErrorMessage = t('messages_error_validation', { detail: errorDetail, defaultValue: `Validation error: ${errorDetail}` });
        } else {
          specificErrorMessage = t('messages_students_form_error_failed', { action: logAction.toLowerCase(), detail: errorDetail, defaultValue: `Failed to ${logAction.toLowerCase()} student. Detail: ${errorDetail}` });
        }

        throw new Error(specificErrorMessage);
      }
      const resultData = await response.json();
      savedStudentId = resultData.id || resultData._id;
      if (!savedStudentId) {
        throw new Error(t('messages_error_actionFailed', { action: logAction, detail: 'missing ID' }));
      }
      
      if (selectedClassGroupId !== initialClassGroupId) {
        // Remove from old class if necessary
        if (initialClassGroupId) {
          const deleteUrl = `${API_BASE_URL}/api/v1/classgroups/${initialClassGroupId}/students/${savedStudentId}`;
          try {
            const deleteResponse = await fetch(deleteUrl, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!deleteResponse.ok && deleteResponse.status !== 404) {
              console.warn(`[handleSubmit] Failed to remove student from previous class ${initialClassGroupId}: ${deleteResponse.status}`);
            }
          } catch (deleteErr) {
            console.warn(`[handleSubmit] Error during fetch to remove student from old class ${initialClassGroupId}: ${deleteErr}`);
          }
        }
        // Add to new class if necessary
        if (selectedClassGroupId) {
          const postUrl = `${API_BASE_URL}/api/v1/classgroups/${selectedClassGroupId}/students/${savedStudentId}`;
          try {
            const postResponse = await fetch(postUrl, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!postResponse.ok) {
              let postErrorDetail = `HTTP ${postResponse.status}`;
              try {
                const errData = await postResponse.json();
                postErrorDetail = errData.detail || JSON.stringify(errData);
              } catch (e) {
                try {
                  postErrorDetail = await postResponse.text() || postErrorDetail;
                } catch (e2) {}
              }
              console.warn(`[handleSubmit] Failed to add student to new class ${selectedClassGroupId}: ${postErrorDetail}`);
            }
          } catch (postErr) {
            console.warn(`[handleSubmit] Error during fetch to add student to new class ${selectedClassGroupId}: ${postErr}`);
          }
        }
      }

      setFormSuccess(t('messages_students_form_success', { action: logAction.toLowerCase() }));
      await fetchStudents();
      await fetchClassGroupsForDropdown();
      resetForms();
    } catch (err) {
      setFormError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDelete = async (studentId, studentName) => {
    if (!isAuthenticated) {
      setFormError(t('messages_error_loginRequired_delete'));
      return;
    }
    if (!window.confirm(t('messages_students_delete_confirm', { name: studentName }))) {
      return;
    }
    setIsProcessing(true);
    setFormError(null);
    setFormSuccess(null);
    let token = null;

    try {
      token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      let classToRemoveFrom = null;
      if (Array.isArray(classGroups)) {
        for (const cg of classGroups) {
          if (cg.student_ids?.includes(studentId)) {
            classToRemoveFrom = cg.id;
            break;
          }
        }
      }
      if (classToRemoveFrom) {
        const deleteUrl = `${API_BASE_URL}/api/v1/classgroups/${classToRemoveFrom}/students/${studentId}`;
        const deleteResponse = await fetch(deleteUrl, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!deleteResponse.ok && deleteResponse.status !== 404) {
          console.warn(`Failed to remove student from class ${classToRemoveFrom} before deleting: ${deleteResponse.status}`);
        }
      }
      const response = await fetch(`${API_BASE_URL}/api/v1/students/${studentId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok || response.status === 204) {
        setFormSuccess(t('messages_students_delete_success'));
        fetchStudents();
        fetchClassGroupsForDropdown();
        setTimeout(() => setFormSuccess(null), 3000);
      } else {
        let errorDetail = `HTTP ${response.status}`;
        try {
          const errData = await response.json();
          errorDetail = errData.detail || errorDetail;
        } catch (e) {
          const textError = await response.text();
          errorDetail = textError || errorDetail;
        }
        throw new Error(t('messages_students_delete_error', { detail: errorDetail }));
      }
    } catch (err) {
      setFormError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-semibold text-base-content">{t('studentsPage_heading')}</h1>
      </div>

      <div className="space-y-6">
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
                ? `${t('students_form_heading_editPrefix')} ${editingStudent?.first_name} ${editingStudent?.last_name}`
                : t('students_form_heading_create')}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="form-control w-full">
                  <label className="label" htmlFor="first_name">
                    <span className="label-text text-sm">
                      {t('students_form_label_firstName')} <span className="text-error">{t('common_required_indicator')}</span>
                    </span>
                  </label>
                  <input
                    type="text"
                    name="first_name"
                    id="first_name"
                    required
                    value={formData.first_name}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
                <div className="form-control w-full">
                  <label className="label" htmlFor="last_name">
                    <span className="label-text text-sm">
                      {t('students_form_label_lastName')} <span className="text-error">{t('common_required_indicator')}</span>
                    </span>
                  </label>
                  <input
                    type="text"
                    name="last_name"
                    id="last_name"
                    required
                    value={formData.last_name}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
                <div className="form-control w-full">
                  <label className="label" htmlFor="email">
                    <span className="label-text text-sm">{t('students_form_label_email')}</span>
                  </label>
                  <input
                    type="email"
                    name="email"
                    id="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
                <div className="form-control w-full">
                  <label className="label" htmlFor="external_student_id">
                    <span className="label-text text-sm">{t('students_form_label_externalId')}</span>
                  </label>
                  <input
                    type="text"
                    name="external_student_id"
                    id="external_student_id"
                    value={formData.external_student_id}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
                <div className="form-control w-full">
                  <label className="label" htmlFor="descriptor">
                    <span className="label-text text-sm">{t('students_form_label_descriptor')}</span>
                  </label>
                  <input
                    type="text"
                    name="descriptor"
                    id="descriptor"
                    value={formData.descriptor}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
                <div className="form-control w-full">
                  <label className="label" htmlFor="year_group">
                    <span className="label-text text-sm">{t('students_form_label_yearGroup')}</span>
                  </label>
                  <input
                    type="text"
                    name="year_group"
                    id="year_group"
                    value={formData.year_group}
                    onChange={handleInputChange}
                    className="input input-bordered w-full"
                  />
                </div>
              </div>

              <div className="form-control w-full">
                <label className="label" htmlFor="class_group">
                  <span className="label-text text-sm">{t('students_form_label_classGroup')}</span>
                </label>
                <select
                  name="class_group"
                  id="class_group"
                  value={selectedClassGroupId}
                  onChange={handleClassChange}
                  className="select select-bordered w-full"
                >
                  <option value="">{t('students_form_select_noClass')}</option>
                  {classGroups.map((classGroup) => (
                    <option key={classGroup.id} value={classGroup.id}>
                      {classGroup.class_name} ({classGroup.academic_year})
                    </option>
                  ))}
                  <option value="CREATE_NEW_CLASS" className="font-semibold text-secondary">
                    {t('students_form_select_createNewClass')}
                  </option>
                </select>
              </div>

              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={resetForms} className="btn btn-ghost btn-sm">
                  {t('common_button_cancel')}
                </button>
                <button type="submit" disabled={isProcessing} className="btn btn-primary btn-sm">
                  {isProcessing ? (
                    <><span className="loading loading-spinner loading-xs"></span>{t('common_status_saving')}</>
                  ) : (
                    showEditForm ? t('students_form_button_update') : t('students_form_button_save')
                  )}
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="mt-4">
          {isLoading && (
            <div className="flex justify-center py-4">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          )}
        </div>

        {!isLoading && !error && (
          <div className="card w-full bg-base-100 shadow-md">
            <div className="card-body">
              <div className="flex justify-between items-center mb-4">
                <h2 className="card-title text-xl">{t('students_list_heading', { defaultValue: 'Student List'})}</h2>
                <button
                  onClick={handleShowCreateForm}
                  className="btn btn-success btn-sm"
                >
                  <PlusIcon className="h-5 w-5 mr-1"/>
                  {t('studentsPage_button_add')}
                </button>
              </div>
              {students.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="table w-full">
                    <thead>
                      <tr>
                        <th>{t('common_label_name')}</th>
                        <th>{t('common_label_email')}</th>
                        <th>{t('common_label_yearGroup')}</th>
                        <th>{t('common_label_actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {students.map((student) => (
                        <tr key={student.id} className="hover">
                          <td className="font-medium">
                            {student.first_name} {student.last_name}
                          </td>
                          <td>{student.email || '-'}</td>
                          <td>{student.year_group || '-'}</td>
                          <td className="space-x-2">
                            <button
                              onClick={() => handleShowEditForm(student)}
                              className="btn btn-ghost btn-xs"
                              title={t('students_button_edit_title')}
                            >
                              <PencilSquareIcon className="h-4 w-4"/> {t('common_button_edit')}
                            </button>
                            <button
                              onClick={() => handleDelete(student.id, `${student.first_name} ${student.last_name}`)}
                              className="btn btn-ghost btn-xs text-error"
                              title={t('students_button_delete_title')}
                            >
                              <TrashIcon className="h-4 w-4"/> {t('common_button_delete')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-base-content/70">{t('students_list_empty')}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Create Class Modal */}
      {showCreateClassModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-base-100 p-6 rounded-lg shadow-xl max-w-md w-full">
            <h3 className="text-lg font-medium mb-4">{t('classes_modal_heading_create')}</h3>
            {createClassError && (
              <div className="alert alert-error mb-4">
                <XCircleIcon className="h-6 w-6"/>
                <span>{t('common_error_prefix')} {createClassError}</span>
              </div>
            )}
            <form onSubmit={handleCreateClassSubmit} className="space-y-4">
              <div className="form-control">
                <label className="label" htmlFor="newClassName">
                  <span className="label-text text-sm">
                    {t('classes_modal_label_name')} <span className="text-error">{t('common_required_indicator')}</span>
                  </span>
                </label>
                <input
                  type="text"
                  id="newClassName"
                  value={newClassName}
                  onChange={(e) => setNewClassName(e.target.value)}
                  className="input input-bordered w-full"
                  required
                />
              </div>
              <div className="form-control">
                <label className="label" htmlFor="newClassYear">
                  <span className="label-text text-sm">
                    {t('classes_modal_label_year')} <span className="text-error">{t('common_required_indicator')}</span>
                  </span>
                </label>
                <input
                  type="text"
                  id="newClassYear"
                  value={newClassYear}
                  onChange={(e) => setNewClassYear(e.target.value)}
                  className="input input-bordered w-full"
                  required
                />
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={handleCloseCreateClassModal}
                  className="btn btn-ghost btn-sm"
                  disabled={isCreatingClass}
                >
                  {t('common_button_cancel')}
                </button>
                <button
                  type="submit"
                  className="btn btn-primary btn-sm"
                  disabled={isCreatingClass}
                >
                  {isCreatingClass ? (
                    <><span className="loading loading-spinner loading-xs"></span>{t('common_status_saving')}</>
                  ) : (
                    t('classes_modal_button_create')
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default StudentsPage; 