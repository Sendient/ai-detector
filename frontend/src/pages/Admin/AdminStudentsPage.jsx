import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/apiService';
import { TrashIcon, SortAscendingIcon, SortDescendingIcon, SearchIcon } from '@heroicons/react/outline'; // Ensure Heroicons v1 imports

const AdminStudentsPage = () => {
  const { currentUser, isLoading: authLoading } = useAuth();
  const [students, setStudents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'last_name', direction: 'ascending' });
  const navigate = useNavigate();

  useEffect(() => {
    if (!authLoading && currentUser && !currentUser.is_administrator) {
      navigate('/unauthorized');
    }
  }, [currentUser, authLoading, navigate]);

  useEffect(() => {
    const fetchStudentsData = async () => {
      if (!currentUser || !currentUser.is_administrator) {
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError('');
      try {
        const response = await apiService.get('/api/v1/admin/students');
        if (response.data && Array.isArray(response.data)) {
          setStudents(response.data);
        } else {
          console.error("Fetched data is not an array or is null:", response.data);
          setStudents([]);
          setError("Failed to load student data in expected format.");
        }
      } catch (err) {
        console.error("Error fetching students:", err);
        const errorMsg = err.response?.data?.detail || err.message || 'An unexpected error occurred while fetching students.';
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        setStudents([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStudentsData();
  }, [currentUser]);

  const handleDeleteStudent = async (studentId, studentName) => {
    if (!studentId) {
      setError("Cannot delete student: ID is missing.");
      return;
    }
    if (window.confirm(`Are you sure you want to delete student ${studentName} (ID: ${studentId})? This action cannot be undone.`)) {
      try {
        await apiService.delete(`/api/v1/admin/students/${studentId}`);
        setStudents(prevStudents => prevStudents.filter(student => student.id !== studentId));
        setError(''); // Clear any previous error
      } catch (err) {
        console.error("Error deleting student:", err);
        const errorMsg = err.response?.data?.detail || err.message || 'An unexpected error occurred during deletion.';
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
      }
    }
  };

  const requestSort = (key) => {
    let direction = 'ascending';
    if (sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending';
    }
    setSortConfig({ key, direction });
  };

  const getSortIcon = (columnKey) => {
    if (sortConfig.key === columnKey) {
      return sortConfig.direction === 'ascending' ? <SortAscendingIcon className="w-4 h-4 inline ml-1" /> : <SortDescendingIcon className="w-4 h-4 inline ml-1" />;
    }
    return null;
  };

  const filteredAndSortedStudents = useMemo(() => {
    let filtered = [...students];
    if (searchTerm) {
      const lowerSearchTerm = searchTerm.toLowerCase();
      filtered = filtered.filter(student =>
        (student.teacher_id && student.teacher_id.toLowerCase().includes(lowerSearchTerm)) ||
        (student.email && student.email.toLowerCase().includes(lowerSearchTerm)) ||
        (student.first_name && student.first_name.toLowerCase().includes(lowerSearchTerm)) ||
        (student.last_name && student.last_name.toLowerCase().includes(lowerSearchTerm))
      );
    }

    if (sortConfig.key) {
      filtered.sort((a, b) => {
        const valA = a[sortConfig.key];
        const valB = b[sortConfig.key];

        if (valA === null || valA === undefined) return sortConfig.direction === 'ascending' ? -1 : 1;
        if (valB === null || valB === undefined) return sortConfig.direction === 'ascending' ? 1 : -1;
        
        if (typeof valA === 'string' && typeof valB === 'string') {
            return sortConfig.direction === 'ascending' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else {
            if (valA < valB) return sortConfig.direction === 'ascending' ? -1 : 1;
            if (valA > valB) return sortConfig.direction === 'ascending' ? 1 : -1;
            return 0;
        }
      });
    }
    return filtered;
  }, [students, searchTerm, sortConfig]);

  if (authLoading || (isLoading && students.length === 0)) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (!currentUser || !currentUser.is_administrator) {
    return (
      <div className="p-4 text-center">
        <p className="text-error">You are not authorized to view this page.</p>
        <p>If you believe this is an error, please contact support.</p>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-center">Manage Students</h1>
      
      {error && (
        <div role="alert" className="alert alert-error mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2 2m2-2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Error: {error}</span>
        </div>
      )}

      <div className="mb-4 p-4 card bg-base-200 shadow-xl">
        <div className="flex items-center space-x-2">
          <SearchIcon className="w-5 h-5 text-gray-500" />
          <input
            type="text"
            placeholder="Search by Teacher ID, Email, First or Last Name..."
            className="input input-bordered w-full"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="overflow-x-auto">
            {isLoading && students.length === 0 && <p>Loading students...</p>}
            {!isLoading && students.length === 0 && !error && <p>No students found.</p>}
            {students.length > 0 && (
              <table className="table table-zebra table-sm w-full">
                <thead>
                  <tr>
                    <th onClick={() => requestSort('teacher_id')} className="cursor-pointer">
                      Teacher ID {getSortIcon('teacher_id')}
                    </th>
                    <th onClick={() => requestSort('first_name')} className="cursor-pointer">
                      First Name {getSortIcon('first_name')}
                    </th>
                    <th onClick={() => requestSort('last_name')} className="cursor-pointer">
                      Last Name {getSortIcon('last_name')}
                    </th>
                    <th onClick={() => requestSort('email')} className="cursor-pointer">
                      Email {getSortIcon('email')}
                    </th>
                    <th>External ID</th>
                    <th>Descriptor</th>
                    <th>Year Group</th>
                    <th>Created At</th>
                    <th>Updated At</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAndSortedStudents.map((student) => (
                    <tr key={student.id || student.email} className="hover">
                      <td>{student.teacher_id}</td>
                      <td>{student.first_name}</td>
                      <td>{student.last_name}</td>
                      <td>{student.email}</td>
                      <td>{student.external_student_id ?? 'N/A'}</td>
                      <td>{student.descriptor ?? 'N/A'}</td>
                      <td>{student.year_group ?? 'N/A'}</td>
                      <td>{student.created_at ? new Date(student.created_at).toLocaleDateString() : 'N/A'}</td>
                      <td>{student.updated_at ? new Date(student.updated_at).toLocaleDateString() : 'N/A'}</td>
                      <td>
                        {student.id ? (
                          <button 
                            onClick={() => handleDeleteStudent(student.id, `${student.first_name} ${student.last_name}`)}
                            className="btn btn-ghost btn-xs text-red-500 hover:text-red-700"
                            aria-label={`Delete student ${student.first_name} ${student.last_name}`}
                          >
                            <TrashIcon className="w-4 h-4" />
                          </button>
                        ) : (
                          <span className="text-xs text-gray-500">(ID Missing)</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminStudentsPage; 