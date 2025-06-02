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
        if (!profileData) {
            console.log('[useTeacherProfile] checkProfileCompletion: profileData is null or undefined, returning false.');
            return false;
        }
        const isComplete = Boolean(
            profileData.first_name?.trim() &&
            profileData.last_name?.trim() &&
            profileData.school_name?.trim() &&
            profileData.role &&
            profileData.country &&
            profileData.state_county?.trim()
        );
        console.log('[useTeacherProfile] checkProfileCompletion called with:', profileData);
        console.log('[useTeacherProfile] Fields check: first_name:', !!profileData.first_name?.trim(), ', last_name:', !!profileData.last_name?.trim(), ', school_name:', !!profileData.school_name?.trim(), ', role:', !!profileData.role, ', country:', !!profileData.country, ', state_county:', !!profileData.state_county?.trim());
        console.log('[useTeacherProfile] checkProfileCompletion result:', isComplete);
        return isComplete;
    }, []);

    const fetchProfile = useCallback(async () => {
        if (!isAuthenticated || isAuthLoading || !user?.id) {
            console.log('[useTeacherProfile] Skipping profile fetch:', { isAuthenticated, isAuthLoading, hasUserId: !!user?.id });
            setProfile(null);
            setIsLoadingProfile(false);
            setIsProfileComplete(false);
            return;
        }
        console.log('[useTeacherProfile] Starting fetchProfile...');
        setIsLoadingProfile(true);
        setProfileError(null);

        try {
            const token = await getAccessToken("https://api.aidetector.sendient.ai");
            if (!token) {
                console.error('[useTeacherProfile] Failed to get access token.');
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
                    console.log('[useTeacherProfile] Profile not found (404). Setting profile to null and incomplete.');
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
                    console.error(`[useTeacherProfile] Error fetching profile: ${errorDetail}`);
                    throw new Error(t('header_error_fetch_failed', { detail: errorDetail }));
                }
            } else {
                const data = await response.json();
                console.log('[useTeacherProfile] Profile data fetched successfully:', data);
                setProfile(data);
                // Explicitly call checkProfileCompletion and log its result before setting state
                const completionStatus = checkProfileCompletion(data);
                console.log(`[useTeacherProfile] About to call setIsProfileComplete with: ${completionStatus}`);
                setIsProfileComplete(completionStatus);
            }
        } catch (err) {
            console.error('[useTeacherProfile] Catch block in fetchProfile:', err.message);
            setProfileError(err.message);
            setProfile(null);
            setIsProfileComplete(false);
        } finally {
            console.log('[useTeacherProfile] fetchProfile finally block. Setting isLoadingProfile to false.');
            setIsLoadingProfile(false);
        }
    }, [isAuthenticated, isAuthLoading, user?.id, getAccessToken, t, checkProfileCompletion, API_BASE_URL]);

    useEffect(() => {
        console.log('[useTeacherProfile] Outer useEffect triggered. isAuthenticated:', isAuthenticated, 'user?.id:', user?.id, 'isAuthLoading:', isAuthLoading);
        if (isAuthenticated && user?.id) {
            console.log('[useTeacherProfile] Outer useEffect: Calling fetchProfile.');
            fetchProfile();
        } else if (!isAuthLoading && !isAuthenticated) {
            console.log('[useTeacherProfile] Outer useEffect: User not authenticated and auth not loading. Resetting profile state.');
            setIsLoadingProfile(false);
            setProfile(null);
            setProfileError(null);
            setIsProfileComplete(false);
        }
    }, [isAuthenticated, user?.id, isAuthLoading, fetchProfile]);

    // Log state changes for debugging
    useEffect(() => {
        console.log('[useTeacherProfile] State changed: isProfileComplete:', isProfileComplete);
    }, [isProfileComplete]);
    useEffect(() => {
        console.log('[useTeacherProfile] State changed: isLoadingProfile:', isLoadingProfile);
    }, [isLoadingProfile]);
    useEffect(() => {
        console.log('[useTeacherProfile] State changed: profile:', profile);
    }, [profile]);

    return {
        profile,
        isLoadingProfile,
        profileError,
        isProfileComplete,
        refetchProfile: fetchProfile
    };
} 