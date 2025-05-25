import React, { useState, useEffect } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { useTeacherProfile } from '../hooks/useTeacherProfile.js';

// Keep countries list for option values if needed, but display text will be translated
const countries = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan",
    "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina",
    "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Central African Republic",
    "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic", "Democratic Republic of the Congo",
    "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia",
    "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala",
    "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland",
    "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", "Latvia",
    "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives",
    "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia", "Montenegro",
    "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea",
    "North Macedonia", "Norway", "Oman", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines",
    "Poland", "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines",
    "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore",
    "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan",
    "Suriname", "Sweden", "Switzerland", "Syria", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay",
    "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"
];

// --- Define role keys and their corresponding backend values ---
const roleKeys = [
    "role_teacher", "role_tutor", "role_lecturer", "role_admin", "role_other"
];
const roleValues = {
    "role_teacher": "teacher", "role_tutor": "tutor", "role_lecturer": "lecturer",
    "role_admin": "admin", "role_other": "other"
};
// -------------------------------------------------------------

const initialProfileData = {
    first_name: '', last_name: '', email: '', school_name: '',
    role: 'teacher', country: '', state_county: ''
};

function ProfilePage() {
    const { t } = useTranslation();
    const { user, isAuthenticated, isLoading: isAuthLoading, getAccessToken } = useKindeAuth();
    const navigate = useNavigate();
    const { profile, isLoadingProfile, profileError, refetchProfile } = useTeacherProfile();

    const [formData, setFormData] = useState(initialProfileData);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState('');

    // const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
    const PROXY_PATH = import.meta.env.VITE_API_PROXY_PATH || '/api/v1';

    // Effect 1: Populate initial form data from Kinde user when available
    useEffect(() => {
        if (!isAuthLoading && user) {
            // console.log('ProfilePage Effect 1 - Setting initial Kinde data:', user);
            // Directly set the Kinde data, merging with initialProfileData for structure
            setFormData({
                ...initialProfileData, // Ensure all profile fields exist
                email: user.email || '',
                first_name: user.givenName || '',
                last_name: user.familyName || ''
            });
        }
    }, [user, isAuthLoading]);

    // Effect 2: Merge fetched profile data, prioritizing DB names if they exist
    useEffect(() => {
        if (!isLoadingProfile && profile) {
             // console.log('ProfilePage Effect 2 - Merging DB profile:', profile);
            // Update state based on the fetched profile
            setFormData(prev => ({
                ...prev, // Start with potentially Kinde-populated state
                ...profile, // Merge the fetched profile
                // Ensure Kinde names are kept if API profile names are empty/null
                first_name: profile.first_name || prev.first_name,
                last_name: profile.last_name || prev.last_name,
                // Always ensure Kinde email is preserved (already set in prev)
                email: prev.email
            }));
        } else if (!isLoadingProfile && profile === null) {
            // If profile fetch finished and confirmed no profile exists,
            // ensure Kinde names (already set by Effect 1) are kept.
            // No state update needed here as Effect 1 handled it.
             // console.log('ProfilePage Effect 2 - DB Profile is null, Kinde data already set.');
        }
    }, [profile, isLoadingProfile]);

    useEffect(() => {
        if (profileError) {
            setError(profileError);
        }
    }, [profileError]);

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        setError(null);
        setSuccess('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!isAuthenticated || !user?.id) {
            setError(t('messages_profile_error_authRequired'));
            return;
        }

        // Validate required fields
        if (!formData.first_name?.trim() || !formData.last_name?.trim() || 
            !formData.school_name?.trim() || !formData.role || 
            !formData.country || !formData.state_county?.trim()) {
            setError(t('messages_profile_error_fieldsRequired'));
            return;
        }

        setIsSubmitting(true);
        setError(null);
        setSuccess('');

        try {
            const token = await getAccessToken("https://api.aidetector.sendient.ai"); // Use correct audience if different
            if (!token) {
                throw new Error(t('messages_profile_error_noToken'));
            }

            // const response = await fetch(`${API_BASE_URL}/api/v1/teachers/me`, {
            const response = await fetch(`${PROXY_PATH}/teachers/me`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

            if (!response.ok) {
                let errorDetail = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) {
                     errorDetail = `${response.status} ${response.statusText}`;
                }
                // Use a more specific error message if possible
                throw new Error(t('messages_profile_error_saveFailed', { detail: errorDetail }));
            }

            // Optional: Refetch profile data to ensure UI consistency if not redirecting immediately
            // await refetchProfile(); 

            setSuccess(t('messages_profile_success_saved'));

            // Redirect to dashboard after successful save
            setTimeout(() => {
                navigate('/');
            }, 2000);
        } catch (err) {
            console.error("Profile save error:", err); // Log the error for debugging
            setError(err.message || t('messages_profile_error_unexpectedSave'));
        } finally {
            setIsSubmitting(false);
        }
    };

    // --- Log formData state before rendering ---
    // console.log('ProfilePage render - formData:', formData);

    if (isAuthLoading || isLoadingProfile) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="loading loading-spinner loading-lg text-primary"></div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return (
            <div className="alert alert-info shadow-lg">
                <InformationCircleIcon className="h-6 w-6 stroke-current shrink-0" />
                <div>
                    <h3 className="font-bold">{t('common_login_required_heading')}</h3>
                    <div className="text-xs">{t('common_login_required_message')}</div>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto p-4 sm:p-6 lg:p-8">
            <h1 className="text-xl font-semibold text-base-content mb-6">{t('profilePage_heading')}</h1>

            {/* Subscription Status Section */}
            {profile && (
                <div className="card bg-base-200 shadow-sm mb-6">
                    <div className="card-body">
                        <h2 className="card-title text-lg">{t('profilePage_subscription_title', 'My Subscription')}</h2>
                        <div className="divider my-1"></div>
                        <div className="space-y-2 text-sm">
                            <p>
                                <span className="font-medium">{t('profilePage_subscription_currentPlan', 'Current Plan')}:</span> 
                                <span className="badge badge-lg ml-2">{profile.current_plan || t('common_unknown', 'Unknown')}</span>
                            </p>
                            {profile.current_plan === 'Pro' && profile.subscription_status && (
                                <p>
                                    <span className="font-medium">{t('profilePage_subscription_status', 'Status')}:</span> 
                                    <span className={`badge badge-lg ml-2 ${profile.subscription_status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                                        {profile.subscription_status}
                                    </span>
                                </p>
                            )}
                            {profile.current_plan === 'Pro' && profile.current_period_end && (
                                <p>
                                    <span className="font-medium">{t('profilePage_subscription_renews', 'Renews/Expires on')}:</span> 
                                    <span className="ml-2">
                                        {new Date(profile.current_period_end).toLocaleDateString()}
                                    </span>
                                </p>
                            )}
                        </div>
                        <div className="card-actions justify-end mt-4">
                            {profile.current_plan === 'Pro' ? (
                                <button 
                                    onClick={() => navigate('/account/billing')} // Placeholder for Stripe Customer Portal
                                    className="btn btn-outline btn-sm"
                                >
                                    {t('profilePage_subscription_manageButton', 'Manage Subscription')}
                                </button>
                            ) : (
                                <button 
                                    onClick={() => navigate('/subscriptions')}
                                    className="btn btn-primary btn-sm"
                                >
                                    {t('profilePage_subscription_upgradeButton', 'Upgrade to Pro')}
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {success && (
                <div role="alert" className="alert alert-success mb-4 shadow-sm">
                    <CheckCircle2 className="h-6 w-6 stroke-current shrink-0" />
                    <span>{success}</span>
                </div>
            )}

            {error && (
                <div role="alert" className="alert alert-error mb-4 shadow-sm">
                    <XCircle className="h-6 w-6 stroke-current shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_firstName')}</span>
                        </label>
                        <input
                            type="text"
                            name="first_name"
                            value={formData.first_name}
                            onChange={handleInputChange}
                            className="input input-bordered w-full"
                            required
                        />
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_lastName')}</span>
                        </label>
                        <input
                            type="text"
                            name="last_name"
                            value={formData.last_name}
                            onChange={handleInputChange}
                            className="input input-bordered w-full"
                            required
                        />
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_email')}</span>
                        </label>
                        <input
                            type="email"
                            name="email"
                            value={formData.email}
                            readOnly
                            className="input input-bordered w-full"
                        />
                        <p className="mt-1 text-xs text-gray-500">{t('profilePage_form_helpText_email')}</p>
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_schoolName')}</span>
                        </label>
                        <input
                            type="text"
                            name="school_name"
                            value={formData.school_name}
                            onChange={handleInputChange}
                            className="input input-bordered w-full"
                            required
                            placeholder={t('profilePage_form_placeholder_schoolName')}
                        />
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_role')}</span>
                        </label>
                        <select
                            name="role"
                            value={formData.role}
                            onChange={handleInputChange}
                            className="select select-bordered w-full"
                            required
                        >
                            {roleKeys.map(key => (
                                <option key={key} value={roleValues[key]}>
                                    {t(key)}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_country')}</span>
                        </label>
                        <select
                            name="country"
                            value={formData.country}
                            onChange={handleInputChange}
                            className="select select-bordered w-full"
                            required
                        >
                            <option value="">{t('profilePage_form_select_countryPlaceholder')}</option>
                            {countries.map(country => (
                                <option key={country} value={country}>
                                    {country}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="form-control">
                        <label className="label">
                            <span className="label-text">{t('profilePage_form_label_stateCounty')}</span>
                        </label>
                        <input
                            type="text"
                            name="state_county"
                            value={formData.state_county}
                            onChange={handleInputChange}
                            className="input input-bordered w-full"
                            required
                        />
                    </div>
                </div>

                <div className="flex justify-end">
                    <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={isSubmitting}
                    >
                        {isSubmitting ? (
                            <>
                                <span className="loading loading-spinner loading-sm"></span>
                                {t('common_saving')}
                            </>
                        ) : (
                            t('profilePage_form_button_save')
                        )}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default ProfilePage; 