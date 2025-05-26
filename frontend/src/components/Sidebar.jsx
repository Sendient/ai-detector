// src/components/Sidebar.jsx
import React from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
// -> Import actual icons from lucide-react
import {
    LayoutDashboard,
    FileText,
    Users, // Using 'Users' for Classes
    GraduationCap, // Using 'GraduationCap' for Students
    BarChart3,
    User,
    Puzzle, // Ensure Puzzle icon is imported
    // Settings, // Uncomment if needed later
    LogIn,
    UserPlus,
    LogOut
} from 'lucide-react';
import AppLogoDark from './Ai_DETECTOR_STRAPLINE_DARK.png'; // Import the logo
import UpgradeSideImage from '../img/Upgrade-side-image.png'; // Import the new upgrade image

// -> Remove the old PlaceholderIcon, LoginIcon, etc. component definitions

function Sidebar() {
    const { t } = useTranslation();
    const { login, register, logout, isAuthenticated, isLoading } = useKindeAuth();
    const location = useLocation();

    // -> Using same navItems structure, icons will be mapped below
    const navItems = [
        { nameKey: 'sidebar_menu_dashboard', iconName: 'LayoutDashboard', to: '/' },
        { nameKey: 'sidebar_menu_documents', iconName: 'FileText', to: '/documents' },
        { nameKey: 'sidebar_menu_classes', iconName: 'Users', to: '/classes' }, // Map key to icon name
        { nameKey: 'sidebar_menu_students', iconName: 'GraduationCap', to: '/students' }, // Map key to icon name
        { nameKey: 'sidebar_menu_analytics', iconName: 'BarChart3', to: '/analytics' }
        // { nameKey: 'sidebar_menu_integrations', iconName: 'LayoutDashboard', to: '/integrations' } // REMOVED from navItems
        // { nameKey: 'sidebar_menu_schools', iconName: 'Building', to: '/schools' }, // Example if added
        // { nameKey: 'sidebar_menu_teachers', iconName: 'UsersRound', to: '/teachers' }, // Example if added
    ];

    // -> Map icon names to components for easier use in loop
    const iconComponents = {
        LayoutDashboard, FileText, Users, GraduationCap, BarChart3, User, Puzzle, LogIn, UserPlus, LogOut // Ensure Puzzle is here
        // Add other imported icons here if needed: Building, UsersRound, etc.
    };


    return (
        // -> Updated aside classes: background, text, border - REMOVED fixed, left-0, top-0
        <aside className="w-64 h-screen bg-base-200 text-base-content flex flex-col border-r border-base-300 shadow-sm z-40 shrink-0">
            {/* Logo Area */}
            {/* -> Updated logo area classes: text, border */}
            <div className="p-4 py-5 border-b border-base-300 flex justify-center items-center"> {/* Added flex for centering */}
                {/* Replace text with image */}
                <img src={AppLogoDark} alt="AI Detector Logo" className="h-20" /> {/* Adjust height as needed */}
                {/* <h1 className="text-xl font-bold text-primary tracking-tight">{t('sidebar_app_title')}</h1>
                <p className="text-xs text-neutral mt-1">{t('sidebar_app_tagline')}</p> */}
            </div>

            {/* Navigation */}
            <nav className="flex-grow mt-4 space-y-1 px-2 overflow-y-auto">
                {navItems.map((item) => {
                    const isActive = location.pathname === item.to || (item.to !== '/' && location.pathname.startsWith(item.to));
                    // -> Get the IconComponent based on the name defined in navItems
                    const IconComponent = iconComponents[item.iconName] || LayoutDashboard; // Fallback to Dashboard icon

                    return (
                        <Link
                            key={item.nameKey}
                            to={item.to}
                            // -> Updated Link classes for active/inactive states using theme colors
                            className={`flex items-center px-3 py-2 rounded-md text-sm font-medium group ${
                                isActive
                                    ? 'bg-primary text-primary-content' // Active style
                                    : 'text-neutral hover:bg-base-300' // Inactive style (using text-neutral for contrast on base-200 bg)
                            }`}
                        >
                            {/* -> Render actual icon component with updated classes */}
                            <IconComponent
                                className={`mr-3 h-5 w-5 ${isActive ? 'text-primary-content' : 'text-neutral'}`} // Use theme text colors
                                aria-hidden="true"
                            />
                            {t(item.nameKey)}
                        </Link>
                    );
                })}
            </nav>

            {/* Auth Buttons Area */}
            {/* -> Updated border color */}
            <div className="p-2 border-t border-base-300 mt-auto space-y-1 shrink-0">
                {isLoading ? (
                    <div className="text-center text-sm text-gray-500 p-2">{t('sidebar_auth_loading')}</div>
                ) : isAuthenticated ? (
                    <>
                        {/* New Upgrade Image */}
                        <div className="px-3 py-2">
                            <img src={UpgradeSideImage} alt="Upgrade Plan" className="w-full h-auto rounded-md" />
                        </div>

                        {/* Integrations Link - Added back here with Puzzle icon */}
                        <Link
                            to="/integrations"
                            className={`flex items-center w-full px-3 py-2 text-sm font-medium rounded-md group ${
                                location.pathname === '/integrations'
                                    ? 'bg-primary text-primary-content' // Active style
                                    : 'text-neutral hover:bg-base-300' // Inactive style
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
                        {/* -> Updated button classes and icon */}
                        <button
                            onClick={() => login()}
                            className="flex items-center w-full px-3 py-2 text-sm font-medium rounded-md text-neutral hover:bg-base-300 group"
                        >
                            <LogIn className="mr-3 h-5 w-5 text-neutral" aria-hidden="true" />
                            {t('sidebar_auth_sign_in')}
                        </button>
                         {/* -> Updated button classes and icon */}
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