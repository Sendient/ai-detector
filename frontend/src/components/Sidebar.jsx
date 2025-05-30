// src/components/Sidebar.jsx
import React from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
// -> Import actual icons from lucide-react
import {
    LayoutDashboard,
    FileText,
    Users, // Using 'Users' for Classes
    GraduationCap, // Using 'GraduationCap' for Students
    BarChart3,
    User,
    Puzzle, // Ensure Puzzle icon is imported
    UserCog, // <<< ADDED ICON FOR ADMIN
    // Settings, // Uncomment if needed later
    LogIn,
    UserPlus,
    LogOut
} from 'lucide-react';
import AppLogoDark from '../img/SMARTDETECTOR_STRAPLINE_DARK.png'; // Import the new logo
import UpgradeSideImage from '../img/Upgrade-Side-Image.png'; // Import the new upgrade image

// -> Remove the old PlaceholderIcon, LoginIcon, etc. component definitions

function Sidebar() {
    const { t } = useTranslation();
    const { login, register, logout, isAuthenticated, isLoading: kindeIsLoading } = useKindeAuth();
    const { currentUser, loading: authContextLoading } = useAuth();
    const location = useLocation();

    // Base navigation items for the top section
    const topNavItems = [
        { nameKey: 'sidebar_menu_dashboard', iconName: 'LayoutDashboard', to: '/' },
        { nameKey: 'sidebar_menu_documents', iconName: 'FileText', to: '/documents' },
        { nameKey: 'sidebar_menu_classes', iconName: 'Users', to: '/classes' },
        { nameKey: 'sidebar_menu_students', iconName: 'GraduationCap', to: '/students' },
        { nameKey: 'sidebar_menu_analytics', iconName: 'BarChart3', to: '/analytics' }
    ];

    // Icon mapping
    const iconComponents = {
        LayoutDashboard, FileText, Users, GraduationCap, BarChart3, User, Puzzle, UserCog, LogIn, UserPlus, LogOut
    };

    // Use combined loading state
    const overallIsLoading = kindeIsLoading || authContextLoading;

    return (
        <aside className="w-64 h-screen bg-base-200 text-base-content flex flex-col border-r border-base-300 shadow-sm z-40 shrink-0">
            <div className="p-4 py-5 border-b border-base-300 flex justify-center items-center">
                <img src={AppLogoDark} alt="Smart Detector Logo" />
            </div>

            {/* Top Navigation Items */}
            <nav className="flex-grow mt-4 space-y-1 px-2 overflow-y-auto">
                {topNavItems.map((item) => {
                    const isActive = location.pathname === item.to || (item.to !== '/' && location.pathname.startsWith(item.to));
                    const IconComponent = iconComponents[item.iconName] || LayoutDashboard;
                    return (
                        <Link
                            key={item.nameKey}
                            to={item.to}
                            className={`flex items-center px-3 py-2 rounded-md text-sm font-medium group ${
                                isActive
                                    ? 'bg-primary text-primary-content'
                                    : 'text-neutral hover:bg-base-300'
                            }`}
                        >
                            <IconComponent
                                className={`mr-3 h-5 w-5 ${isActive ? 'text-primary-content' : 'text-neutral'}`}
                                aria-hidden="true"
                            />
                            {t(item.nameKey)}
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom Auth/Admin/Integrations Area */}
            <div className="p-2 border-t border-base-300 mt-auto space-y-1 shrink-0">
                {overallIsLoading ? (
                    <div className="text-center text-sm text-gray-500 p-2">{t('sidebar_auth_loading')}</div>
                ) : isAuthenticated ? (
                    <>
                        <a href="https://www.smarteducator.ai/sign-up/" target="_blank" rel="noopener noreferrer">
                            <div className="px-3 py-2">
                                <img src={UpgradeSideImage} alt="Upgrade Plan" className="w-full h-auto rounded-md" />
                            </div>
                        </a>

                        {/* Conditionally render Admin link here */}
                        {!authContextLoading && currentUser && currentUser.is_administrator && (
                            <Link
                                to="/admin"
                                className={`flex items-center w-full px-3 py-2 text-sm font-medium rounded-md group ${
                                    location.pathname === '/admin'
                                        ? 'bg-primary text-primary-content'
                                        : 'text-neutral hover:bg-base-300'
                                }`}
                            >
                                <UserCog className={`mr-3 h-5 w-5 ${location.pathname === '/admin' ? 'text-primary-content' : 'text-neutral'}`} aria-hidden="true" />
                                {t('sidebar_menu_admin')}
                            </Link>
                        )}

                        {/* Integrations Link */}
                        <Link
                            to="/integrations"
                            className={`flex items-center w-full px-3 py-2 text-sm font-medium rounded-md group ${
                                location.pathname === '/integrations'
                                    ? 'bg-primary text-primary-content'
                                    : 'text-neutral hover:bg-base-300'
                            }`}
                        >
                            <Puzzle className={`mr-3 h-5 w-5 ${location.pathname === '/integrations' ? 'text-primary-content' : 'text-neutral'}`} aria-hidden="true" />
                            {t('sidebar_menu_integrations')}
                        </Link>

                        {/* Sign Out Button */}
                        <button
                            onClick={() => logout()}
                            className="flex items-center w-full px-3 py-2 text-sm font-medium rounded-md text-neutral hover:bg-base-300 group"
                        >
                            <LogOut className="mr-3 h-5 w-5 text-neutral" aria-hidden="true" />
                            {t('sidebar_auth_sign_out')}
                        </button>
                    </>
                ) : (
                    <>
                        <button
                            onClick={() => login()}
                            className="flex items-center w-full px-3 py-2 text-sm font-medium rounded-md text-neutral hover:bg-base-300 group"
                        >
                            <LogIn className="mr-3 h-5 w-5 text-neutral" aria-hidden="true" />
                            {t('sidebar_auth_sign_in')}
                        </button>
                        <button
                            onClick={() => register()}
                            className="flex items-center w-full px-3 py-2 text-sm font-medium rounded-md text-neutral hover:bg-base-300 group"
                        >
                            <UserPlus className="mr-3 h-5 w-5 text-neutral" aria-hidden="true" />
                            {t('sidebar_auth_register')}
                        </button>
                    </>
                )}
            </div>
        </aside>
    );
}

export default Sidebar;