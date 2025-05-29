import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext'; // Assuming AuthContext provides user info
import { useNavigate, Link } from 'react-router-dom';
import { ShieldCheckIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
// You might want to create a specific API service for admin actions
// import adminApiService from '../services/adminApiService'; 

const AdminPage = () => {
    const { currentUser, loading } = useAuth();
    const navigate = useNavigate();
    const [adminData, setAdminData] = useState(null);
    const [error, setError] = useState('');
    const { t } = useTranslation();

    useEffect(() => {
        // Redirect if not admin or still loading
        if (!loading && (!currentUser || !currentUser.is_administrator)) {
            navigate('/'); // Redirect to home or a 'not authorized' page
            return;
        }

        // Fetch admin-specific data if the user is an admin
        if (currentUser && currentUser.is_administrator) {
            // Example: Fetch admin overview data
            /* 
            const fetchAdminOverview = async () => {
                try {
                    // const data = await adminApiService.getOverview(); 
                    // setAdminData(data);
                    setAdminData({ overview: "Admin overview data loaded successfully!" }); // Placeholder
                } catch (err) {
                    setError('Failed to load admin data: ' + (err.response?.data?.detail || err.message));
                }
            };
            fetchAdminOverview();
            */
           // For now, just set placeholder data
           setAdminData({ overview: "Welcome to the Admin Dashboard. More features coming soon!" });
        }
    }, [currentUser, loading, navigate]);

    if (loading || (!currentUser || !currentUser.is_administrator)) {
        // Show loading indicator or null while checking auth/admin status or redirecting
        return <div className="p-8 text-center">Loading or checking admin privileges...</div>;
    }

    // Placeholder data for cards - you can expand this later
    const adminCards = [
        {
            id: 'students',
            titleKey: 'admin_card_students_title', // e.g., "Manage Students"
            descriptionKey: 'admin_card_students_description', // e.g., "View, edit, or manage student accounts."
            // icon: Users, // Example icon
            linkTo: '/admin/students' // Example link
        },
        {
            id: 'classes',
            titleKey: 'admin_card_classes_title', // e.g., "Manage Classes"
            descriptionKey: 'admin_card_classes_description', // e.g., "Administer class sections and enrollments."
            // icon: Library, // Example icon
            linkTo: '/admin/classes' // Example link
        },
        {
            id: 'documents',
            titleKey: 'admin_card_documents_title', // e.g., "Manage Documents"
            descriptionKey: 'admin_card_documents_description', // e.g., "Oversee all submitted documents and reports."
            // icon: FileText, // Example icon
            linkTo: '/admin/documents' // Example link
        }
    ];

    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8 text-primary">{t('admin_page_title', 'Admin Dashboard')}</h1>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {adminCards.map((card) => (
                    <div key={card.id} className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow duration-300">
                        {/* Card Icon (optional) - uncomment and style if you add icons
                        {card.icon && (
                            <figure className="px-10 pt-10">
                                <card.icon size={48} className="text-primary" />
                            </figure>
                        )}
                        */}
                        <div className="card-body">
                            <h2 className="card-title text-xl font-semibold">{t(card.titleKey, `Manage ${card.id.charAt(0).toUpperCase() + card.id.slice(1)}`)}</h2>
                            <p className="text-sm text-base-content/80">{t(card.descriptionKey, `Manage all ${card.id}.`)}</p>
                            <div className="card-actions justify-end mt-4">
                                <Link to={card.linkTo} className="btn btn-primary btn-sm">
                                    {t('admin_card_button_go', 'Go to ' + card.id)}
                                </Link>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default AdminPage; 