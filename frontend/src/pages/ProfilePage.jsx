import React, { useState, useEffect } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, XCircle, ShieldCheckIcon } from 'lucide-react';
import { useTeacherProfile } from '../hooks/useTeacherProfile.js';
import { useAuth } from '../contexts/AuthContext';

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
    const { profile, isLoadingProfile, profileError, refetchProfile, isProfileComplete } = useTeacherProfile();
    const { currentUser, loading: authContextLoading } = useAuth();

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
            const token = await getAccessToken("https://api.aidetector.sendient.ai");
            if (!token) {
                throw new Error(t('messages_profile_error_noToken'));
            }

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
                throw new Error(t('messages_profile_error_saveFailed', { detail: errorDetail }));
            }

            await refetchProfile();
            
            setSuccess(t('messages_profile_success_saved'));
            console.log("[ProfilePage] Profile saved and refetchProfile called. Success message set.");
            setIsSubmitting(false);

        } catch (err) {
            console.error("Profile save error:", err);
            setError(err.message || t('messages_profile_error_unexpectedSave'));
            setIsSubmitting(false);
        }
    };

    if (isAuthLoading || isLoadingProfile || authContextLoading) {
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

            {/* Display Administrator Status if applicable */}
            {currentUser && currentUser.is_administrator && (
                <div 
                    role="alert" 
                    className="alert bg-blue-100 border-blue-500 text-blue-700 mb-6 shadow-md flex items-center"
                >
                    <ShieldCheckIcon className="h-6 w-6 stroke-current shrink-0 mr-3 text-blue-600" />
                    <div>
                        <h3 className="font-bold text-blue-800">{t('profilePage_adminStatus_heading')}</h3>
                        <p className="text-sm text-blue-700">{t('profilePage_adminStatus_message')}</p>
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

            {/* Personal Information Card - Remains largely the same, but Account Created On will be moved */}
            <div className="card bg-base-100 shadow-md mb-6"> {/* Added mb-6 for spacing between cards */}
                <div className="card-body">
                    <h2 className="card-title text-lg">{t('profilePage_personalInfo_title', 'Personal Information')}</h2>
                    <div className="divider my-1"></div>
                    <form onSubmit={handleSubmit} className="space-y-4"> {/* Moved form tag here, simpler structure */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4"> {/* Reverted to md:grid-cols-2 */}
                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_firstName')} <span className="text-red-500">*</span></span>
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

                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_lastName')} <span className="text-red-500">*</span></span>
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

                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_email')}</span>
                                </label>
                                <input
                                    type="email"
                                    name="email"
                                    value={formData.email}
                                    readOnly
                                    className="input input-bordered w-full bg-base-200 text-base-content/70 cursor-not-allowed"
                                />
                                <p className="mt-1 text-xs text-gray-500">{t('profilePage_form_helpText_email')}</p>
                            </div>

                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_schoolName')} <span className="text-red-500">*</span></span>
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

                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_role')} <span className="text-red-500">*</span></span>
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

                            <div className="form-control w-full">
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_country')} <span className="text-red-500">*</span></span>
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

                            <div className="form-control w-full md:col-span-2"> {/* State/County reverted to md:col-span-2 */}
                                <label className="label">
                                    <span className="label-text">{t('profilePage_form_label_stateCounty')} <span className="text-red-500">*</span></span>
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
                        <div className="text-sm text-gray-600 md:col-span-2 mb-4">
                            <span className="text-red-500">*</span> {t('profilePage_form_mandatory_key', 'Indicates a required field')}
                        </div>
                        <div className="card-actions justify-end pt-4 md:col-span-2"> {/* Ensure button spans if needed */}
                            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                                {isSubmitting ? (
                                    <>
                                        <span className="loading loading-spinner"></span>
                                        {t('profilePage_button_saving')}
                                    </>
                                ) : t('profilePage_button_saveChanges')}
                            </button>
                        </div>
                    </form>
                </div>
            </div>

            {/* My Account Card - Includes Subscription Info */}
            <div className="card bg-base-100 shadow-md mb-6">
                <div className="card-body">
                    <h2 className="card-title text-lg">{t('profilePage_myAccount_title', 'My Account')}</h2>
                    <div className="divider my-1"></div>
                    <div className="space-y-2">
                        <div>
                            <span className="font-medium">{t('profilePage_account_createdOn', 'Account Created On:')}</span> 
                            {profile?.created_at ? new Date(profile.created_at).toLocaleString() : t('common_notAvailable')}
                        </div>
                        <div>
                            <span className="font-medium">{t('profilePage_subscription_currentPlan', 'Current Plan:')}</span> 
                            {profile?.current_plan ? t(`subscriptionPlan_${profile.current_plan.toLowerCase()}`, profile.current_plan) : t('common_notAvailable')}
                        </div>
                        {/* MODIFIED: Display Plan Limits */}
                        {profile?.current_plan && profile.current_plan !== 'Schools' && (
                            <>
                                <div>
                                    <span className="font-medium">{t('profilePage_subscription_wordLimit', 'Monthly Word Limit:')}</span> 
                                    {profile.current_plan_word_limit !== null && profile.current_plan_word_limit !== undefined 
                                        ? profile.current_plan_word_limit.toLocaleString() 
                                        : t('profilePage_subscription_unlimited', 'Unlimited')}
                                </div>
                                <div>
                                    <span className="font-medium">{t('profilePage_subscription_charLimit', 'Monthly Character Limit:')}</span> 
                                    {profile.current_plan_char_limit !== null && profile.current_plan_char_limit !== undefined 
                                        ? profile.current_plan_char_limit.toLocaleString() 
                                        : t('profilePage_subscription_unlimited', 'Unlimited')}
                                </div>
                            </>
                        )}
                        {profile?.current_plan === 'Schools' && (
                            <>
                                <div>
                                    <span className="font-medium">{t('profilePage_subscription_wordLimit', 'Monthly Word Limit:')}</span> 
                                    {t('profilePage_subscription_unlimited', 'Unlimited')}
                                </div>
                                <div>
                                    <span className="font-medium">{t('profilePage_subscription_charLimit', 'Monthly Character Limit:')}</span> 
                                    {t('profilePage_subscription_unlimited', 'Unlimited')}
                                </div>
                            </>
                        )}
                        {/* End MODIFIED */}
                        {profile?.current_plan === 'Pro' && profile?.pro_plan_activated_at && (
                            <div>
                                <span className="font-medium">{t('profilePage_subscription_proActivatedOn', 'Pro Plan Activated On:')}</span> 
                                {new Date(profile.pro_plan_activated_at).toLocaleString()}
                            </div>
                        )}
                        {profile?.current_plan === 'Free' && (
                            <div className="mt-4">
                                <button 
                                    className="btn btn-primary btn-sm"
                                    onClick={() => navigate('/subscribe')} // Navigate to subscribe page
                                >
                                    {t('profilePage_button_upgradeToPro', 'Upgrade to Pro')}
                                </button>
                            </div>
                        )}
                         {profile?.current_plan === 'Pro' && (
                            <div className="mt-4">
                                <button 
                                    className="btn btn-outline btn-sm"
                                    // onClick={handleManageSubscription} // Implement this function
                                    onClick={() => window.location.href = profile.stripe_customer_portal_url || '/'} // TEMP: Direct link if available
                                    disabled={!profile.stripe_customer_portal_url} // Disable if no portal URL
                                >
                                    {t('profilePage_button_manageSubscription', 'Manage Subscription')}
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Usage Details Card - NEW */}
            {currentUser && (
                <div className="card bg-base-100 shadow-md mb-6">
                    <div className="card-body">
                        <h2 className="card-title text-lg">{t('profilePage_usageDetails_title', 'Usage Details')}</h2>
                        <div className="divider my-1"></div>
                        {currentUser.current_plan === 'SCHOOLS' ? (
                            <p>{t('profilePage_usage_unlimited', "Your Schools plan includes unlimited word usage.")}</p>
                        ) : (
                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <span>{t('profilePage_usage_allowance', 'Monthly Word Allowance:')}</span>
                                    <span className="font-semibold">{currentUser.current_plan_word_allowance?.toLocaleString() || t('common_not_applicable', 'N/A')}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>{t('profilePage_usage_used', 'Words Used This Cycle:')}</span>
                                    <span className="font-semibold">{currentUser.words_used_current_cycle?.toLocaleString() || '0'}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>{t('profilePage_usage_remaining', 'Words Remaining This Cycle:')}</span>
                                    <span className="font-semibold">{currentUser.remaining_words_current_cycle?.toLocaleString() || t('common_not_applicable', 'N/A')}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>{t('profilePage_usage_documentsProcessed', 'Documents Processed This Cycle:')}</span>
                                    <span className="font-semibold">{currentUser.documents_processed_current_cycle?.toLocaleString() || '0'}</span>
                                </div>
                                {currentUser.current_plan_word_allowance && currentUser.current_plan_word_allowance > 0 && currentUser.current_plan !== 'SCHOOLS' && (
                                    <progress 
                                        className="progress progress-primary w-full mt-2" 
                                        value={currentUser.words_used_current_cycle || 0} 
                                        max={currentUser.current_plan_word_allowance}>
                                    </progress>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Contact Information Card */}
            <div className="card bg-base-100 shadow-md">
                <div className="card-body">
                    <h2 className="card-title text-lg">{t('profilePage_contactInfo_title', 'Contact Information')}</h2>
                    <div className="divider my-1"></div>
                    <div className="space-y-2">
                        <div>
                            <span className="font-medium">{t('profilePage_contactInfo_phone', 'Phone:')}</span>
                            {currentUser?.phone || t('common_not_applicable', 'N/A')}
                        </div>
                        <div>
                            <span className="font-medium">{t('profilePage_contactInfo_email', 'Email:')}</span>
                            {currentUser?.email || t('common_not_applicable', 'N/A')}
                        </div>
                        <div>
                            <span className="font-medium">{t('profilePage_contactInfo_address', 'Address:')}</span>
                            {currentUser?.address || t('common_not_applicable', 'N/A')}
                        </div>
                    </div>
                </div>
            </div>

        </div>
    );
}

export default ProfilePage; 