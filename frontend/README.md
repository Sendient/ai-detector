# AI Detector Frontend

**IMPORTANT DEPLOYMENT PREREQUISITES:**
1. **Before UI Code Deployment:**
   - After running the infrastructure deployment (`deploy-frontend-infra.yml`), you MUST set the Static Web App deployment token as a GitHub secret named `AZURE_STATIC_WEB_APPS_API_TOKEN`
   - This token can be obtained from the Azure Portal under your Static Web App's "Manage deployment tokens" section

2. **Before Infrastructure Deployment:**
   - Set up the following Kinde environment variables in your GitHub repository secrets:
     - `KINDE_ISSUER_URL`
     - `KINDE_CLIENT_ID`
     - `KINDE_REDIRECT_URI`
     - `KINDE_LOGOUT_REDIRECT_URI`

This is the frontend application for the AI Detector, built with React and Vite, featuring a modern UI with Tailwind CSS and DaisyUI components.

## Project Structure.

```
frontend/
├── src/                    # Source code
│   ├── assets/            # Static assets (images, fonts, etc.)
│   ├── components/        # Reusable React components
│   ├── hooks/            # Custom React hooks
│   ├── pages/            # Page components
│   ├── App.jsx           # Main application component
│   ├── main.jsx          # Application entry point
│   ├── i18n.js           # Internationalization setup
│   └── index.css         # Global styles
├── public/               # Public static files
├── index.html           # HTML entry point
├── package.json         # Project dependencies and scripts
├── vite.config.js       # Vite configuration
├── tailwind.config.js   # Tailwind CSS configuration
├── postcss.config.js    # PostCSS configuration
└── eslint.config.js     # ESLint configuration
```

## Local Development Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

The application will be available at `http://localhost:5173`

## Available Scripts

- `npm run dev`: Start development server
- `npm run build`: Build for production
- `npm run preview`: Preview production build
- `npm run lint`: Run ESLint

## Key Features

### 1. Modern Tech Stack
- React 19
- Vite 6
- Tailwind CSS
- DaisyUI components
- React Router v7
- i18next for internationalization

### 2. Authentication
- Kinde authentication integration
- JWT handling
- Protected routes

### 3. UI Components
- Responsive design
- Modern UI with Tailwind CSS
- DaisyUI component library
- Heroicons and Lucide icons
- Recharts for data visualization

### 4. Internationalization
- Multi-language support
- Automatic language detection
- Dynamic language switching

## Dependencies

### Core Dependencies
- `react`: UI library
- `react-dom`: React DOM rendering
- `react-router-dom`: Routing
- `@kinde-oss/kinde-auth-react`: Authentication
- `i18next`: Internationalization
- `recharts`: Data visualization
- `@heroicons/react`: Icon library
- `lucide-react`: Additional icons

### Development Dependencies
- `vite`: Build tool and dev server
- `tailwindcss`: Utility-first CSS framework
- `daisyui`: Component library
- `eslint`: Code linting
- `postcss`: CSS processing
- `autoprefixer`: CSS vendor prefixing

## Configuration Files

### Vite Configuration (`vite.config.js`)
- Development server settings
- Build optimization
- Plugin configuration

### Tailwind Configuration (`tailwind.config.js`)
- Theme customization
- Plugin configuration
- DaisyUI setup

### ESLint Configuration (`eslint.config.js`)
- Code style rules
- React-specific rules
- TypeScript support

## Building for Production

1. Create a production build:
   ```bash
   npm run build
   ```

2. Preview the production build:
   ```bash
   npm run preview
   ```

The build output will be in the `dist` directory.

## Environment Variables

Create a `.env` file in the frontend directory with the following variables:
```
VITE_API_URL=your_api_url
VITE_KINDE_ISSUER_URL=your_kinde_issuer_url
VITE_KINDE_CLIENT_ID=your_kinde_client_id
VITE_KINDE_REDIRECT_URI=your_kinde_redirect_uri
VITE_KINDE_LOGOUT_REDIRECT_URI=your_kinde_logout_redirect_uri
```

## Deployment

The frontend is deployed as a Static Web App in Azure. The deployment process:

1. Builds the application using Vite
2. Deploys the built files to Azure Static Web Apps
3. Configures routing and authentication
4. Sets up environment variables

## Development Guidelines

1. **Component Structure**
   - Use functional components
   - Implement proper prop typing
   - Follow React best practices

2. **Styling**
   - Use Tailwind CSS for styling
   - Follow the design system
   - Maintain responsive design

3. **State Management**
   - Use React hooks for local state
   - Implement proper error handling
   - Follow React patterns

4. **Code Quality**
   - Run linter before committing
   - Write meaningful component names
   - Document complex logic
