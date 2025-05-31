import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import apiService from '../services/apiService'; // Assuming this will be used for API calls
import { ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid';

const AdminManageDocumentsPage = () => {
    const { t } = useTranslation();
    const { currentUser, loading: authLoading } = useAuth();
    const navigate = useNavigate();
    
    const [documents, setDocuments] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'created_at', direction: 'descending' });
    const [searchTerm, setSearchTerm] = useState('');

    const fetchAdminDocuments = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            // TODO: Replace with actual API call
            // const fetchedData = await apiService.get('/admin/documents/all'); 
            // For now, using placeholder empty data. 
            // When implementing, ensure _id is mapped to id if necessary, similar to AdminStudentsPage.
            const fetchedData = []; // Replace with actual API call result
            setDocuments(fetchedData.map(doc => ({...doc, id: doc._id || doc.id })) || []);
            console.log("AdminManageDocumentsPage: Fetched documents data (placeholder):", fetchedData);
        } catch (err) {
            console.error("AdminManageDocumentsPage: Error fetching documents data:", err);
            let errorMessage = t('admin_documents_page.error_load', "Failed to load documents.");
            if (err.response && err.response.data && typeof err.response.data.detail === 'string') {
                errorMessage = err.response.data.detail;
            } else if (typeof err.message === 'string') {
                errorMessage = err.message;
            }
            setError(errorMessage);
            setDocuments([]);
        } finally {
            setIsLoading(false);
        }
    }, [t]);

    useEffect(() => {
        if (!authLoading) {
            if (!currentUser || !currentUser.is_administrator) {
                navigate('/');
                return;
            }
            fetchAdminDocuments();
        }
    }, [currentUser, authLoading, navigate, fetchAdminDocuments]);

    const columnsToDisplay = useMemo(() => [
        { key: '_id', label: t('admin_documents_table.col_id', 'ID'), sortable: true },
        { key: 'original_filename', label: t('admin_documents_table.col_original_filename', 'Original Filename'), sortable: true },
        { key: 'storage_blob_path', label: t('admin_documents_table.col_storage_blob_path', 'Storage Path'), sortable: false },
        { key: 'file_type', label: t('admin_documents_table.col_file_type', 'File Type'), sortable: true },
        { key: 'upload_timestamp', label: t('admin_documents_table.col_upload_timestamp', 'Uploaded At'), sortable: true },
        { key: 'student_id', label: t('admin_documents_table.col_student_id', 'Student ID'), sortable: true },
        { key: 'assignment_id', label: t('admin_documents_table.col_assignment_id', 'Assignment ID'), sortable: true },
        { key: 'status', label: t('admin_documents_table.col_status', 'Status'), sortable: true },
        { key: 'batch_id', label: t('admin_documents_table.col_batch_id', 'Batch ID'), sortable: true },
        { key: 'queue_position', label: t('admin_documents_table.col_queue_position', 'Queue Position'), sortable: true },
        { key: 'processing_priority', label: t('admin_documents_table.col_processing_priority', 'Priority'), sortable: true },
        { key: 'character_count', label: t('admin_documents_table.col_character_count', 'Chars'), sortable: true },
        { key: 'word_count', label: t('admin_documents_table.col_word_count', 'Words'), sortable: true },
        { key: 'score', label: t('admin_documents_table.col_score', 'Score'), sortable: true },
        { key: 'teacher_id', label: t('admin_documents_table.col_teacher_id', 'Teacher ID'), sortable: true },
        { key: 'student_details', label: t('admin_documents_table.col_student_details', 'Student Details'), sortable: false }, // Consider how to display this
        { key: 'created_at', label: t('admin_documents_table.col_created_at', 'Created At'), sortable: true },
        { key: 'updated_at', label: t('admin_documents_table.col_updated_at', 'Updated At'), sortable: true },
        { key: 'is_deleted', label: t('admin_documents_table.col_is_deleted', 'Deleted?'), sortable: true },
        // Add an actions column if needed, similar to AdminStudentsPage
        // { key: 'actions', label: t('admin_documents_table.col_actions', 'Actions'), sortable: false }
    ], [t]);

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

    const formatDisplayValue = (value) => {
        if (typeof value === 'boolean') {
            return value ? t('general.yes', 'Yes') : t('general.no', 'No');
        }
        if (value instanceof Date || (typeof value === 'string' && !isNaN(Date.parse(value)))) {
            return new Date(value).toLocaleString();
        }
        if (value === null || value === undefined) {
            return t('general.not_applicable', 'N/A');
        }
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        // For objects (like student_details), you might want a more specific rendering
        if (typeof value === 'object') {
            return JSON.stringify(value); // Basic representation
        }
        return String(value);
    };

    const filteredAndSortedDocuments = useMemo(() => {
        let filteredItems = [...documents];

        if (searchTerm) {
            const lowercasedSearchTerm = searchTerm.toLowerCase();
            filteredItems = filteredItems.filter(doc => {
                return (
                    (doc.original_filename && doc.original_filename.toLowerCase().includes(lowercasedSearchTerm)) ||
                    (doc._id && String(doc._id).toLowerCase().includes(lowercasedSearchTerm)) ||
                    (doc.student_id && String(doc.student_id).toLowerCase().includes(lowercasedSearchTerm)) ||
                    (doc.teacher_id && String(doc.teacher_id).toLowerCase().includes(lowercasedSearchTerm)) ||
                    (doc.status && doc.status.toLowerCase().includes(lowercasedSearchTerm))
                );
            });
        }

        if (sortConfig.key) {
            filteredItems.sort((a, b) => {
                const valA = a[sortConfig.key];
                const valB = b[sortConfig.key];

                let comparison = 0;
                if (valA === null || valA === undefined) comparison = 1;
                else if (valB === null || valB === undefined) comparison = -1;
                else if (typeof valA === 'number' && typeof valB === 'number') {
                    comparison = valA - valB;
                }
                else if (typeof valA === 'boolean' && typeof valB === 'boolean') {
                    comparison = valA === valB ? 0 : (valA ? -1 : 1);
                } else {
                    // Attempt to parse as dates for date fields
                    if (['upload_timestamp', 'created_at', 'updated_at'].includes(sortConfig.key)) {
                        const dateA = new Date(valA).getTime();
                        const dateB = new Date(valB).getTime();
                        if (!isNaN(dateA) && !isNaN(dateB)) {
                            comparison = dateA - dateB;
                        } else {
                            comparison = String(valA).toLowerCase().localeCompare(String(valB).toLowerCase());
                        }
                    } else {
                        comparison = String(valA).toLowerCase().localeCompare(String(valB).toLowerCase());
                    }
                }
                return sortConfig.direction === 'ascending' ? comparison : comparison * -1;
            });
        }
        return filteredItems;
    }, [documents, sortConfig, searchTerm]);

    if (authLoading) {
        return <div className="p-8 text-center">{t('admin_documents_page.loading_auth', 'Verifying administrator privileges...')}</div>;
    }

    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8 text-primary">
                {t('admin_documents_page.title', 'Manage Documents (Admin)')}
            </h1>

            {error && (
                <div className="p-4 mb-4 text-center text-error bg-error/10 rounded-md">
                    {error}
                </div>
            )}

            <div className="mb-4">
                <input 
                    type="text"
                    placeholder={t('admin_documents_page.search_placeholder', "Search documents...")}
                    className="input input-bordered w-full max-w-xs sm:max-w-sm md:max-w-md"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>
            
            <div className="card bg-base-100 shadow-xl">
                <div className="card-body p-0 sm:p-4 md:p-6">
                    {isLoading && (
                        <div className="p-8 text-center">
                            <span className="loading loading-lg loading-spinner text-primary"></span>
                            <p>{t('admin_documents_page.loading_data', 'Loading documents...')}</p>
                        </div>
                    )}
                    {!isLoading && filteredAndSortedDocuments.length === 0 && (
                        <p className="text-center py-4">
                            {searchTerm ? 
                                t('admin_documents_page.no_results', 'No documents match your search criteria.') :
                                t('admin_documents_page.no_documents', 'No documents available.')}
                        </p>
                    )}
                    {!isLoading && filteredAndSortedDocuments.length > 0 && (
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
                                                        {column.label}
                                                        {getSortIcon(column.key)}
                                                    </button>
                                                ) : (
                                                    column.label
                                                )}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAndSortedDocuments.map((doc, rowIndex) => (
                                        <tr key={doc.id || doc._id || rowIndex} className="hover">
                                            {columnsToDisplay.map(column => (
                                                <td key={`${doc.id || doc._id || rowIndex}-${column.key}`} className="p-3 text-sm whitespace-nowrap">
                                                    {formatDisplayValue(doc[column.key])}
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

export default AdminManageDocumentsPage; 