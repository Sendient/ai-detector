// frontend/src/pages/SubscriptionsPage.jsx
import React, { useState } from 'react';
import { useKindeAuth } from '@kinde-oss/kinde-auth-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { loadStripe } from '@stripe/stripe-js'; // For Stripe.js
import { CheckCircle, XCircle } from 'lucide-react';

// Import images
import freePlanImage from '../img/SD_Free.png';
import proPlanImage from '../img/SD_Pro.png';
import schoolsPlanImage from '../img/SD_Schools.png';

// Placeholder for your Stripe Publishable Key (from .env)
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
console.log('VITE_API_BASE_URL in SubscriptionsPage:', import.meta.env.VITE_API_BASE_URL);

function SubscriptionsPage() {
    const { t } = useTranslation();
    const { getAccessToken } = useKindeAuth();
    const { currentUser, loading: authContextLoading, error: authContextError } = useAuth();

    const [isProcessing, setIsProcessing] = useState(false);
    const [apiError, setApiError] = useState(null);

    const features = [
        { id: 'ai_detection', nameKey: 'features_aiDetection', label: 'AI Detection', isBoolean: true },
        { id: 'word_limits', nameKey: 'features_wordLimits', label: 'Word Limits' },
        { id: 'page_limits', nameKey: 'features_pageLimits', label: 'Page Limits' },
        { id: 'pdf_support', nameKey: 'features_pdfSupport', label: 'PDF Support', isBoolean: true },
        { id: 'word_support', nameKey: 'features_wordSupport', label: 'Word Support', isBoolean: true },
        { id: 'student_allocation', nameKey: 'features_studentAllocation', label: 'Student Allocation', isBoolean: true },
        { id: 'classroom_allocation', nameKey: 'features_classroomAllocation', label: 'Classroom Allocation', isBoolean: true },
        { id: 'analytics', nameKey: 'features_analytics', label: 'Analytics', isBoolean: true },
        { id: 'plagiarism_detection', nameKey: 'features_plagiarismDetection', label: 'Plagiarism Detection', isBoolean: true },
        { id: 'lms_integration', nameKey: 'features_lmsIntegration', label: 'Integration with LMS', isBoolean: true },
        { id: 'teams_integration', nameKey: 'features_teamsIntegration', label: 'Integration with Teams', isBoolean: true },
        { id: 'google_classroom_integration', nameKey: 'features_googleClassroom', label: 'Integration with Google Classroom', isBoolean: true },
    ];

    const tiers = [
        {
            name: 'Free',
            price: t('subscriptions_free_price', '£0/month'),
            imageSrc: freePlanImage,
            priceSubtitleKey: 'subscriptions_free_subtitle',
            bgColor: 'bg-[#FDFAFC]', 
            textColor: 'text-gray-800', // Dark text for light background
            buttonClass: 'btn-ghost', // Consider btn-neutral or btn-outline for better visibility on #FDFAFC
            planId: 'FREE',
            featuresValue: {
                ai_detection: true,
                word_limits: t('subscriptions_free_words', '5,000'), page_limits: '5',
                pdf_support: true, word_support: true, allocation: true,
                student_allocation: true, classroom_allocation: true, analytics: true,
                plagiarism_detection: false, lms_integration: false,
                teams_integration: false, google_classroom_integration: false
            },
        },
        {
            name: 'Pro',
            price: t('subscriptions_pro_price', '£8/month'),
            imageSrc: proPlanImage,
            priceSubtitleKey: 'subscriptions_pro_subtitle',
            bgColor: 'bg-primary',
            textColor: 'text-primary-content', // Assuming this is light/white for a typical primary color
            buttonClass: 'btn-secondary', 
            planId: 'PRO',
            featuresValue: {
                ai_detection: true,
                word_limits: t('subscriptions_pro_words', '100,000'), page_limits: '100',
                pdf_support: true, word_support: true, allocation: true,
                student_allocation: true, classroom_allocation: true, analytics: true,
                plagiarism_detection: true, lms_integration: false,
                teams_integration: false, google_classroom_integration: false
            },
        },
        {
            name: 'Schools',
            price: t('subscriptions_schools_price', 'Contact Us'),
            imageSrc: schoolsPlanImage,
            priceSubtitleKey: 'subscriptions_schools_subtitle',
            bgColor: 'bg-accent',
            textColor: 'text-accent-content', // Assuming this is light/white for a typical accent color
            buttonClass: 'btn-info', 
            planId: 'SCHOOLS',
            featuresValue: {
                ai_detection: true,
                word_limits: t('subscriptions_schools_limits', 'No Limit'), page_limits: t('subscriptions_schools_limits', 'No Limit'),
                pdf_support: true, word_support: true, allocation: true,
                student_allocation: true, classroom_allocation: true, analytics: true,
                plagiarism_detection: true, lms_integration: true,
                teams_integration: true, google_classroom_integration: true
            },
        }
    ];

    if (authContextLoading) {
        return <div className="flex items-center justify-center min-h-screen"><span className="loading loading-lg loading-spinner text-primary"></span></div>;
    }

    if (authContextError) {
        return <div className="p-4 text-center text-error">{t('subscriptions_error_loading_profile', { message: authContextError.message || authContextError })}</div>;
    }

    const handleUpgradeToPro = async () => {
        setIsProcessing(true);
        setApiError(null);
        try {
            const token = await getAccessToken();
            if (!token) {
                throw new Error(t('messages_error_authTokenMissing', 'Authentication token is missing.'));
            }

            const proPriceId = import.meta.env.VITE_STRIPE_PRO_PLAN_PRICE_ID;
            if (!proPriceId) {
                throw new Error(t('messages_error_stripe_pro_price_id_missing', 'Stripe Pro Plan Price ID is not configured.'));
            }

            const response = await fetch(`${API_BASE_URL}/api/v1/create-checkout-session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({ price_id: proPriceId }),
            });

            if (!response.ok) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch {
                    // Ignore if response is not JSON
                }
                const errorMessage = errorData?.detail || response.statusText || t('messages_error_create_checkout_failed', 'Failed to create checkout session.');
                throw new Error(errorMessage);
            }

            const session = await response.json();
            const sessionId = session?.sessionId;

            if (sessionId) {
                console.log("Stripe Checkout Session ID:", sessionId);
                const stripe = await stripePromise; // Get the Stripe instance
                if (stripe) {
                    const { error } = await stripe.redirectToCheckout({ sessionId: sessionId });
                    if (error) {
                        // If `redirectToCheckout` fails due to a browser policy
                        // or network error, display the localized error message to your customer.
                        console.error("Stripe redirectToCheckout error:", error);
                        setApiError(error.message || t('messages_error_stripe_redirect', 'Failed to redirect to Stripe. Please try again.'));
                    }
                } else {
                    throw new Error(t('messages_error_stripe_not_loaded', 'Stripe.js has not loaded yet.'));
                }
            } else {
                throw new Error(t('messages_error_checkout_session_id_missing', 'Checkout session ID not found in response.'));
            }

        } catch (error) {
            console.error("handleUpgradeToPro error:", error);
            setApiError(error.message);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleManageSubscription = async () => {
        setIsProcessing(true);
        setApiError(null);
        try {
            const token = await getAccessToken();
            if (!token) {
                throw new Error(t('messages_error_authTokenMissing', 'Authentication token is missing.'));
            }

            const response = await fetch(`${API_BASE_URL}/api/v1/create-portal-session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
            });

            if (!response.ok) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch {
                    // Ignore if response is not JSON
                }
                const errorMessage = errorData?.detail || response.statusText || t('messages_error_create_portal_failed', 'Failed to create customer portal session.');
                throw new Error(errorMessage);
            }

            const session = await response.json();
            const portalUrl = session?.url;

            if (portalUrl) {
                window.location.href = portalUrl; // Redirect to Stripe Customer Portal
            } else {
                throw new Error(t('messages_error_portal_url_missing', 'Customer portal URL not found in response.'));
            }

        } catch (error) {
            console.error("handleManageSubscription error:", error);
            setApiError(error.message);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleContactSchools = () => {
        window.location.href = 'mailto:hello@smartdetector.ai';
    };

    // Determine current plan to adjust button text or highlight
    const currentPlanId = currentUser?.current_plan?.toUpperCase();

    return (
        <div className="container mx-auto p-4 sm:p-6 lg:p-8">
            <h1 className="text-3xl font-bold text-center mb-10 sm:mb-16">{t('subscriptions_page_title', 'Choose Your Plan')}</h1>
            {apiError && <div className="alert alert-error shadow-lg mb-6"><div><span>{apiError}</span></div></div>}

            <div className="grid grid-cols-1 md:grid-cols-[minmax(200px,_1fr)_repeat(3,minmax(0,_1fr))] gap-x-2 sm:gap-x-4 lg:gap-x-6">
                {/* Row for Plan Headers (including images, name, price) */}
                <div className="hidden md:block"></div> {/* Empty cell for alignment above feature labels */}
                {tiers.map(tier => (
                    <div key={tier.planId + "-header-column-wrapper"} className="flex flex-col items-stretch">
                        {/* Image Band - always #FDFAFC, rounded at the top */}
                        <div className="bg-[#FDFAFC] p-4 w-full rounded-t-lg">
                            <img src={tier.imageSrc} alt={`${tier.name} plan`} className="h-24 w-auto object-contain mx-auto" />
                        </div>
                        {/* Plan Details Section - takes its color from tier.bgColor/tier.textColor */}
                        <div className={`p-4 text-center w-full ${tier.planId === 'FREE' ? tier.bgColor + ' ' + tier.textColor : tier.bgColor + ' ' + tier.textColor}`}>
                            <h2 className="text-xl sm:text-2xl font-semibold">{tier.name}</h2>
                            <p className="text-lg sm:text-xl font-bold my-1">{tier.price}</p>
                            {t(tier.priceSubtitleKey) && <p className="text-xs opacity-80">{t(tier.priceSubtitleKey)}</p>}
                        </div>
                        {/* Buttons Section - Placed after plan details, before feature rows start conceptually */}
                        <div className={`px-4 pt-2 pb-4 text-center w-full rounded-b-lg ${tier.planId === 'FREE' ? tier.bgColor : tier.bgColor}`}>
                            {tier.planId === 'FREE' && currentPlanId === 'FREE' && (
                                <button className="btn btn-disabled w-full" disabled>{t('subscriptions_button_currentPlan', 'Current Plan')}</button>
                            )}
                            {tier.planId === 'FREE' && currentPlanId !== 'FREE' && (
                                // No button for Free if not current plan, or specific downgrade logic if needed
                                <span className="text-sm italic">{t('subscriptions_free_info', 'Basic access features.')}</span>
                            )}
                            {tier.planId === 'PRO' && currentPlanId !== 'PRO' && (
                                <button className={`btn w-full ${tier.buttonClass}`} onClick={handleUpgradeToPro} disabled={isProcessing}>
                                    {isProcessing ? t('subscriptions_button_processing', 'Processing...') : t('subscriptions_button_upgradeToPro', 'Upgrade to Pro')}
                                </button>
                            )}
                            {tier.planId === 'PRO' && currentPlanId === 'PRO' && (
                                <button className={`btn w-full ${tier.buttonClass}`} onClick={handleManageSubscription} disabled={isProcessing}>
                                    {isProcessing ? t('subscriptions_button_processing', 'Processing...') : t('subscriptions_button_manageSubscription', 'Manage Subscription')}
                                </button>
                            )}
                            {tier.planId === 'SCHOOLS' && (
                                <button className={`btn w-full ${tier.buttonClass}`} onClick={handleContactSchools}>
                                    {t('subscriptions_button_contactForSchools', 'Contact for Schools')}
                                </button>
                            )}
                        </div>
                    </div>
                ))}

                {/* Feature Rows */}
                {features.map((feature, featureIndex) => (
                    <React.Fragment key={feature.id}>
                        {/* Feature Label Column */}
                        <div className={`hidden md:flex items-center pr-2 min-h-[3.5rem] py-2 ${featureIndex === 0 ? 'md:border-t border-base-300' : ''} border-b border-base-300`}>
                            <span className={`text-sm ${feature.isHeading ? 'font-semibold' : 'font-medium'} text-neutral`}>{t(feature.nameKey, feature.label)}</span>
                        </div>

                        {/* Tier Feature Value Columns - uses tier.bgColor and tier.textColor */}
                        {tiers.map(tier => (
                            <div key={`${tier.planId}-${feature.id}`} 
                                 className={`flex justify-center items-center text-center px-2 min-h-[3.5rem] py-2 ${tier.bgColor} ${tier.textColor} ${featureIndex === 0 ? 'md:border-t border-base-300' : ''} border-b border-base-300 ${tier.planId === 'FREE' ? '' : 'md:bg-opacity-20'}`}>
                                {/* Mobile label, shown only on small screens */}
                                <span className={`md:hidden text-sm ${feature.isHeading ? 'font-semibold' : 'font-medium'} mr-auto ${tier.planId === 'FREE' ? tier.textColor : 'text-neutral'}`}>{t(feature.nameKey, feature.label)}:</span>
                                <div className="ml-auto md:ml-0">
                                    {feature.isHeading ? (
                                        <span>&nbsp;</span>
                                    ) : feature.isBoolean ? (
                                        tier.featuresValue[feature.id] ? <CheckCircle className="h-5 w-5 text-success" /> : <XCircle className="h-5 w-5 text-error" />
                                    ) : (
                                        <span className="text-sm">{tier.featuresValue[feature.id]}</span>
                                    )}
                                </div>    
                            </div>
                        ))}
                    </React.Fragment>
                ))}
            </div>

            <div className="mt-10 sm:mt-16 border-t pt-6">
                {/* Rest of the component content remains unchanged */}
            </div>
        </div>
    );
}

export default SubscriptionsPage;