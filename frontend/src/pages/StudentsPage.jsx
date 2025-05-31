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
  DocumentPlusIcon
} from '@heroicons/react/24/outline';
import { ChevronUpIcon, ChevronDownIcon, ArrowsUpDownIcon } from '@heroicons/react/20/solid';
import { API_BASE_URL } from '../services/apiService';

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
  const [studentSortField, setStudentSortField] = useState('created_at'); // Default: created_at
  const [studentSortOrder, setStudentSortOrder] = useState('desc'); // Default: desc

  // New state for student documents
  const [studentDocuments, setStudentDocuments] = useState([]);
  const [isLoadingStudentDocuments, setIsLoadingStudentDocuments] = useState(false);
  const [studentDocumentsError, setStudentDocumentsError] = useState(null);

  // State for allocating documents modal
  const [showAllocateDocumentModal, setShowAllocateDocumentModal] = useState(false);
  const [allTeacherDocuments, setAllTeacherDocuments] = useState([]);
  const [filteredUnallocatedDocuments, setFilteredUnallocatedDocuments] = useState([]);
  const [isLoadingAllTeacherDocs, setIsLoadingAllTeacherDocs] = useState(false);
  const [allocateDocError, setAllocateDocError] = useState(null);
  const [allocateDocSuccess, setAllocateDocSuccess] = useState(null);
  const [selectedDocumentForAllocationId, setSelectedDocumentForAllocationId] = useState(null);
  const [searchTermForAllocateDocModal, setSearchTermForAllocateDocModal] = useState('');
  const [isAllocatingDocument, setIsAllocatingDocument] = useState(false); // For modal's confirm button

  const initialStudentData = {
    first_name: '',
    last_name: '',
    email: '',
    external_student_id: '',
    descriptor: '',
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
    if (!isAuthenticated) return;
    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/students`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || t('messages_error_fetchFailed'));
      }

      const data = await response.json();
      setStudents(data);
    } catch (err) {
      console.error('Error fetching students:', err);
      setError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, getToken, t]);

  const fetchClassGroupsForDropdown = useCallback(async () => {
    if (!isAuthenticated) return [];
    
    setIsLoadingClasses(true);
    setClassFetchError(null);
    let fetchedClasses = [];

    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      const response = await fetch(`${API_BASE_URL}/api/v1/class-groups`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        throw new Error(t('messages_error_fetchFailed', { detail: `class groups: ${response.status}` }));
      }
      const data = await response.json();
      console.log('[fetchClassGroupsForDropdown] Raw data:', data); // Log fetched class groups
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

        const response = await fetch(`${API_BASE_URL}/api/v1/documents/?student_id=${currentStudentId}`, {
            headers: { Authorization: `Bearer ${token}` },
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
  }, [isAuthenticated, getToken, t, editingStudent]); // Added editingStudent to deps for the error message

  const fetchAllTeacherDocuments = useCallback(async () => {
    if (!isAuthenticated) {
      setAllocateDocError(t('messages_error_loginRequired_action'));
      return;
    }
    setIsLoadingAllTeacherDocs(true);
    setAllocateDocError(null);
    setAllTeacherDocuments([]);
    setFilteredUnallocatedDocuments([]);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));
      
      const response = await fetch(`${API_BASE_URL}/api/v1/documents/`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        const detail = (typeof errorData.detail === 'string' && errorData.detail) ? errorData.detail : response.statusText;
        throw new Error(t('messages_docs_fetchError', { detail }));
      }
      const data = await response.json();
      const allDocs = data.map(doc => ({ ...doc, id: doc._id || doc.id })).filter(doc => doc.id);
      setAllTeacherDocuments(allDocs);

      const unallocated = allDocs.filter(doc => !doc.student_id);
      setFilteredUnallocatedDocuments(unallocated);
      // if (unallocated.length === 0) { // Optional: message if no unallocated docs found
      //   setAllocateDocError(t('studentsPage.modal_allocateDoc_noUnallocatedDocs')); 
      // }
    } catch (err) {
      console.error("Error fetching all teacher documents:", err);
      setAllocateDocError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsLoadingAllTeacherDocs(false);
    }
  }, [isAuthenticated, getToken, t]);

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
      const response = await fetch(`${API_BASE_URL}/api/v1/class-groups`, {
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
      const payload = {
        first_name: formData.first_name,
        last_name: formData.last_name,
        email: formData.email || null,
        external_student_id: formData.external_student_id || null,
        descriptor: formData.descriptor || null,
      };
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
      const studentResponseData = await response.json();
      savedStudentId = studentResponseData.id || studentResponseData._id;
      if (!savedStudentId) {
        throw new Error(t('messages_error_actionFailed', { action: logAction, detail: 'missing ID' }));
      }
      
      console.info(t(isEditing ? 'messages_students_form_editSuccess' : 'messages_students_form_success'));
      console.info(`Student ${isEditing ? 'updated' : 'created'} successfully: ${savedStudentId} for teacher ${user.id}`);

      if (!isEditing) {
        // Logic for NEW student class assignment
        if (selectedClassGroupId && selectedClassGroupId !== "") {
          console.info(`[handleSubmit NewStudent] Attempting to add student ${savedStudentId} to selected class ${selectedClassGroupId}`);
          const addUrl = `${API_BASE_URL}/api/v1/class-groups/${selectedClassGroupId}/students/${savedStudentId}`;
          try {
            const addResponse = await fetch(addUrl, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            });
            if (!addResponse.ok) {
              const errorData = await addResponse.json().catch(() => ({}));
              const detail = errorData.detail || `Status: ${addResponse.status}`;
              console.warn(`[handleSubmit NewStudent] Failed to add student ${savedStudentId} to class ${selectedClassGroupId}. Detail: ${detail}`);
              setFormError(t('messages_students_class_assignErrorOnCreate', { detail })); 
            } else {
              console.info(`[handleSubmit NewStudent] Student ${savedStudentId} successfully added to class ${selectedClassGroupId}.`);
            }
          } catch (error) {
            console.warn(`[handleSubmit NewStudent] Error adding student to class ${selectedClassGroupId}: ${error.message}`);
            setFormError(t('messages_students_class_assignErrorOnCreate', { detail: error.message }));
          }
        }
      } else {
        // Logic for EXISTING student class assignment
        if (selectedClassGroupId !== initialClassGroupId) {
          console.info(`[handleSubmit EditStudent] Class selection changed. Initial: '${initialClassGroupId}', Selected: '${selectedClassGroupId}' for student ${savedStudentId}`);
          
          // 1. Remove from old class if it was set and is different from new selection
          if (initialClassGroupId && initialClassGroupId !== "" && initialClassGroupId !== selectedClassGroupId) {
            console.info(`[handleSubmit EditStudent] Attempting to remove student ${savedStudentId} from old class ${initialClassGroupId}`);
            const deleteUrl = `${API_BASE_URL}/api/v1/class-groups/${initialClassGroupId}/students/${savedStudentId}`;
            try {
              const deleteResponse = await fetch(deleteUrl, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` },
              });
              if (!deleteResponse.ok && deleteResponse.status !== 404) {
                const errorData = await deleteResponse.json().catch(() => ({}));
                console.warn(`[handleSubmit EditStudent] Failed to remove student from old class ${initialClassGroupId}. Detail: ${errorData.detail || `Status: ${deleteResponse.status}`}`);
              } else {
                console.info(`[handleSubmit EditStudent] Student ${savedStudentId} removed from old class ${initialClassGroupId} or was not in it.`);
              }
            } catch (error) {
              console.warn(`[handleSubmit EditStudent] Error removing student from old class ${initialClassGroupId}: ${error.message}`);
            }
          }

          // 2. Add to new class if a new one is selected (and it's not empty)
          if (selectedClassGroupId && selectedClassGroupId !== "") {
            console.info(`[handleSubmit EditStudent] Attempting to add student ${savedStudentId} to new class ${selectedClassGroupId}`);
            const addUrl = `${API_BASE_URL}/api/v1/class-groups/${selectedClassGroupId}/students/${savedStudentId}`;
            try {
              const addResponse = await fetch(addUrl, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
              });
              if (!addResponse.ok) {
                const errorData = await addResponse.json().catch(() => ({}));
                console.warn(`[handleSubmit EditStudent] Failed to add student ${savedStudentId} to new class ${selectedClassGroupId}. Detail: ${errorData.detail || `Status: ${addResponse.status}`}`);
                // Consider setting formError here too if this failure is critical for editing
              } else {
                console.info(`[handleSubmit EditStudent] Student ${savedStudentId} successfully added to new class ${selectedClassGroupId}.`);
              }
            } catch (error) {
              console.warn(`[handleSubmit EditStudent] Error adding student to new class ${selectedClassGroupId}: ${error.message}`);
            }
          }
        } else {
          console.info(`[handleSubmit EditStudent] Class selection not changed for student ${savedStudentId}. No class update needed.`);
        }
      }

      // Common post-success actions
      if (isEditing) { // For existing students, stay on form, refresh related data
        // setFormSuccess(t('messages_students_form_editSuccess')); // Already handled by console.info
        // Fetch updated student details or class lists if necessary for immediate UI update
        // For now, we assume the individual add/remove calls update state sufficiently for the session, or a full refresh is okay.
      }
      // For both new and existing, after all operations:
      await fetchStudents(); // Refresh student list in the background
      await fetchClassGroupsForDropdown(); // Refresh class group dropdown
      resetForms(); // Reset form fields and hide form
      if (location.pathname.startsWith('/students')) { // Only navigate if still on a student related page (e.g. not if called from bulk upload context in future)
          navigate('/students'); // Navigate back to student list view
      }

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

  const handleOpenAllocateDocumentModal = () => {
    if (!editingStudent || !editingStudent.id) {
      console.error("Cannot open allocate document modal without a selected student.");
      return;
    }
    setShowAllocateDocumentModal(true);
    setSelectedDocumentForAllocationId(null);
    setSearchTermForAllocateDocModal('');
    setAllocateDocError(null);
    setAllocateDocSuccess(null);
    fetchAllTeacherDocuments();
  };

  const handleCloseAllocateDocumentModal = () => {
    setShowAllocateDocumentModal(false);
    setAllTeacherDocuments([]); // Clear to ensure fresh data next time
    setFilteredUnallocatedDocuments([]);
    setSelectedDocumentForAllocationId(null);
    setSearchTermForAllocateDocModal('');
    setAllocateDocError(null);
    setAllocateDocSuccess(null);
    setIsAllocatingDocument(false);
  };

  const handleConfirmDocumentAllocation = async () => {
    if (!editingStudent || !editingStudent.id || !selectedDocumentForAllocationId) {
      setAllocateDocError(t('messages_students_docAllocate_error_selectDocAndStudent'));
      return;
    }
    setIsAllocatingDocument(true);
    setAllocateDocError(null);
    setAllocateDocSuccess(null);
    try {
      const token = await getToken();
      if (!token) throw new Error(t('messages_error_authTokenMissing'));

      const response = await fetch(`${API_BASE_URL}/api/v1/documents/${selectedDocumentForAllocationId}/assign-student`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ student_id: editingStudent.id }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        const detail = (typeof errorData.detail === 'string' && errorData.detail) ? errorData.detail : response.statusText;
        throw new Error(t('messages_students_docAllocate_error_assignFailed', { detail }));
      }
      
      const allocatedDocFilename = allTeacherDocuments.find(d => d.id === selectedDocumentForAllocationId)?.original_filename || 'document';
      setAllocateDocSuccess(t('messages_students_docAllocate_success', { filename: allocatedDocFilename, studentName: `${editingStudent.first_name} ${editingStudent.last_name}` }));
      
      fetchStudentDocuments(editingStudent.id);
      // Optimistically update the unallocated list locally or re-fetch
      setFilteredUnallocatedDocuments(prev => prev.filter(doc => doc.id !== selectedDocumentForAllocationId));
      setAllTeacherDocuments(prev => prev.filter(doc => doc.id !== selectedDocumentForAllocationId)); // Also from the main list if needed

      setTimeout(() => {
        handleCloseAllocateDocumentModal();
      }, 2000);

    } catch (err) {
      console.error("Error allocating document to student:", err);
      setAllocateDocError(err.message || t('messages_error_unexpected'));
    } finally {
      setIsAllocatingDocument(false);
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
                      <div className="flex justify-between items-center mb-4">
                        <h2 className="card-title text-lg">{t('students_form_card_studentDocuments_subheading', 'Documents for this Student')}</h2>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={handleOpenAllocateDocumentModal}
                            className="btn btn-sm btn-primary"
                            title={t('studentsPage.button_allocateNewDocument_title')}
                            disabled={isLoadingStudentDocuments || isAllocatingDocument}
                          >
                            <DocumentPlusIcon className="h-5 w-5 mr-1" />
                            {t('studentsPage.button_allocateNewDocument')}
                          </button>
                          <button
                            type="button"
                            onClick={() => fetchStudentDocuments(editingStudent.id)}
                            disabled={isLoadingStudentDocuments}
                            className="btn btn-sm btn-outline btn-secondary"
                            title={t('studentsPage.button_refreshDocuments_title')}
                          >
                            <ArrowPathIcon className="h-5 w-5" />
                          </button>
                        </div>
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
                          <th className="cursor-pointer hover:bg-base-200" onClick={() => handleStudentSort('first_name')}>
                            {t('students_column_firstName')}
                            {studentSortField === 'first_name' && (studentSortOrder === 'asc' ? <ChevronUpIcon className="inline h-4 w-4 ml-1" /> : <ChevronDownIcon className="inline h-4 w-4 ml-1" />)}
                            {studentSortField !== 'first_name' && <ArrowsUpDownIcon className="inline h-4 w-4 ml-1 text-gray-400" />}
                          </th>
                          <th className="cursor-pointer hover:bg-base-200" onClick={() => handleStudentSort('last_name')}>
                            {t('students_column_lastName')}
                            {studentSortField === 'last_name' && (studentSortOrder === 'asc' ? <ChevronUpIcon className="inline h-4 w-4 ml-1" /> : <ChevronDownIcon className="inline h-4 w-4 ml-1" />)}
                            {studentSortField !== 'last_name' && <ArrowsUpDownIcon className="inline h-4 w-4 ml-1 text-gray-400" />}
                          </th>
                          <th className="cursor-pointer hover:bg-base-200" onClick={() => handleStudentSort('email')}>
                            {t('students_column_email')}
                            {studentSortField === 'email' && (studentSortOrder === 'asc' ? <ChevronUpIcon className="inline h-4 w-4 ml-1" /> : <ChevronDownIcon className="inline h-4 w-4 ml-1" />)}
                            {studentSortField !== 'email' && <ArrowsUpDownIcon className="inline h-4 w-4 ml-1 text-gray-400" />}
                          </th>
                          <th>{t('students_column_externalId')}</th>
                          <th>{t('students_column_classes')}</th>
                          <th className="cursor-pointer hover:bg-base-200" onClick={() => handleStudentSort('created_at')}>
                            {t('students_column_createdOn', 'Created On')}
                            {studentSortField === 'created_at' && (studentSortOrder === 'asc' ? <ChevronUpIcon className="inline h-4 w-4 ml-1" /> : <ChevronDownIcon className="inline h-4 w-4 ml-1" />)}
                            {studentSortField !== 'created_at' && <ArrowsUpDownIcon className="inline h-4 w-4 ml-1 text-gray-400" />}
                          </th>
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
                              <td>
                                {getStudentClassNames(student)}
                              </td>
                              <td>
                                {student.created_at ? new Date(student.created_at).toLocaleString() : '-'}
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

      {/* Allocate Document Modal */}
      {showAllocateDocumentModal && editingStudent && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
          <div className="bg-base-100 p-6 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-semibold mb-4 text-base-content">
              {t('studentsPage.modal_allocateDoc_heading', { studentName: `${editingStudent.first_name} ${editingStudent.last_name}` })}
            </h3>
            
            {allocateDocError && (
              <div className="alert alert-error mb-4">
                <XCircleIcon className="h-6 w-6"/>
                <span>{t('common_error_prefix')} {allocateDocError}</span>
              </div>
            )}
            {allocateDocSuccess && (
              <div className="alert alert-success mb-4">
                <CheckCircleIcon className="h-6 w-6" />
                <span>{allocateDocSuccess}</span>
              </div>
            )}

            <div className="mb-4">
              <input
                type="text"
                placeholder={t('studentsPage.modal_allocateDoc_searchPlaceholder')}
                value={searchTermForAllocateDocModal}
                onChange={(e) => setSearchTermForAllocateDocModal(e.target.value)}
                className="input input-bordered w-full input-sm"
                disabled={isLoadingAllTeacherDocs}
              />
            </div>

            <div className="overflow-y-auto flex-grow mb-4 border border-base-300 rounded-md min-h-[200px]">
              {isLoadingAllTeacherDocs ? (
                <div className="flex justify-center items-center h-full">
                  <span className="loading loading-spinner loading-lg"></span>
                  <p className="ml-2">{t('studentsPage.modal_allocateDoc_loadingDocs')}</p>
                </div>
              ) : filteredUnallocatedDocuments.filter(doc => 
                  doc.original_filename.toLowerCase().includes(searchTermForAllocateDocModal.toLowerCase())
                ).length === 0 ? (
                <p className="text-center p-4 text-base-content/70">
                  {allTeacherDocuments.length > 0 && filteredUnallocatedDocuments.length === 0 
                    ? t('studentsPage.modal_allocateDoc_allDocsAllocated') 
                    : t('studentsPage.modal_allocateDoc_noUnallocatedDocs')
                  }
                </p>
              ) : (
                <table className="table table-sm w-full">
                  <thead>
                    <tr>
                      <th>{t('studentsPage.modal_allocateDoc_col_filename')}</th>
                      <th>{t('studentsPage.modal_allocateDoc_col_status')}</th>
                      <th>{t('studentsPage.modal_allocateDoc_col_words')}</th>
                      <th>{t('studentsPage.modal_allocateDoc_col_chars')}</th>
                      <th>{t('studentsPage.modal_allocateDoc_col_aiScore')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUnallocatedDocuments
                      .filter(doc => 
                        doc.original_filename.toLowerCase().includes(searchTermForAllocateDocModal.toLowerCase())
                      )
                      .map(doc => (
                        <tr 
                          key={doc.id}
                          onClick={() => setSelectedDocumentForAllocationId(doc.id)}
                          className={`cursor-pointer hover:bg-base-200 ${selectedDocumentForAllocationId === doc.id ? 'bg-primary text-primary-content' : ''}`}
                        >
                          <td title={doc.original_filename} className="truncate max-w-xs">{doc.original_filename}</td>
                          <td><span className={`badge badge-sm ${doc.status === 'COMPLETED' ? 'badge-success' : doc.status === 'PROCESSING' || doc.status === 'QUEUED' ? 'badge-info' : doc.status === 'ERROR' ? 'badge-error' : 'badge-ghost'}`}>{doc.status}</span></td>
                          <td>{doc.word_count?.toLocaleString() || '-'}</td>
                          <td>{doc.character_count?.toLocaleString() || '-'}</td>
                          <td>{doc.score !== null && doc.score !== undefined ? `${(doc.score * 100).toFixed(1)}%` : 'N/A'}</td>
                        </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="flex justify-end space-x-3 pt-4 border-t border-base-300">
              <button
                type="button"
                onClick={handleCloseAllocateDocumentModal}
                className="btn btn-ghost btn-sm"
                disabled={isAllocatingDocument}
              >
                {t('common_button_cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmDocumentAllocation} // Changed from form onSubmit to button onClick
                className="btn btn-primary btn-sm"
                disabled={!selectedDocumentForAllocationId || isAllocatingDocument || isLoadingAllTeacherDocs}
              >
                {isAllocatingDocument ? (
                  <><span className="loading loading-spinner loading-xs"></span>{t('common_status_allocating')}</>
                ) : (
                  t('studentsPage.modal_allocateDoc_button_confirm')
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default StudentsPage; 