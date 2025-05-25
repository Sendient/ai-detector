// src/components/Header.jsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import LocaleSelector from './LocaleSelector.jsx';
import { User, LogOut, CreditCard, ShieldCheck } from 'lucide-react';
import { useTeacherProfile } from '../hooks/useTeacherProfile';

function Header() {
    const { t } = useTranslation();
    const { user, isAuthenticated, isLoading: isAuthLoading, logout } = useKindeAuth();
    const { profile, isLoading: isLoadingProfile } = useTeacherProfile();
    const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);

    const getInitials = () => {
        const firstName = user?.givenName || '';
        const lastName = user?.familyName || '';
        if (firstName && lastName) { return `${firstName[0]}${lastName[0]}`.toUpperCase(); }
        return '?';
    };
    const initials = getInitials();

    const toggleProfileMenu = () => { setIsProfileMenuOpen(!isProfileMenuOpen); };

    const displayName = (user?.givenName && user?.familyName)
        ? `${user.givenName} ${user.familyName}`
        : t('header_default_user_name');

    const getPlanDisplayName = () => {
        if (isLoadingProfile || !isAuthenticated) return null;
        if (profile && profile.current_plan && profile.current_plan.toLowerCase() !== 'free') {
            return `${profile.current_plan} Plan`;
        }
        return t('header_free_plan', 'Free Plan');
    };

    const planDisplayName = getPlanDisplayName();

    return (
        <header className="h-16 bg-base-100 border-b border-base-300 flex items-center justify-between px-6 shrink-0 z-10 relative">
            <div></div>

            <div className="flex items-center space-x-3">
                {isAuthenticated && planDisplayName && (
                     <Link to="/subscriptions" className="btn btn-ghost btn-sm hidden sm:inline-flex items-center">
                        <ShieldCheck className="h-4 w-4 mr-1.5" /> 
                        {planDisplayName}
                    </Link>
                )}
                <div className="mr-0"> <LocaleSelector /> </div>

                {isAuthLoading ? (
                    <span className="text-sm text-gray-500">{t('header_loading')}</span>
                ) : isAuthenticated ? (
                    <>
                        <span className="text-sm font-medium text-base-content hidden sm:block">{displayName}</span>
                        <button
                            id="user-menu-button"
                            onClick={toggleProfileMenu}
                            className={`flex items-center justify-center h-9 w-9 rounded-full ${
                                initials === '?' ? 'bg-neutral text-neutral-content' : 'bg-primary text-primary-content'
                            } text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary`}
                            title={t('header_toggle_menu_title', { name: displayName })}
                            aria-expanded={isProfileMenuOpen}
                            aria-haspopup="true"
                        >
                            {initials}
                        </button>

                        {isProfileMenuOpen && (
                            <div
                                className="origin-top-right absolute right-0 mt-2 top-full w-56 rounded-md shadow-lg py-1 bg-base-100 border border-base-300 focus:outline-none z-50"
                                role="menu" aria-orientation="vertical" aria-labelledby="user-menu-button" tabIndex="-1"
                            >
                                <div className="px-4 py-2 text-sm text-gray-500 border-b border-base-300">
                                    {t('header_menu_signed_in_as')} <span className='font-medium'>{user?.email}</span>
                                </div>
                                <Link
                                    to="/profile"
                                    onClick={() => setIsProfileMenuOpen(false)}
                                    className="flex items-center px-4 py-2 text-sm text-base-content hover:bg-base-200"
                                    role="menuitem" tabIndex="-1" id="user-menu-item-0"
                                >
                                    <User className="mr-2 h-4 w-4" />
                                    {t('header_menu_profile')}
                                </Link>
                                <Link
                                   to="/subscriptions"
                                   onClick={() => setIsProfileMenuOpen(false)}
                                   className="flex items-center px-4 py-2 text-sm text-base-content hover:bg-base-200"
                                   role="menuitem" tabIndex="-1" id="user-menu-item-subscriptions"
                                >
                                   <CreditCard className="mr-2 h-4 w-4" />
                                   {t('header_menu_subscriptions', 'Subscriptions')}
                                </Link>
                                <button
                                    onClick={() => { logout(); setIsProfileMenuOpen(false); }}
                                    className="flex items-center w-full text-left px-4 py-2 text-sm text-error hover:bg-base-200"
                                    role="menuitem" tabIndex="-1" id="user-menu-item-1"
                                >
                                    <LogOut className="mr-2 h-4 w-4" />
                                    {t('header_menu_sign_out')}
                                </button>
                            </div>
                        )}
                    </>
                ) : (
                    <span className="text-sm text-neutral">{t('header_not_logged_in')}</span>
                )}
            </div>
        </header>
    );
}

export default Header;