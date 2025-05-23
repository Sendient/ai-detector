// frontend/src/pages/PaymentSuccessPage.jsx
import React, { useEffect } from 'react';
import { Link, useSearchParams, useNavigate }    from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle } from 'lucide-react'; // Assuming you use lucide-react for icons
import { useTeacherProfile } from '../hooks/useTeacherProfile'; // To refetch profile


function PaymentSuccessPage() {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { refetchProfile } = useTeacherProfile();
    const sessionId = searchParams.get('session_id'); // Optional: for logging or display

    useEffect(() => {
        // Optionally refetch profile to update UI sooner, though webhooks are the source of truth
        refetchProfile();

        // Redirect to dashboard or subscriptions page after a few seconds
        const timer = setTimeout(() => {
            navigate('/'); // Or '/subscriptions' or '/profile'
        }, 5000); // 5 seconds

        return () => clearTimeout(timer);
    }, [navigate, refetchProfile]);

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
                {t('payment_success_message2', 'Your account is being updated. You will be redirected shortly.')}
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