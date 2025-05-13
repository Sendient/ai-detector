// src/components/LocaleSelector.jsx
import React from 'react';
import { useTranslation } from 'react-i18next';

// Define the available locales and their display names (using translation keys)
const locales = {
  'en-GB': { titleKey: 'locale_uk', nativeName: 'English (UK)' },
  'en-US': { titleKey: 'locale_us', nativeName: 'English (US)' },
  'fr-FR': { titleKey: 'locale_fr', nativeName: 'Français (France)' },
  // Add other supported locales here
};

function LocaleSelector() {
  const { i18n, t } = useTranslation();

  // Function to handle language change (logic remains the same)
  const handleLanguageChange = (event) => {
    const newLocale = event.target.value;
    console.log(`Attempting to change language to: ${newLocale}`);
    i18n.changeLanguage(newLocale)
      .then(() => {
        console.log(`Language successfully changed to ${i18n.language}`);
      })
      .catch((err) => {
        console.error("Error changing language:", err);
      });
  };

  const currentLanguage = i18n.language;

  // It's generally better practice for the parent (e.g., Header) to handle positioning.
  // However, keeping margin-left for now if this component needs to self-position.
  // Using Tailwind for margin and padding instead of inline style.
  // Reduced padding slightly assuming it sits within a header.
  return (
    <div className="ml-auto p-2 flex items-center"> {/* Use Tailwind for layout */}
      {/* Use DaisyUI form-control structure for proper spacing/alignment, though might be overkill if label is hidden */}
      {/* <div className="form-control"> */}
        {/* Visually hidden label for accessibility, but label text helps */}
        <label htmlFor="locale-select" className="sr-only"> {/* sr-only hides visually but keeps for screen readers */}
          {t('select_language')}:
        </label>
        {/* Use DaisyUI select component with appropriate styles */}
        <select
          id="locale-select"
          value={currentLanguage}
          onChange={handleLanguageChange}
          aria-label={t('select_language')} // Important for accessibility
          // Apply DaisyUI select classes - choose size/style as needed
          className="select select-bordered select-sm max-w-xs focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        >
          {/* Map options - logic remains the same */}
          {Object.keys(locales).map((localeCode) => (
            <option key={localeCode} value={localeCode}>
              {t(locales[localeCode].titleKey)} {/* Display translated short name */}
            </option>
          ))}
        </select>
      {/* </div> */}
    </div>
  );
}

export default LocaleSelector;