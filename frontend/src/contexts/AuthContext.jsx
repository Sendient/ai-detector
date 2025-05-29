import React, { createContext, useContext, useState, useEffect } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import apiService from '../services/apiService'; // Assuming you have a general apiService

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const { isAuthenticated, user, isLoading: kindeIsLoading, getToken } = useKindeAuth();
    const [currentUser, setCurrentUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchUserProfile = async () => {
            if (isAuthenticated && user) {
                try {
                    setLoading(true);
                    // console.log("AuthProvider: Fetching user profile from /teachers/me");
                    const token = await getToken();
                    console.log("AuthProvider: Kinde Access Token for /teachers/me:", token ? "Token Present (see details in network tab or if Kinde logs it)" : "Token Undefined/Null", token);
                    
                    if (!token) {
                        throw new Error("AuthProvider: Kinde token is null or undefined. Cannot fetch profile.");
                    }

                    apiService.setAuthToken(token); // Ensure apiService has the token
                    
                    let profileData;
                    try {
                        profileData = await apiService.get('/api/v1/teachers/me');
                        // console.log("AuthProvider: Initial /teachers/me GET successful:", profileData);
                        console.log("AuthProvider: Initial /teachers/me GET successful. Full Profile Data:", JSON.parse(JSON.stringify(profileData)));
                        console.log("AuthProvider: profileData.is_administrator directly after fetch:", profileData?.is_administrator);
                    } catch (initialError) {
                        if (initialError.response && initialError.response.status === 404) {
                            console.warn("AuthProvider: Initial /teachers/me call failed with 404. Attempting to create/update profile via PUT, then retrying GET.");
                            
                            // Attempt to create/update the profile via PUT /teachers/me
                            try {
                                console.log("AuthProvider: Attempting PUT /teachers/me to create/sync profile.");

                                // Robust handling for names and school_name
                                const payload_first_name = user.givenName && user.givenName.trim() !== '' ? user.givenName.trim() : undefined;
                                const payload_last_name = user.familyName && user.familyName.trim() !== '' ? user.familyName.trim() : undefined;
                                const payload_school_name = (user.schoolName && user.schoolName.trim() !== '') ? user.schoolName.trim() : 'Not Specified';

                                const minimalProfilePayload = {
                                    first_name: payload_first_name,
                                    last_name: payload_last_name,
                                    school_name: payload_school_name,
                                    role: 'teacher',
                                    country: 'Not Specified',
                                    state_county: 'Not Specified'
                                };
                                // Ensure token is set for apiService if it's not global or sticky
                                // apiService.setAuthToken(token); // Already set before the initial GET
                                
                                // +++ ADDED: Log auth header right before PUT +++
                                console.log("AuthProvider: Auth header before PUT /teachers/me:", apiService.defaults.headers.common['Authorization'] ? "Present" : "MISSING OR UNDEFINED", apiService.defaults.headers.common['Authorization']);
                                // +++ ADDED: Log the payload being sent +++
                                console.log("AuthProvider: Sending minimalProfilePayload to PUT /teachers/me:", minimalProfilePayload);
                                // +++ ADDED: Log the full URL +++
                                console.log("AuthProvider: Full PUT URL should be:", apiService.defaults.baseURL + '/api/v1/teachers/me');

                                const putResponse = await apiService.put('/api/v1/teachers/me', minimalProfilePayload);
                                console.log("AuthProvider: PUT /teachers/me successful or finished:", putResponse);

                                // After successful PUT, retry GET /teachers/me
                                console.log("AuthProvider: Retrying GET /teachers/me after PUT.");
                                // apiService.setAuthToken(token); // Still set
                                profileData = await apiService.get('/api/v1/teachers/me');
                                console.log("AuthProvider: Subsequent GET /teachers/me successful after PUT:", profileData);

                            } catch (putOrSecondGetError) {
                                console.error("AuthProvider: Error during PUT /teachers/me or subsequent GET /teachers/me:", putOrSecondGetError);
                                // If PUT or the second GET fails, we'll fall through to the main error handling
                                // which uses Kinde user data as a fallback.
                                throw putOrSecondGetError; // Re-throw to be caught by the outer catch block
                            }
                        } else {
                            console.error("AuthProvider: Initial GET /teachers/me failed with non-404 error:", initialError);
                            throw initialError; // Re-throw other errors immediately
                        }
                    }
                    
                    // console.log("AuthProvider: Profile data received:", profileData);
                    let isAdminFromKinde = false;
                    if (user && user.roles && Array.isArray(user.roles)) {
                        // Kinde roles might be an array of strings or an array of objects with a 'key' property
                        isAdminFromKinde = user.roles.some(role => 
                            (typeof role === 'string' && role.toLowerCase() === 'admin') || 
                            (typeof role === 'object' && role !== null && role.key?.toLowerCase() === 'admin')
                        );
                    }
                    console.log("AuthProvider: Determined isAdminFromKinde:", isAdminFromKinde);

                    // Fallback: If profileData is still undefined (e.g., PUT and subsequent GET failed),
                    // use Kinde details directly. This part of the logic can remain similar.
                    if (!profileData) {
                        console.warn("AuthProvider: Profile data is still undefined after all attempts. Falling back to Kinde user details.");
                        setCurrentUser({
                            kinde_id: user?.id || null,
                            email: user?.email || null,
                            first_name: user?.givenName || null,
                            last_name: user?.familyName || null,
                            // is_administrator: isAdminFromKinde, // This was the problematic part
                            // For fallback, if we couldn't get from backend, is_administrator should be false or undetermined
                            // unless we decode the token here (which is a more advanced fallback)
                            is_administrator: false, // Safer fallback if backend sync failed
                            picture: user?.picture || null,
                            // Add a flag to indicate this is fallback data
                            isFallback: true 
                        });

                        if (err && err.response && err.response.status === 404) {
                            setError('User profile not found or created in DB via /teachers/me. Using Kinde data as fallback.'); 
                        } else if (err) {
                            setError(err.message || 'Failed to fetch or create user profile.');
                        } else {
                            // This case might occur if PUT succeeded but the final GET failed for a non-404 reason
                            setError('Profile created/updated, but failed to fetch final state. Using Kinde data as fallback.');
                        }
                    } else {
                        // This means profileData was successfully fetched at some point
                        setCurrentUser(profileData);
                        setError(null);
                    }

                } catch (err) {
                    console.error("AuthProvider: Error fetching user profile for /teachers/me:", err);
                    console.log("AuthProvider: Kinde 'user' object in catch block:", user); // Log the Kinde user object

                    let isAdminFromKinde = false;
                    if (user && user.roles && Array.isArray(user.roles)) {
                        // Kinde roles might be an array of strings or an array of objects with a 'key' property
                        isAdminFromKinde = user.roles.some(role => 
                            (typeof role === 'string' && role.toLowerCase() === 'admin') || 
                            (typeof role === 'object' && role !== null && role.key?.toLowerCase() === 'admin')
                        );
                    }
                    console.log("AuthProvider: Determined isAdminFromKinde:", isAdminFromKinde);

                    setCurrentUser({
                        kinde_id: user?.id || null,
                        email: user?.email || null,
                        first_name: user?.givenName || null,
                        last_name: user?.familyName || null,
                        is_administrator: isAdminFromKinde,
                        picture: user?.picture || null
                    });

                    if (err.response && err.response.status === 404) {
                         setError('User profile not found in DB via /teachers/me. Using Kinde data as fallback.'); 
                    } else {
                        setError(err.message || 'Failed to fetch user profile from /teachers/me');
                    }
                } finally {
                    setLoading(false);
                }
            } else if (!kindeIsLoading) {
                // Not authenticated and Kinde is not loading anymore
                setCurrentUser(null);
                setLoading(false);
                setError(null);
            }
        };

        fetchUserProfile();
    }, [isAuthenticated, user, kindeIsLoading, getToken]);

    // This effect logs when currentUser changes, for debugging
    useEffect(() => {
        // console.log("AuthProvider: currentUser state updated:", currentUser);
        console.log("AuthProvider: currentUser state updated. Full currentUser:", JSON.parse(JSON.stringify(currentUser)));
        console.log("AuthProvider: currentUser.is_administrator from state:", currentUser?.is_administrator);
        window.currentUserForDebug = currentUser; // Temporarily expose for debugging
    }, [currentUser]);
    
    // This effect logs when loading state changes
    useEffect(() => {
        // console.log("AuthProvider: loading state updated:", loading);
    }, [loading]);

    return (
        <AuthContext.Provider value={{ currentUser, setCurrentUser, loading, setLoading, error }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}; 