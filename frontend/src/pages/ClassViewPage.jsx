import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'react-toastify';
import { useAuth } from '../contexts/AuthContext';

// VITE_API_BASE_URL will be like http://localhost:8000 (without /api/v1)
const API_HOST_URL = import.meta.env.VITE_API_BASE_URL;
const API_PREFIX = '/api/v1';

function ClassViewPage() {
    const { t } = useTranslation();
    const { classId } = useParams();
    const navigate = useNavigate();
    const { isAuthenticated, isLoading: authLoading, getToken } = useKindeAuth();
    const [classGroup, setClassGroup] = useState(null);
    const [students, setStudents] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    const API_URL = API_HOST_URL;

    const fetchClassDetails = useCallback(async () => {
        if (!classId) {
            console.warn('fetchClassDetails called unexpectedly without classId.');
            setError(t('messages_error_invalidId'));
            setIsLoading(false);
            return;
        }

        setIsLoading(true);
        setError(null);

        if (!isAuthenticated) {
            if (!authLoading) setError(t('messages_error_loginRequired_viewClasses'));
            setIsLoading(false);
            return;
        }

        try {
            const token = await getToken();
            if (!token) {
                setError(t('messages_error_authTokenMissing'));
                setIsLoading(false);
                return;
            }
            
            console.log(`Fetching class details for ID: ${classId}`);
            const classGroupRes = await fetch(`${API_HOST_URL}${API_PREFIX}/class-groups/${classId}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!classGroupRes.ok) {
                const errorData = await classGroupRes.json().catch(() => ({ detail: classGroupRes.statusText }));
                throw new Error(t('messages_error_fetchFailed', { detail: errorData.detail || t('messages_error_notFound', { item: t('common_label_className') }) }));
            }
            const classGroupData = await classGroupRes.json();
            setClassGroup(classGroupData);

            const studentsRes = await fetch(`${API_HOST_URL}${API_PREFIX}/students?class_group_id=${classId}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!studentsRes.ok) {
                const errorData = await studentsRes.json().catch(() => ({ detail: studentsRes.statusText }));
                throw new Error(t('messages_error_fetchFailed', { detail: errorData.detail || t('messages_students_fetchError') }));
            }
            const studentsData = await studentsRes.json();
            console.log("Fetched Students Data for ClassViewPage:", JSON.stringify(studentsData, null, 2));
            setStudents(studentsData || []);

            const documentsRes = await fetch(`${API_HOST_URL}${API_PREFIX}/documents?class_group_id=${classId}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!documentsRes.ok) throw new Error(t('messages_error_fetchFailed', { detail: `documents (${documentsRes.status})` }));

        } catch (err) {
            console.error("Error fetching class details:", err);
            setError(err.message);
            setClassGroup(null);
            setStudents([]);
        } finally {
            setIsLoading(false);
        }
    }, [API_HOST_URL, API_PREFIX, isAuthenticated, authLoading, t, getToken, classId]);

    useEffect(() => {
        if (classId) {
            fetchClassDetails();
        } else {
            console.log('useEffect: classId is not available yet or route is missing param.');
            setIsLoading(false);
        }
    }, [classId, fetchClassDetails]);

    if (authLoading || isLoading) {
        return <div className="p-4 flex justify-center items-center min-h-screen"><span className="loading loading-spinner loading-lg"></span></div>;
    }

    if (error) {
        return (
            <div className="container mx-auto p-4">
                <div role="alert" className="alert alert-error mb-4 shadow-lg">
                    <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    <span>{error}</span>
                </div>
                <Link to="/classes" className="btn btn-ghost">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 me-2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                    </svg>
                    {t('sidebar_menu_classes')}
                </Link>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <div className="p-4">{t('messages_error_loginRequired_viewClasses')}</div>;
    }

    if (!classGroup) {
        return (
            <div className="container mx-auto p-4">
                <p>{t('messages_error_notFound', { item: t('common_label_className') })}</p>
                <Link to="/classes" className="btn btn-ghost mt-4">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 me-2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                    </svg>
                    {t('sidebar_menu_classes')}
                </Link>
            </div>
        );
    }

    return (
        <div className="container mx-auto p-4 space-y-6">
            <Link to="/classes" className="btn btn-outline btn-sm mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 me-2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                </svg>
                {t('sidebar_menu_classes')}
            </Link>

            <div className="card bg-base-100 shadow-xl">
                <div className="card-body">
                    <h2 className="card-title">{t('common_label_className')}: {classGroup.class_name}</h2>
                    <p>{t('common_label_academicYear')}: {classGroup.academic_year || t('common_text_notApplicable')}</p>
                </div>
            </div>

            <div className="card bg-base-100 shadow-xl">
                <div className="card-body">
                    <h2 className="card-title">{t('sidebar_menu_students')}</h2>
                    {students.length > 0 ? (
                        <div className="overflow-x-auto">
                            <table className="table w-full">
                                <thead>
                                    <tr>
                                        <th>{t('students_form_label_firstName')}</th>
                                        <th>{t('students_form_label_lastName')}</th>
                                        <th>{t('common_label_emailAddress')}</th>
                                        <th>{t('common_label_externalId')}</th>
                                        <th>{t('common_label_actions')}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {students.map(student => (
                                        <tr key={student._id}>
                                            <td>{student.first_name}</td>
                                            <td>{student.last_name}</td>
                                            <td>{student.email || t('common_text_notApplicable')}</td>
                                            <td>{student.external_student_id || t('common_text_notApplicable')}</td>
                                            <td>
                                                <button
                                                    className="btn btn-xs btn-ghost btn-square me-1"
                                                    onClick={() => navigate('/students', { state: { studentToEdit: student } })}
                                                    title={t('students_list_button_edit_title')}
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                                                        <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
                                                    </svg>
                                                </button>
                                                <button
                                                    className="btn btn-xs btn-ghost btn-square text-error"
                                                    onClick={() => console.log(`Delete student ${student._id}`)}
                                                    title={t('students_list_button_delete_title')}
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                                                        <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25V4c.827-.05 1.66-.075 2.5-.075zM8.47 9.03a.75.75 0 00-1.06-1.06L7 8.44l-.41-1.47a.75.75 0 00-1.434.403l.485 1.733A.75.75 0 007 9.5h.5a.75.75 0 00.47-.22L8 9.03zM11.5 9.5a.75.75 0 00.47.22h.5a.75.75 0 00.675-.934l.485-1.733a.75.75 0 00-1.434-.403L11.5 8.44l-.53 1.06a.75.75 0 001.06 1.06l.53-.22.001.001z" clipRule="evenodd" />
                                                    </svg>
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <p>{t('students_list_status_noStudents')}</p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default ClassViewPage; 