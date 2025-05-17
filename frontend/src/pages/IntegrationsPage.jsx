import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

function IntegrationsPage() {
    const { t } = useTranslation();
    const [selectedIntegration, setSelectedIntegration] = useState('');
    const [interestRegistered, setInterestRegistered] = useState(false);
    const [registrationTarget, setRegistrationTarget] = useState(''); // To store which integration interest was for

    const integrations = [
        "Microsoft Teams",
        "Google Classroom",
        "Moodle",
        "Canvas",
        "Microsoft Forms",
        "Survey Monkey", // Corrected typo: SurveyMonkey -> Survey Monkey
        "Other"
    ];

    const handleSelectChange = (event) => {
        const value = event.target.value;
        setSelectedIntegration(value);
        setInterestRegistered(false); // Reset registration status if selection changes
        setRegistrationTarget('');      // Reset registration target
        if (value) {
            console.log(`Selected integration: ${value}`);
        }
    };

    const handleRegisterInterest = () => {
        console.log(`Registering interest for: ${selectedIntegration}`);
        // Here you would typically trigger an API call to your backend
        // For now, we'll just update the UI state
        setInterestRegistered(true);
        setRegistrationTarget(selectedIntegration); 
    };

    return (
        <div className="p-6 md:p-8 lg:p-10 bg-base-100 min-h-screen">
            <header className="mb-8">
                <h1 className="text-3xl font-semibold text-base-content tracking-tight">
                    {t('integrations_page_title', 'Integrations')}
                </h1>
                <p className="mt-2 text-neutral">
                    {t('integrations_page_description', 'Manage your connections with third-party services.')}
                </p>
            </header>

            <section className="bg-base-200 p-6 rounded-lg shadow">
                <h2 className="text-xl font-medium text-base-content mb-4">
                    {t('integrations_select_label', 'Select an Integration')}
                </h2>
                <div className="max-w-md">
                    <select 
                        className="select select-bordered w-full"
                        value={selectedIntegration}
                        onChange={handleSelectChange}
                    >
                        <option value="" disabled>
                            {t('integrations_select_placeholder', 'Choose an option...')}
                        </option>
                        {integrations.map((integrationName) => (
                            <option key={integrationName} value={integrationName}>
                                {integrationName}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Dynamic box for registering interest */}
                {selectedIntegration && !interestRegistered && (
                    <div className="mt-6 p-4 bg-base-100 rounded-md shadow">
                        <p className="text-base-content mb-3">
                            <span className="font-semibold">{selectedIntegration}</span> {t('integrations_paid_plan_info', 'is available in paid plans. To register your interest, select here.')}
                        </p>
                        <button 
                            className="btn btn-primary btn-sm"
                            onClick={handleRegisterInterest}
                        >
                            {t('integrations_button_register_interest', 'Register Interest')}
                        </button>
                    </div>
                )}

                {/* Confirmation message after registering interest */}
                {interestRegistered && registrationTarget && (
                     <div className="mt-6 p-4 bg-success/20 text-success-content rounded-md shadow">
                        <p className="font-semibold">
                            {t('integrations_thank_you_message', 'Thank you for registering your interest in {{integrationName}}!', { integrationName: registrationTarget })}
                        </p>
                    </div>
                )}
            </section>

            {/* Future sections for listing active integrations or adding new ones can go here */}
        </div>
    );
}

export default IntegrationsPage; 