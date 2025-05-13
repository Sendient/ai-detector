import { useState, useEffect, useCallback } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';

export function useTeacherProfile() {
    const { t } = useTranslation();
    const { user, isAuthenticated, isLoading: isAuthLoading, getAccessToken } = useKindeAuth();
    const [profile, setProfile] = useState(null);
    const [isLoadingProfile, setIsLoadingProfile] = useState(true);
    const [profileError, setProfileError] = useState(null);
    const [isProfileComplete, setIsProfileComplete] = useState(false);
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

    const checkProfileCompletion = useCallback((profileData) => {
        if (!profileData) return false;
        return Boolean(
            profileData.first_name?.trim() &&
            profileData.last_name?.trim() &&
            profileData.school_name?.trim() &&
            profileData.role &&
            profileData.country &&
            profileData.state_county?.trim()
        );
    }, []);

    const fetchProfile = useCallback(async () => {
        if (!isAuthenticated || isAuthLoading || !user?.id) {
            console.log('[Profile Hook Debug] Skipping profile fetch:', {
                isAuthenticated,
                isAuthLoading,
                hasUserId: !!user?.id,
                timestamp: new Date().toISOString()
            });
            setProfile(null);
            setIsLoadingProfile(false);
            setIsProfileComplete(false);
            return;
        }

        setIsLoadingProfile(true);
        setProfileError(null);

        try {
            const token = await getAccessToken("https://api.aidetector.sendient.ai");
            
            if (!token) {
                throw new Error(t('header_error_no_token'));
            }

            const response = await fetch(`${API_BASE_URL}/api/v1/teachers/me`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                if (response.status === 404) {
                    // Profile doesn't exist yet - this is expected for new users
                    setProfile(null);
                    setIsProfileComplete(false);
                } else {
                    let errorDetail = `HTTP ${response.status}`;
                    try {
                        const errorData = await response.json();
                        errorDetail = errorData.detail || errorDetail;
                    } catch (e) {
                        errorDetail = `${response.status} ${response.statusText}`;
                    }
                    throw new Error(t('header_error_fetch_failed', { detail: errorDetail }));
                }
            } else {
                const data = await response.json();
                setProfile(data);
                setIsProfileComplete(checkProfileCompletion(data));
            }
        } catch (err) {
            console.error('[Profile Hook Debug] Profile fetch error:', {
                message: err.message,
                stack: err.stack,
                timestamp: new Date().toISOString()
            });
            setProfileError(err.message);
            setProfile(null);
            setIsProfileComplete(false);
        } finally {
            setIsLoadingProfile(false);
        }
    }, [isAuthenticated, isAuthLoading, user?.id, getAccessToken, t, checkProfileCompletion, API_BASE_URL]);

    useEffect(() => {
        if (isAuthenticated && user?.id) {
            fetchProfile();
        } else if (!isAuthLoading && !isAuthenticated) {
            setIsLoadingProfile(false);
            setProfile(null);
            setProfileError(null);
            setIsProfileComplete(false);
        }
    }, [isAuthenticated, user?.id, isAuthLoading, fetchProfile]);

    return {
        profile,
        isLoadingProfile,
        profileError,
        isProfileComplete,
        refetchProfile: fetchProfile
    };
} 