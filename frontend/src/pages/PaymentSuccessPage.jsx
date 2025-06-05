// frontend/src/pages/PaymentSuccessPage.jsx
import React, { useEffect } from 'react';
import { Link, useSearchParams, useNavigate }    from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle } from 'lucide-react'; // Assuming you use lucide-react for icons
// import { useTeacherProfile } from '../hooks/useTeacherProfile'; // Removed
import { useAuth } from '../contexts/AuthContext'; // Added
import { useKindeAuth } from '@kinde-oss/kinde-auth-react'; // Added

const PROXY_PATH = import.meta.env.VITE_API_PROXY_PATH || '/api/v1'; // Added

function PaymentSuccessPage() {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    // const { refetchProfile } = useTeacherProfile(); // Removed
    const { setCurrentUser } = useAuth(); // Added
    const { getAccessToken } = useKindeAuth(); // Added
    const sessionId = searchParams.get('session_id'); // Optional: for logging or display

    useEffect(() => {
        const updateUserProfile = async () => {
            try {
                const token = await getAccessToken();
                if (!token) {
                    console.error("PaymentSuccessPage: Failed to get access token.");
                    // Handle missing token error if necessary, maybe redirect to login or show error
                    return;
                }
                const response = await fetch(`${PROXY_PATH}/teachers/me`, {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                });

                if (!response.ok) {
                    console.error("PaymentSuccessPage: Failed to fetch updated profile.", response.status);
                    // Handle fetch error if necessary
                    return;
                }
                const updatedProfileData = await response.json();
                setCurrentUser(updatedProfileData); // Update AuthContext
                console.log("PaymentSuccessPage: AuthContext updated with new profile data.", updatedProfileData);
            } catch (error) {
                console.error("PaymentSuccessPage: Error updating user profile:", error);
                // Handle other errors if necessary
            }
        };

        updateUserProfile();

        // Redirect to dashboard or subscriptions page after a few seconds
        const timer = setTimeout(() => {
            navigate('/profile'); // Changed to /profile as per original file
        }, 5000); // 5 seconds

        return () => clearTimeout(timer);
    }, [navigate, setCurrentUser, getAccessToken]); // Added dependencies

    return (
        <div className="container mx-auto p-4 py-12 flex flex-col items-center text-center">
            <CheckCircle className="w-16 h-16 text-success mb-6" />
            <h1 className="text-3xl font-bold text-base-content mb-4">
                {t('payment_success_title', 'Payment Successful!')}
            </h1>
            <p className="text-lg text-base-content mb-2">
                {t('payment_success_message1', 'Thank you for your subscription.')}
            </p>
            <p className="text-base-content mb-8">
                {t('payment_success_message2', 'Your account is being updated with your new Pro plan. This may take a moment. You will be redirected shortly.')}
            </p>
            {sessionId && (
                <p className="text-xs text-gray-500 mb-4">
                    {t('payment_success_session_id', 'Session ID')}: {sessionId}
                </p>
            )}
            <Link to="/" className="btn btn-primary">
                {t('payment_success_cta_dashboard', 'Go to Dashboard')}
            </Link>
        </div>
    );
}

export default PaymentSuccessPage;