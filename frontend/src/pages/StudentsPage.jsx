import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
  ArrowUpTrayIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { ChevronUpIcon, ChevronDownIcon, ArrowsUpDownIcon } from '@heroicons/react/20/solid';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function StudentsPage() {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading: isAuthLoading, getToken, user } = useKindeAuth();
  const navigate = useNavigate();
  const location = useLocation();
  
  const [students, setStudents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [classGroups, setClassGroups] = useState([]);
  const [isLoadingClasses, setIsLoadingClasses] = useState(false);
  const [classFetchError, setClassFetchError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [editingStudent, setEditingStudent] = useState(null);
  const [assignedClassesForEdit, setAssignedClassesForEdit] = useState([]);
  const [availableClassesForAdding, setAvailableClassesForAdding] = useState([]);
  const [classToAddId, setClassToAddId] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isClassMembershipProcessing, setIsClassMembershipProcessing] = useState(false);
  const [formError, setFormError] = useState(null);
  const [formSuccess, setFormSuccess] = useState(null);
  const [selectedClassGroupId, setSelectedClassGroupId] = useState('');
  const [initialClassGroupId, setInitialClassGroupId] = useState('');
  const [showCreateClassModal, setShowCreateClassModal] = useState(false);
  const [newClassName, setNewClassName] = useState('');
  const [newClassYear, setNewClassYear] = useState('');
  const [isCreatingClass, setIsCreatingClass] = useState(false);
  const [createClassError, setCreateClassError] = useState(null);
  const [tempPreviousClassToAddId, setTempPreviousClassToAddId] = useState('');

  // Sorting state for students table
  const [studentSortField, setStudentSortField] = useState('last_name'); // Default: last_name
  const [studentSortOrder, setStudentSortOrder] = useState('asc'); // Default: asc

  // New state for student documents
  const [studentDocuments, setStudentDocuments] = useState([]);
  const [isLoadingStudentDocuments, setIsLoadingStudentDocuments] = useState(false);
  const [studentDocumentsError, setStudentDocumentsError] = useState(null);

  const initialStudentData = {
    first_name: '',
    last_name: '',
    email: '',
    external_student_id: '',
    descriptor: '',
    year_group: ''
  };

  const [formData, setFormData] = useState(initialStudentData);

  const handleStudentSort = (field) => {
    if (studentSortField === field) {
      setStudentSortOrder(studentSortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setStudentSortField(field);
      setStudentSortOrder('asc'); // Default to ascending for new fields
    }
  };

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
      const response = await fetch(`${API_BASE_URL}/api/v1/class-groups`, {
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

  const fetchStudentDocuments = useCallback(async (currentStudentId) => {
    if (!isAuthenticated || !currentStudentId) {
        setStudentDocuments([]);
        setStudentDocumentsError(null); // Clear previous errors
        setIsLoadingStudentDocuments(false); // Ensure loading is stopped
        return;
    }
    setIsLoadingStudentDocuments(true);
    setStudentDocumentsError(null);
    try {
        const token = await getToken();
        if (!token) throw new Error(t('messages_error_authTokenMissing'));

        // Ensure API_BASE_URL is defined, fallback if necessary.
        const baseUrl = API_BASE_URL || 'http://localhost:8000';
        const response = await fetch(`${baseUrl}/api/v1/documents/?student_id=${currentStudentId}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            // Use a more generic error message if detail is not specific
            const detail = (typeof errorData.detail === 'string' && errorData.detail) ? errorData.detail : response.statusText;
            throw new Error(t('messages_students_documents_fetchError', { studentName: editingStudent?.first_name || 'student', detail }));
        }
        const data = await response.json();
        // console.log('Student Documents API Response:', data); // Removed console.log
        setStudentDocuments(data || []);
    } catch (err) {
        console.error("Error fetching student documents:", err);
        setStudentDocumentsError(err.message || t('messages_error_unexpected'));
        setStudentDocuments([]);
    } finally {
        setIsLoadingStudentDocuments(false);
    }
  }, [isAuthenticated, getToken, t, API_BASE_URL, editingStudent]); // Added editingStudent to deps for the error message

  useEffect(() => {
    if (isAuthenticated) {
      // Fetch class groups first
      fetchClassGroupsForDropdown().then(fetchedClassGroups => {
        // Then fetch students
        fetchStudents().then(() => {
          // Then, if studentToEdit is in location state, show the edit form
          // Pass the fetchedClassGroups directly because the state might not have updated yet
          if (location.state?.studentToEdit) {
            const studentToEditWithId = {
              ...location.state.studentToEdit,
              id: location.state.studentToEdit._id || location.state.studentToEdit.id
            };
            handleShowEditForm(studentToEditWithId, fetchedClassGroups); 
          }
        });
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, user, location.state]); // Removed fetchStudents, fetchClassGroupsForDropdown from deps as they are stable

  const resetForms = () => {
    setShowCreateForm(false);
    setShowEditForm(false);
    setEditingStudent(null);
    setAssignedClassesForEdit([]);
    setAvailableClassesForAdding([]);
    setClassToAddId('');
    setFormData(initialStudentData);
    setFormError(null);
    setFormSuccess(null);
    setIsProcessing(false);
    setIsClassMembershipProcessing(false);
    setSelectedClassGroupId('');
    setInitialClassGroupId('');
    setShowCreateClassModal(false);
    setNewClassName('');
    setNewClassYear('');
    setIsCreatingClass(false);
    setCreateClassError(null);
    setTempPreviousClassToAddId('');
    // Reset student documents state
    setStudentDocuments([]);
    setIsLoadingStudentDocuments(false);
    setStudentDocumentsError(null);
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
    setInitialClassGroupId('');

    setClassToAddId(tempPreviousClassToAddId || '');
    setTempPreviousClassToAddId('');
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

      const updatedClassGroupsLocally = classGroups.find(cg => cg.id === newClass.id)
        ? classGroups.map(cg => cg.id === newClass.id ? (studentIdToAssign && studentAssigned ? {...newClass, student_ids: Array.from(new Set([...(cg.student_ids || []), studentIdToAssign]))} : newClass) : cg)
        : [...classGroups, (studentIdToAssign && studentAssigned ? {...newClass, student_ids: [studentIdToAssign]} : newClass)];
      setClassGroups(updatedClassGroupsLocally);
      
      if (editingStudent && studentIdToAssign && studentAssigned) {
        setAssignedClassesForEdit(prevAssigned => {
          if (!prevAssigned.find(cg => cg.id === newClass.id)) {
            return [...prevAssigned, newClass];
          }
          return prevAssigned;
        });
        setAvailableClassesForAdding(prevAvailable => prevAvailable.filter(cg => cg.id !== newClass.id));
        setFormSuccess(t('messages_students_class_assignSuccessOnCreate', { studentName: `${editingStudent.first_name} ${editingStudent.last_name}`, className: newClass.class_name }) || `Assigned ${editingStudent.first_name} to new class ${newClass.class_name}`);
      } else {
        if (editingStudent) {
          setAvailableClassesForAdding(prevAvailable => {
            if (!prevAvailable.find(cg => cg.id === newClass.id) && newClass) { 
              return [...prevAvailable, newClass];
            }
            return prevAvailable;
          });
        } else {
          setSelectedClassGroupId(newClass.id);
        }
        setFormSuccess(t('messages_classes_modal_success_created', {className: newClass.class_name}) || `Class ${newClass.class_name} created.`);
      }

      setClassToAddId('');
      setTempPreviousClassToAddId('');
      
      handleCloseCreateClassModal();

      await fetchClassGroupsForDropdown();
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

  const handleShowEditForm = async (studentToEdit, allClassGroups = classGroups) => {
    if (!studentToEdit || !studentToEdit.id) {
      setError(t('messages_students_error_cannotLoadForEdit'));
      setFormError(t('messages_students_error_cannotLoadForEdit'));
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    setIsProcessing(false);
    setIsClassMembershipProcessing(false);

    const currentClassGroups = allClassGroups && allClassGroups.length > 0 ? allClassGroups : classGroups;

    if (!currentClassGroups || currentClassGroups.length === 0) {
        console.warn("handleShowEditForm called when classGroups might not be fully loaded.");
    }

    setEditingStudent(studentToEdit);
    setFormData({
      first_name: studentToEdit.first_name || '',
      last_name: studentToEdit.last_name || '',
      email: studentToEdit.email || '',
      external_student_id: studentToEdit.external_student_id || '',
      descriptor: studentToEdit.descriptor || '',
      year_group: studentToEdit.year_group || ''
    });

    const assigned = currentClassGroups.filter(cg => 
        cg.student_ids && cg.student_ids.includes(studentToEdit.id)
    );
    setAssignedClassesForEdit(assigned);

    const available = currentClassGroups.filter(cg => 
        !cg.student_ids || !cg.student_ids.includes(studentToEdit.id)
    );
    setAvailableClassesForAdding(available);
    setClassToAddId('');

    // Fetch documents for this student
    if (studentToEdit && studentToEdit.id) {
      fetchStudentDocuments(studentToEdit.id);
    } else {
      setStudentDocuments([]); // Clear if no valid student
      setStudentDocumentsError(null);
    }

    setShowEditForm(true);
    setShowCreateForm(false);
  };

  const handleRemoveStudentFromClass = async (classGroupIdToRemove) => {
    if (!editingStudent || !editingStudent.id) {
      setFormError(t('messages_error_unexpected', { detail: 'No student selected for class removal.'}));
      return;
    }
    if (!isAuthenticated) {
      setFormError(t('messages_error_loginRequired_form'));
      return;
    }

    setIsClassMembershipProcessing(true);
    setFormError(null);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/classgroups/${classGroupIdToRemove}/students/${editingStudent.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok && response.status !== 404) {
        const errorData = await response.json().catch(() => null);
        const errorDetail = errorData?.detail || `HTTP ${response.status}`;
        throw new Error(t('messages_students_class_removeError', { detail: errorDetail }));
      }

      setAssignedClassesForEdit(prev => prev.filter(cg => cg.id !== classGroupIdToRemove));
      setClassGroups(prevCgs => prevCgs.map(cg => 
        cg.id === classGroupIdToRemove 
          ? { ...cg, student_ids: cg.student_ids.filter(sid => sid !== editingStudent.id) } 
          : cg
      ));
      const studentClassIds = new Set(assignedClassesForEdit.filter(ac => ac.id !== classGroupIdToRemove).map(ac => ac.id));
      setAvailableClassesForAdding(classGroups.filter(cg => !studentClassIds.has(cg.id)));
      setFormSuccess(t('messages_students_class_removeSuccess'));
      setTimeout(() => setFormSuccess(null), 3000);

    } catch (err) {
      console.error("Error removing student from class:", err);
      setFormError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsClassMembershipProcessing(false);
    }
  };

  const handleClassToAddChange = (event) => {
    const value = event.target.value;
    if (value === 'CREATE_NEW_CLASS') {
      setTempPreviousClassToAddId(classToAddId); 
      handleOpenCreateClassModal();
    } else {
      setClassToAddId(value);
    }
  };

  const handleAddStudentToSelectedClass = async () => {
    if (!editingStudent || !editingStudent.id || !classToAddId) {
      setFormError(t('messages_students_form_error_selectClassAndStudent'));
      setTimeout(() => setFormError(null), 3000);
      return;
    }

    console.log('handleAddStudentToSelectedClass - Student ID:', editingStudent?.id, 'Class ID:', classToAddId);

    setIsClassMembershipProcessing(true);
    setFormError(null);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/class-groups/${classToAddId}/students/${editingStudent.id}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const errorDetail = errorData?.detail || `HTTP ${response.status}`;
        throw new Error(t('messages_students_class_addError', { detail: errorDetail }));
      }
      
      const classAdded = classGroups.find(cg => cg.id === classToAddId);
      if (classAdded) {
        setAssignedClassesForEdit(prev => [...prev, classAdded]);
        setAvailableClassesForAdding(prev => prev.filter(cg => cg.id !== classToAddId));
        setClassGroups(prevCgs => prevCgs.map(cg => 
          cg.id === classToAddId 
            ? { ...cg, student_ids: [...(cg.student_ids || []), editingStudent.id] } 
            : cg
        ));
      }
      setClassToAddId('');
      setFormSuccess(t('messages_students_class_addSuccess'));
      setTimeout(() => setFormSuccess(null), 3000);

    } catch (err) {
      console.error("Error adding student to class:", err);
      setFormError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsClassMembershipProcessing(false);
    }
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
      
      if (!isEditing && selectedClassGroupId !== initialClassGroupId) {
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

  // Helper to get class names for a student
  const getStudentClassNames = (student) => {
    if (!student || !student.class_group_ids || student.class_group_ids.length === 0 || !classGroups || classGroups.length === 0) {
      return '-';
    }
    const assignedNames = student.class_group_ids
      .map(cgId => {
        const foundClass = classGroups.find(cg => cg.id === cgId || cg._id === cgId);
        return foundClass ? foundClass.class_name : null;
      })
      .filter(name => name !== null);

    return assignedNames.length > 0 ? assignedNames.join(', ') : '-';
  };

  // Sort students before rendering
  const sortedStudents = React.useMemo(() => {
    if (!students || students.length === 0) return [];
    return [...students].sort((a, b) => {
      const fieldA = a[studentSortField];
      const fieldB = b[studentSortField];

      if (fieldA == null && fieldB == null) return 0;
      if (fieldA == null) return studentSortOrder === 'asc' ? 1 : -1;
      if (fieldB == null) return studentSortOrder === 'asc' ? -1 : 1;

      let comparison = 0;
      if (typeof fieldA === 'string' && typeof fieldB === 'string') {
        comparison = fieldA.localeCompare(fieldB);
      } else {
        if (fieldA < fieldB) comparison = -1;
        if (fieldA > fieldB) comparison = 1;
      }
      return studentSortOrder === 'asc' ? comparison : comparison * -1;
    });
  }, [students, studentSortField, studentSortOrder]);

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
              {/* Card 1: Student Details */}
              <div className="card w-full bg-base-100 shadow-md p-4">
                <h4 className="text-md font-semibold mb-3 text-base-content">{t('students_form_card_details_heading', 'Student Details')}</h4>
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
              </div>

              {/* Card 2: Class Assignments (Only for Edit Form) */}
              {showEditForm && editingStudent && (
                <div className="card w-full bg-base-100 shadow-md p-4 mt-4">
                  <h4 className="text-md font-semibold mb-3 text-base-content">{t('students_form_card_classes_heading', 'Class Assignments')}</h4>
                  
                  {/* "Add to Another Class" section */}
                  <div className="mt-0 pt-0">
                    <label htmlFor="addClassDropdown" className="label-text text-sm font-medium">
                      {t('students_form_label_assignToClass', 'Assign to Class:')}
                    </label>
                    <div className="flex items-center gap-2 mt-1 mb-4 pb-3 border-b border-base-300">
                      <select 
                        id="addClassDropdown"
                        value={classToAddId}
                        onChange={handleClassToAddChange}
                        className="select select-bordered select-sm w-full max-w-xs"
                        disabled={isClassMembershipProcessing}
                      >
                        <option value="">{t('students_form_select_aClass', '-- Select a class --')}</option>
                        {availableClassesForAdding.map(cg => (
                          <option key={cg.id} value={cg.id}>
                            {cg.class_name}{cg.academic_year ? ` (${cg.academic_year})` : ''}
                          </option>
                        ))}
                        <option value="CREATE_NEW_CLASS" className="font-semibold text-secondary">
                          {t('students_form_select_createNewClassAndAssign', 'Create New Class & Assign...')}
                        </option>
                      </select>
                      <button 
                        type="button"
                        onClick={handleAddStudentToSelectedClass}
                        className="btn btn-sm btn-outline btn-primary"
                        disabled={!classToAddId || isClassMembershipProcessing}
                      >
                        {isClassMembershipProcessing && classToAddId ? 
                          <span className="loading loading-spinner loading-xs"></span> :
                          t('students_form_button_addToClass', 'Assign to Selected Class')
                        }
                      </button>
                    </div>
                  </div>

                  {/* "Currently Assigned Classes" list */}
                  {assignedClassesForEdit.length > 0 ? (
                    <div className="mt-0 pt-0"> {/* Adjusted mt-6 to mt-0 as it's inside a card now */}
                      <h5 className="text-sm font-medium mb-2 text-base-content/90">
                        {t('students_form_assignedClasses_subheading', 'Currently Assigned Classes:')}
                      </h5>
                      <ul className="list-none space-y-2 bg-base-200/30 p-3 rounded-md shadow-inner">
                        {assignedClassesForEdit.map(cg => (
                          <li key={cg.id} className="text-sm text-base-content/90 py-1 flex justify-between items-center">
                            <span>
                              {cg.class_name}{cg.academic_year ? ` (${cg.academic_year})` : ''}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleRemoveStudentFromClass(cg.id)}
                              className="btn btn-xs btn-ghost text-error hover:bg-error/20"
                              title={t('students_form_button_removeFromClass_title', { className: cg.class_name })}
                              disabled={isClassMembershipProcessing}
                            >
                              {isClassMembershipProcessing ? 
                                <span className="loading loading-spinner loading-xs"></span> :
                                <XCircleIcon className="h-4 w-4" />
                              }
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="text-sm text-base-content/70 italic">{t('students_form_noClassesAssigned')}</p>
                  )}
                </div>
              )}

              {/* Card 3: Student Documents (Only for Edit Form) */}
              {showEditForm && editingStudent && (
                <div className="card w-full bg-base-100 shadow-md p-4 mt-4">
                  <h4 className="text-md font-semibold mb-3 text-base-content">{t('students_form_card_documents_heading', 'Student Documents')}</h4>
                  <div className="card bg-base-100 shadow-xl">
                    <div className="card-body p-4">
                      <div className="flex justify-between items-center">
                        <h2 className="card-title text-lg">Student Documents</h2>
                        <button
                          type="button"
                          onClick={() => fetchStudentDocuments(editingStudent.id)}
                          disabled={isLoadingStudentDocuments}
                          className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
                        >
                          <ArrowPathIcon className="-ml-0.5 mr-2 h-4 w-4" aria-hidden="true" />
                          {isLoadingStudentDocuments ? t('studentsPage.refreshingDocuments') : t('studentsPage.refreshDocuments')}
                        </button>
                      </div>
                      {isLoadingStudentDocuments && <p className="text-sm text-gray-500 mt-2">{t('studentsPage.loadingDocuments')}</p>}
                      {studentDocumentsError && <p className="text-sm text-red-600 mt-2">{studentDocumentsError}</p>}
                      {!isLoadingStudentDocuments && !studentDocumentsError && studentDocuments.length === 0 && (
                        <p className="text-sm text-gray-500">{t('messages_info_noDocumentsFound')}</p>
                      )}
                      {!isLoadingStudentDocuments && !studentDocumentsError && studentDocuments.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="table table-sm w-full">
                            <thead>
                              <tr>
                                <th>{t('documents_table_header_filename', 'Filename')}</th>
                                <th>{t('documents_table_header_uploadedDate', 'Uploaded Date')}</th>
                                <th>{t('documents_table_header_status', 'Status')}</th>
                                <th>{t('documents_table_header_aiScore', 'AI Score')}</th>
                                <th>{t('documents_table_header_wordCount', 'Word Count')}</th>
                                <th>{t('documents_table_header_charCount', 'Char Count')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {studentDocuments.map(doc => (
                                <tr key={doc.id || doc._id}>
                                  <td>{doc.original_filename || 'N/A'}</td>
                                  <td>{doc.upload_timestamp ? new Date(doc.upload_timestamp).toLocaleDateString() : 'N/A'}</td>
                                  <td>{doc.status || 'N/A'}</td>
                                  <td>{doc.ai_score !== undefined && doc.ai_score !== null ? `${doc.ai_score}%` : 'N/A'}</td>
                                  <td>{doc.word_count !== undefined ? doc.word_count : 'N/A'}</td>
                                  <td>{doc.character_count !== undefined ? doc.character_count : 'N/A'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Form Submission Buttons - Common for Create and Edit */}
              {showCreateForm && (
                <div className="form-control w-full mt-4">
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
              )}

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

        {!showCreateForm && !showEditForm && (
          <>
            <div className="mt-4">
              {isLoading && (
                <div className="flex justify-center py-4">
                  <span className="loading loading-spinner loading-lg"></span>
                </div>
              )}
            </div>

            {!isLoading && !error && (
              <div className="card bg-base-100 shadow-xl mb-6">
                <div className="card-body">
                  <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-semibold">{t('students_list_title')}</h2>
                    <div>
                      <button
                        onClick={handleShowCreateForm}
                        className="btn btn-primary mr-2"
                        aria-label={t('students_list_button_add_title')}
                      >
                        <PlusIcon className="h-5 w-5 mr-1 inline-block" />
                        {t('students_list_button_add')}
                      </button>
                      <button
                        onClick={() => navigate('/bulk-upload')}
                        className="btn btn-secondary"
                        aria-label={t('students_list_button_bulkUpload_title')}
                      >
                        <ArrowUpTrayIcon className="h-5 w-5 mr-1 inline-block" />
                        {t('students_list_button_bulkUpload')}
                      </button>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="table table-zebra w-full">
                      <thead>
                        <tr>
                          <th className="cursor-pointer" onClick={() => handleStudentSort('first_name')}>
                            {t('students_column_firstName')}
                            {studentSortField === 'first_name' ? (
                              studentSortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1" /> : <ChevronDownIcon className="h-4 w-4 inline ml-1" />
                            ) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400" />}
                          </th>
                          <th className="cursor-pointer" onClick={() => handleStudentSort('last_name')}>
                            {t('students_column_lastName')}
                            {studentSortField === 'last_name' ? (
                              studentSortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1" /> : <ChevronDownIcon className="h-4 w-4 inline ml-1" />
                            ) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400" />}
                          </th>
                          <th className="cursor-pointer" onClick={() => handleStudentSort('email')}>
                            {t('students_column_email')}
                            {studentSortField === 'email' ? (
                              studentSortOrder === 'asc' ? <ChevronUpIcon className="h-4 w-4 inline ml-1" /> : <ChevronDownIcon className="h-4 w-4 inline ml-1" />
                            ) : <ArrowsUpDownIcon className="h-4 w-4 inline ml-1 text-gray-400" />}
                          </th>
                          <th>{t('students_column_externalId')}</th>
                          <th>{t('students_column_yearGroup')}</th>
                          <th>{t('students_column_classes')}</th>
                          <th>{t('common_label_actions')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {isLoading ? (
                          <tr><td colSpan="7" className="text-center"><span className="loading loading-dots loading-md"></span></td></tr>
                        ) : sortedStudents.length === 0 ? (
                          <tr><td colSpan="7" className="text-center py-4">{error ? error : t('messages_students_noStudents')}</td></tr>
                        ) : (
                          sortedStudents.map(student => (
                            <tr key={student.id} className="hover">
                              <td>{student.first_name}</td>
                              <td>{student.last_name}</td>
                              <td>{student.email || '-'}</td>
                              <td>{student.external_student_id || '-'}</td>
                              <td>{student.year_group || '-'}</td>
                              <td>
                                {getStudentClassNames(student)}
                              </td>
                              <td className="space-x-1">
                                <button
                                  onClick={() => handleShowEditForm(student)}
                                  className="btn btn-ghost btn-sm p-1"
                                  title={t('students_list_button_edit_title')}
                                >
                                  <PencilSquareIcon className="h-5 w-5 text-blue-600 hover:text-blue-800" />
                                </button>
                                <button
                                  onClick={() => handleDelete(student.id, `${student.first_name} ${student.last_name}`)}
                                  className="btn btn-ghost btn-sm p-1"
                                  title={t('students_list_button_delete_title')}
                                >
                                  <TrashIcon className="h-5 w-5 text-red-600 hover:text-red-800" />
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

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