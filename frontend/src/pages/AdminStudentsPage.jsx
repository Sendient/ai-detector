import React, { useEffect, useState, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import apiService from '../services/apiService';
import { ArrowUpIcon, ArrowDownIcon, TrashIcon } from '@heroicons/react/24/solid';

const AdminStudentsPage = () => {
    const { t } = useTranslation();
    const { currentUser, loading: authLoading } = useAuth();
    const navigate = useNavigate();
    const [students, setStudents] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'last_name', direction: 'ascending' });
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        if (!authLoading) {
            if (!currentUser || !currentUser.is_administrator) {
                navigate('/');
                return;
            }
            fetchStudentsData();
        }
    }, [currentUser, authLoading, navigate]);

    const fetchStudentsData = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const fetchedStudentsRaw = await apiService.get('/api/v1/admin/students'); 
            const processedStudents = fetchedStudentsRaw.map(student => {
                if (!student.id && student._id) {
                    return { ...student, id: student._id };
                }
                return student;
            });
            setStudents(processedStudents || []);
            console.log("AdminStudentsPage: Processed students data:", processedStudents);
        } catch (err) {
            console.error("AdminStudentsPage: Error fetching student data:", err);
            let errorMessage = t('admin_students_page_error_failed_to_load', "Failed to load student data.");
            if (err.response && err.response.data && typeof err.response.data.detail === 'string') {
                errorMessage = err.response.data.detail;
            } else if (typeof err.message === 'string') {
                errorMessage = err.message;
            }
            setError(errorMessage);
            setStudents([]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleDeleteStudent = async (studentId, studentName) => {
        if (!studentId) {
            console.error("AdminStudentsPage: handleDeleteStudent called with undefined studentId.");
            setError(t('admin_students_page_error_undefined_id', "Cannot delete student: ID is missing."));
            return;
        }
        if (window.confirm(t('admin_students_page_confirm_delete', `Are you sure you want to delete student: ${studentName || 'N/A'}? This action cannot be undone.`))) {
            try {
                await apiService.delete(`/api/v1/admin/students/${studentId}`);
                setStudents(prevStudents => prevStudents.filter(student => student.id !== studentId));
                setError(null);
            } catch (err) {
                console.error("AdminStudentsPage: Error deleting student:", err);
                if (err.response && err.response.status === 404) {
                    setStudents(prevStudents => prevStudents.filter(student => student.id !== studentId));
                    setError(null);
                    console.log(`AdminStudentsPage: Student ${studentId} not found on backend (404), removed from UI list.`);
                } else {
                    let deleteErrorMessage = t('admin_students_page_error_delete', "Failed to delete student.");
                    if (err.response && err.response.data && typeof err.response.data.detail === 'string') {
                        deleteErrorMessage = err.response.data.detail;
                    } else if (typeof err.message === 'string') {
                        deleteErrorMessage = err.message;
                    } else if (err.response && typeof err.response.statusText === 'string' && err.response.statusText) {
                        deleteErrorMessage = `${t('admin_students_page_error_status', 'Error')}: ${err.response.status} ${err.response.statusText}`;
                    }    
                    setError(deleteErrorMessage);
                }
            }
        }
    };

    const filteredAndSortedStudents = useMemo(() => {
        let filteredItems = [...students];

        if (searchTerm) {
            const lowercasedSearchTerm = searchTerm.toLowerCase();
            filteredItems = filteredItems.filter(student => {
                return (
                    (student.first_name && student.first_name.toLowerCase().includes(lowercasedSearchTerm)) ||
                    (student.last_name && student.last_name.toLowerCase().includes(lowercasedSearchTerm)) ||
                    (student.email && student.email.toLowerCase().includes(lowercasedSearchTerm)) ||
                    (student.teacher_id && student.teacher_id.toLowerCase().includes(lowercasedSearchTerm))
                );
            });
        }

        if (sortConfig.key !== null) {
            filteredItems.sort((a, b) => {
                const valA = a[sortConfig.key] === null || a[sortConfig.key] === undefined ? '' : a[sortConfig.key];
                const valB = b[sortConfig.key] === null || b[sortConfig.key] === undefined ? '' : b[sortConfig.key];
                
                if (valA < valB) {
                    return sortConfig.direction === 'ascending' ? -1 : 1;
                }
                if (valA > valB) {
                    return sortConfig.direction === 'ascending' ? 1 : -1;
                }
                return 0;
            });
        }
        return filteredItems;
    }, [students, sortConfig, searchTerm]);

    const requestSort = (key) => {
        let direction = 'ascending';
        if (sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    const getSortIcon = (key) => {
        if (sortConfig.key === key) {
            return sortConfig.direction === 'ascending' ? 
                <ArrowUpIcon className="h-4 w-4 inline ml-1" /> : 
                <ArrowDownIcon className="h-4 w-4 inline ml-1" />;
        }
        return <span className="h-4 w-4 inline-block ml-1"></span>; 
    };

    const columnsToDisplay = [
        { key: 'first_name', label: 'First Name', sortable: true },
        { key: 'last_name', label: 'Last Name', sortable: true },
        { key: 'teacher_id', label: 'Teacher Id', sortable: true },
        { key: 'email', label: 'Email', sortable: true },
        { key: 'class_group_ids', label: 'Class Group Ids', sortable: false },
        { key: 'external_student_id', label: 'External Student Id', sortable: false },
        { key: 'year_group', label: 'Year Group', sortable: false },
        { key: 'descriptor', label: 'Descriptor', sortable: false },
        { key: 'created_at', label: 'Created At', sortable: true},
        { key: 'updated_at', label: 'Updated At', sortable: true},
        { key: 'actions', label: 'Actions', sortable: false }
    ];

    if (authLoading || !currentUser || !currentUser.is_administrator) {
        return (
            <div className="p-8 text-center">
                {t('admin_students_page_loading_auth', 'Verifying administrator privileges...')}
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="p-8 text-center">
                <span className="loading loading-lg loading-spinner text-primary"></span>
                <p>{t('admin_students_page_loading_data', 'Loading student data...')}</p>
            </div>
        );
    }

    if (error) {
        return <div className="p-8 text-center text-error">{t('admin_students_page_error', 'Error')}: {error}</div>;
    }
    
    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8 text-primary">
                {t('admin_students_page_title', 'Manage Students (Admin)')}
            </h1>

            {error && (
                <div className="p-4 mb-4 text-center text-error bg-error/10 rounded-md">
                    {typeof error === 'string' ? error : t('admin_students_page_error_generic', 'An unexpected error occurred.')}
                </div>
            )}

            <div className="mb-4">
                <input 
                    type="text"
                    placeholder={t('admin_students_page_search_placeholder', "Search by Name, Email, or Teacher ID...")}
                    className="input input-bordered w-full max-w-xs sm:max-w-sm md:max-w-md"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>
            
            <div className="card bg-base-100 shadow-xl">
                <div className="card-body p-0 sm:p-4 md:p-6">
                    {filteredAndSortedStudents.length === 0 && !isLoading && (
                        <p className="text-center py-4">
                            {searchTerm ? 
                                t('admin_students_page_no_results', 'No students match your search criteria.') : 
                                t('admin_students_page_no_students', 'No student data available at the moment.')}
                        </p>
                    )}

                    {console.log("AdminStudentsPage: Rendering table. filteredAndSortedStudents:", filteredAndSortedStudents, "Length:", filteredAndSortedStudents.length)}
                    {filteredAndSortedStudents.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="table table-zebra table-sm w-full">
                                <thead className="bg-base-200">
                                    <tr>
                                        {columnsToDisplay.map(column => (
                                            <th key={column.key} className="p-3 text-left text-xs font-semibold uppercase tracking-wider">
                                                {column.sortable ? (
                                                    <button 
                                                        onClick={() => requestSort(column.key)} 
                                                        className="btn btn-ghost btn-xs p-0 hover:bg-transparent flex items-center normal-case font-semibold"
                                                    >
                                                        {t(`admin_students_table_col_${column.key}`, column.label)}
                                                        {getSortIcon(column.key)}
                                                    </button>
                                                ) : (
                                                    t(`admin_students_table_col_${column.key}`, column.label)
                                                )}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAndSortedStudents.map((student, rowIndex) => (
                                        <tr key={student.id || rowIndex} className="hover">
                                            {columnsToDisplay.map(column => (
                                                <td key={`${student.id || rowIndex}-${column.key}`} className="p-3 text-sm">
                                                    {column.key === 'actions' ? (
                                                        student.id ? (
                                                            <button 
                                                                onClick={() => handleDeleteStudent(student.id, `${student.first_name} ${student.last_name}`)}
                                                                className="btn btn-ghost btn-xs text-error hover:bg-error/20"
                                                                aria-label={t('admin_students_page_delete_student_aria', `Delete student ${student.first_name} ${student.last_name}`)}
                                                                title={t('admin_students_page_delete_student_title', 'Delete Student')}
                                                            >
                                                                <TrashIcon className="h-5 w-5" />
                                                            </button>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">{t('general.id_missing', '(ID Missing)')}</span>
                                                        )
                                                    ) : typeof student[column.key] === 'boolean' ? (student[column.key] ? t('general.yes', 'Yes') : t('general.no', 'No')) :
                                                     Array.isArray(student[column.key]) ? student[column.key].join(', ') :
                                                     (student[column.key] === null || student[column.key] === undefined ? t('general.not_applicable', 'N/A') : String(student[column.key]))}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AdminStudentsPage; 