// frontend/src/pages/PaymentCancelPage.jsx
import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { XCircle } from 'lucide-react'; // Assuming you use lucide-react

function PaymentCancelPage() {
    const { t } = useTranslation();

    return (
        <div className="container mx-auto p-4 py-12 flex flex-col items-center text-center">
            <XCircle className="w-16 h-16 text-error mb-6" />
            <h1 className="text-3xl font-bold text-base-content mb-4">
                {t('payment_cancel_title', 'Payment Canceled')}
            </h1>
            <p className="text-lg text-base-content mb-8">
                {t('payment_cancel_message', 'Your payment process was canceled. Your subscription has not been changed.')}
            </p>
            <Link to="/subscriptions" className="btn btn-primary">
                {t('payment_cancel_cta_subscriptions', 'View Subscription Plans')}
            </Link>
        </div>
    );
}

export default PaymentCancelPage;