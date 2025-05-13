import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

function SignupPage() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { register, getAccessToken, getUser, isAuthenticated, isLoading } = useKindeAuth();

    const [formData, setFormData] = useState({
        email: '',
        password: '',
        confirmPassword: '',
        firstName: '',
        lastName: ''
    });
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState('');
    const [debugInfo, setDebugInfo] = useState(null);

    // Add debug state
    const [debugLogs, setDebugLogs] = useState([]);

    const addDebugLog = (message, data = null) => {
        const log = {
            timestamp: new Date().toISOString(),
            message,
            data
        };
        console.log(`[Signup Debug] ${message}`, data);
        setDebugLogs(prev => [...prev, log]);
    };

    // Debug Kinde auth state
    useEffect(() => {
        const debugKindeState = async () => {
            try {
                addDebugLog('Checking Kinde auth state', {
                    isAuthenticated,
                    isLoading
                });

                const token = await getAccessToken("https://api.aidetector.sendient.ai");
                const user = await getUser();
                
                addDebugLog('Kinde auth state details', {
                    isAuthenticated,
                    isLoading,
                    token: token ? {
                        type: typeof token,
                        length: token.length,
                        firstChars: token.substring(0, 10) + '...',
                        scopes: token.split(' ').map(t => t.split('.')[0])
                    } : null,
                    user: user ? {
                        ...user,
                        allFields: Object.keys(user)
                    } : null
                });
            } catch (err) {
                addDebugLog('Error getting Kinde debug info', {
                    error: err.message,
                    stack: err.stack
                });
            }
        };

        if (!isLoading) {
            debugKindeState();
        }
    }, [isLoading, isAuthenticated, getAccessToken, getUser]);

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        setError(null);
        setSuccess('');
        setDebugInfo(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setSuccess('');
        setDebugInfo(null);
        setIsSubmitting(true);
        setDebugLogs([]); // Clear previous logs

        addDebugLog('Starting registration process', {
            email: formData.email,
            hasPassword: !!formData.password,
            hasFirstName: !!formData.firstName,
            hasLastName: !!formData.lastName
        });

        // Validate passwords match
        if (formData.password !== formData.confirmPassword) {
            addDebugLog('Password validation failed', {
                passwordLength: formData.password.length,
                confirmPasswordLength: formData.confirmPassword.length
            });
            setError(t('messages_signup_error_passwordsMismatch'));
            setIsSubmitting(false);
            return;
        }

        try {
            // Log registration parameters
            const registrationParams = {
                email: formData.email,
                password: formData.password,
                given_name: formData.firstName,
                family_name: formData.lastName,
                timestamp: new Date().toISOString()
            };
            addDebugLog('Registration parameters prepared', registrationParams);

            // Attempt to register with Kinde
            addDebugLog('Calling Kinde register', {
                email: formData.email,
                given_name: formData.firstName,
                family_name: formData.lastName,
                scopes: ['openid', 'profile', 'email', 'offline']
            });

            const response = await register({
                email: formData.email,
                password: formData.password,
                given_name: formData.firstName,
                family_name: formData.lastName
            });

            addDebugLog('Kinde registration response received', {
                status: response?.status,
                error: response?.error,
                error_description: response?.error_description,
                hasUser: !!response?.user,
                hasTokens: !!response?.tokens,
                userDetails: response?.user ? {
                    id: response.user.id ? String(response.user.id) : undefined,
                    email: response.user.email,
                    given_name: response.user.given_name,
                    family_name: response.user.family_name
                } : null,
                tokenDetails: response?.tokens ? {
                    hasAccessToken: !!response.tokens.access_token,
                    hasRefreshToken: !!response.tokens.refresh_token,
                    hasIdToken: !!response.tokens.id_token,
                    tokenType: response.tokens.token_type,
                    expiresIn: response.tokens.expires_in
                } : null
            });

            // Handle different response scenarios
            if (response?.error === 'server_error' || response?.status === 500) {
                addDebugLog('Server error detected', {
                    error: response?.error,
                    error_description: response?.error_description,
                    responseHeaders: response?.headers,
                    responseStatus: response?.status,
                    responseStatusText: response?.statusText
                });

                // Check if this is a duplicate email error
                if (response?.error_description?.toLowerCase().includes('already exists') ||
                    response?.error_description?.toLowerCase().includes('duplicate')) {
                    addDebugLog('Duplicate email detected');
                    setError(t('messages_signup_error_emailExists'));
                    setDebugInfo(prev => ({
                        ...prev,
                        type: 'duplicate_email',
                        response: response
                    }));
                    // Redirect to login page after a short delay
                    setTimeout(() => {
                        navigate('/login');
                    }, 3000);
                    return;
                }
                
                // Handle other server errors
                addDebugLog('Other server error', {
                    error: response?.error,
                    error_description: response?.error_description,
                    responseHeaders: response?.headers,
                    responseStatus: response?.status,
                    responseStatusText: response?.statusText
                });
                setError(t('messages_signup_error_server'));
                setDebugInfo(prev => ({
                    ...prev,
                    type: 'server_error',
                    response: response
                }));
                return;
            }

            // If registration is successful
            if (response?.user) {
                addDebugLog('Registration successful', {
                    userId: response.user.id ? String(response.user.id) : undefined,
                    email: response.user.email,
                    tokenDetails: response?.tokens ? {
                        hasAccessToken: !!response.tokens.access_token,
                        hasRefreshToken: !!response.tokens.refresh_token,
                        hasIdToken: !!response.tokens.id_token,
                        tokenType: response.tokens.token_type,
                        expiresIn: response.tokens.expires_in
                    } : null
                });

                // Try to get token immediately after registration
                try {
                    const token = await getAccessToken("https://api.aidetector.sendient.ai");
                    addDebugLog('Token retrieved after registration', {
                        hasToken: !!token,
                        tokenType: typeof token,
                        tokenLength: token?.length,
                        firstChars: token?.substring(0, 10) + '...'
                    });
                } catch (tokenErr) {
                    addDebugLog('Error getting token after registration', {
                        error: tokenErr.message,
                        stack: tokenErr.stack
                    });
                }

                setSuccess(t('messages_signup_success'));
                setDebugInfo(prev => ({
                    ...prev,
                    type: 'success',
                    userId: response.user.id ? String(response.user.id) : undefined,
                    email: response.user.email
                }));
                // Redirect to profile page after a short delay
                setTimeout(() => {
                    navigate('/profile');
                }, 2000);
            } else {
                addDebugLog('Registration failed - no user in response', {
                    response: response
                });
                const errorMessage = response?.error_description || t('messages_signup_error_unexpected');
                setError(errorMessage);
                setDebugInfo(prev => ({
                    ...prev,
                    type: 'error',
                    response: response
                }));
                throw new Error(errorMessage);
            }
        } catch (err) {
            addDebugLog('Exception during registration', {
                message: err.message,
                stack: err.stack,
                response: err.response
            });
            console.error('Signup error:', {
                message: err.message,
                stack: err.stack,
                response: err.response
            });
            setError(err.message || t('messages_signup_error_unexpected'));
            setDebugInfo({
                type: 'exception',
                error: err,
                message: err.message,
                stack: err.stack
            });
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="max-w-md mx-auto p-4 sm:p-6 lg:p-8">
            <h1 className="text-xl font-semibold text-base-content mb-6">{t('signupPage_heading')}</h1>

            {/* Success Message */}
            {success && (
                <div role="alert" className="alert alert-success mb-4 shadow-sm">
                    <CheckCircle2 className="h-6 w-6 stroke-current shrink-0" />
                    <span>{success}</span>
                </div>
            )}

            {/* Error Message */}
            {error && !success && (
                <div role="alert" className="alert alert-error mb-4 shadow-sm break-words">
                    <XCircle className="h-6 w-6 stroke-current shrink-0" />
                    <span>{t('common_error_prefix')} {error}</span>
                </div>
            )}

            {/* Debug Information */}
            {debugInfo && (
                <div className="bg-base-200 p-4 rounded-lg mb-4 text-sm">
                    <h3 className="font-semibold mb-2">Debug Information:</h3>
                    <pre className="whitespace-pre-wrap break-words">
                        {JSON.stringify(debugInfo, null, 2)}
                    </pre>
                </div>
            )}

            {/* Debug Logs */}
            {debugLogs.length > 0 && (
                <div className="bg-base-200 p-4 rounded-lg mb-4 text-sm">
                    <h3 className="font-semibold mb-2">Debug Logs:</h3>
                    <div className="space-y-2">
                        {debugLogs.map((log, index) => (
                            <div key={index} className="border-b border-base-300 pb-2">
                                <div className="text-xs text-base-content/70">{log.timestamp}</div>
                                <div className="font-medium">{log.message}</div>
                                {log.data && (
                                    <pre className="whitespace-pre-wrap break-words text-xs mt-1">
                                        {JSON.stringify(log.data, null, 2)}
                                    </pre>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Signup Form */}
            <form onSubmit={handleSubmit} className="space-y-6 bg-base-100 p-6 rounded-lg shadow-sm border border-base-300">
                {/* Email Field */}
                <div>
                    <label htmlFor="email" className="block text-sm font-medium text-base-content mb-1">
                        {t('signupPage_form_label_email')} <span className="text-error">{t('common_required_indicator')}</span>
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        value={formData.email}
                        onChange={handleInputChange}
                        className="input input-bordered w-full"
                        required
                        aria-required="true"
                    />
                </div>

                {/* Password Field */}
                <div>
                    <label htmlFor="password" className="block text-sm font-medium text-base-content mb-1">
                        {t('signupPage_form_label_password')} <span className="text-error">{t('common_required_indicator')}</span>
                    </label>
                    <input
                        type="password"
                        id="password"
                        name="password"
                        value={formData.password}
                        onChange={handleInputChange}
                        className="input input-bordered w-full"
                        required
                        aria-required="true"
                        minLength="8"
                    />
                </div>

                {/* Confirm Password Field */}
                <div>
                    <label htmlFor="confirmPassword" className="block text-sm font-medium text-base-content mb-1">
                        {t('signupPage_form_label_confirmPassword')} <span className="text-error">{t('common_required_indicator')}</span>
                    </label>
                    <input
                        type="password"
                        id="confirmPassword"
                        name="confirmPassword"
                        value={formData.confirmPassword}
                        onChange={handleInputChange}
                        className="input input-bordered w-full"
                        required
                        aria-required="true"
                        minLength="8"
                    />
                </div>

                {/* First Name Field */}
                <div>
                    <label htmlFor="firstName" className="block text-sm font-medium text-base-content mb-1">
                        {t('signupPage_form_label_firstName')} <span className="text-error">{t('common_required_indicator')}</span>
                    </label>
                    <input
                        type="text"
                        id="firstName"
                        name="firstName"
                        value={formData.firstName}
                        onChange={handleInputChange}
                        className="input input-bordered w-full"
                        required
                        aria-required="true"
                    />
                </div>

                {/* Last Name Field */}
                <div>
                    <label htmlFor="lastName" className="block text-sm font-medium text-base-content mb-1">
                        {t('signupPage_form_label_lastName')} <span className="text-error">{t('common_required_indicator')}</span>
                    </label>
                    <input
                        type="text"
                        id="lastName"
                        name="lastName"
                        value={formData.lastName}
                        onChange={handleInputChange}
                        className="input input-bordered w-full"
                        required
                        aria-required="true"
                    />
                </div>

                {/* Submit Button */}
                <button
                    type="submit"
                    className="btn btn-primary w-full"
                    disabled={isSubmitting}
                >
                    {isSubmitting ? t('signupPage_form_button_submitting') : t('signupPage_form_button_submit')}
                </button>
            </form>
        </div>
    );
}

export default SignupPage; 