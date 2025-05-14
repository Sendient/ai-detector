# GitHub Workflows

**REQUIRED GITHUB ENVIRONMENT VARIABLES AND SECRETS**

The following environment variables and secrets must be set in your GitHub repository or environment for successful deployments. Secrets must be added in the GitHub repository or environment as **secrets** (not plain variables).

### Frontend (Static Web App)
- `VITE_KINDE_AUDIENCE`: Kinde audience (environment variable)
- `VITE_KINDE_CLIENT_ID`: Kinde client ID (environment variable)
- `VITE_KINDE_DOMAIN`: Kinde domain (environment variable)
- `VITE_KINDE_LOGIN_REDIRECT_URI`: Kinde login redirect URI (environment variable)
- `VITE_KINDE_LOGOUT_REDIRECT_URI`: Kinde logout redirect URI (environment variable)

### Backend (API & Infrastructure) and Frontend
- `AZURE_CLIENT_ID` (**REQUIRED SECRET**): The client ID of your Azure service principal
- `AZURE_CLIENT_SECRET` (**REQUIRED SECRET**): The client secret of your Azure service principal
- `AZURE_TENANT_ID` (**REQUIRED SECRET**): Your Azure tenant ID
- `AZURE_SUBSCRIPTION_ID` (**REQUIRED SECRET**): Your Azure subscription ID
- `VITE_KINDE_CLIENT_SECRET` (**REQUIRED SECRET**): Kinde client Secret (environment variable)
- `STRIPE_SECRET` (**REQUIRED SECRET**): Stripe Secret (environment variable)


These variables and secrets are accessible only by GitHub Actions in the context of this environment. Set them before running any deployments.

This directory contains the GitHub Actions workflows that automate the deployment of the AI Detector application. The workflows are organized into complete deployment pipelines and individual deployment steps.

## Complete Deployment Workflows

### 1. `deploy-backend-complete.yml`
Complete backend deployment pipeline that orchestrates:
- Infrastructure deployment
- Backend code deployment
- Container infrastructure setup
- Container app deployment

**Triggered by:**
- Push to main branch
- Manual workflow dispatch

**Environment Options:**
- dev1 (default)
- dev
- staging
- prod

**Job Dependencies:**
1. `get-changes`: Detects changes in:
   - Backend infrastructure files
   - Container infrastructure files
   - Backend code files

2. `deploy-infra`: Depends on `get-changes`
   - Calls `deploy-backend-infra.yml`
   - Only runs if infrastructure changes detected or manually triggered

3. `deploy-backend`: Depends on `deploy-infra` and `get-changes`
   - Calls `deploy-api-code.yml`
   - Only runs if backend code changes detected or manually triggered
   - Waits for infrastructure deployment to complete

4. `deploy-container-infra`: Depends on `deploy-backend` and `get-changes`
   - Calls `deploy-container-infra.yml`
   - Only runs if container infrastructure changes detected or manually triggered
   - Waits for backend deployment to complete

5. `push-to-container`: Depends on `deploy-container-infra` and `deploy-backend`
   - Calls `deploy-api-to-containerapp.yml`
   - Only runs if backend deployment succeeds
   - Waits for container infrastructure deployment to complete

### 2. `deploy-frontend-complete.yml`
Complete frontend deployment pipeline that orchestrates:
- Static Web App infrastructure deployment
- Frontend code deployment

**Triggered by:**
- Push to main branch
- Manual workflow dispatch

**Environment Options:**
- dev1 (default)
- dev
- staging
- prod

**Job Dependencies:**
1. `get-changes`: Detects changes in:
   - Frontend infrastructure files
   - Frontend code files

2. `deploy-infra`: Depends on `get-changes`
   - Calls `deploy-frontend-infra.yml`
   - Only runs if infrastructure changes detected or manually triggered

3. `deploy-ui-code`: Depends on `get-changes` and `deploy-infra`
   - Calls `deploy-ui-code.yml`
   - Only runs if frontend code changes detected or manually triggered
   - Waits for infrastructure deployment to complete

## Individual Deployment Workflows

### Backend Infrastructure (`deploy-backend-infra.yml`)
Deploys backend infrastructure components:
- Container Registry
- Cosmos DB
- Key Vault
- Managed Identities
- Storage Account

### Backend Code (`deploy-api-code.yml`)
Handles backend code deployment:
- Builds Docker image
- Pushes to Container Registry
- Manages image tags

### Container Infrastructure (`deploy-container-infra.yml`)
Deploys container-specific infrastructure:
- Container App Environment
- Container App configuration

### API to Container App (`deploy-api-to-containerapp.yml`)
Deploys the API to Azure Container Apps:
- Updates container app with new image
- Configures environment variables
- Manages scaling settings

### Frontend Infrastructure (`deploy-frontend-infra.yml`)
Deploys frontend infrastructure:
- Azure Static Web App
- Configuration settings
- Environment variables

### UI Code (`deploy-ui-code.yml`)
Deploys frontend code:
- Builds the React application
- Deploys to Static Web App
- Configures routing

## Workflow Dependencies

The workflows are designed to run in a specific order:

### Backend Deployment Flow
1. `deploy-backend-complete.yml` orchestrates:
   - Calls `deploy-backend-infra.yml`
   - Calls `deploy-api-code.yml`
   - Calls `deploy-container-infra.yml`
   - Calls `deploy-api-to-containerapp.yml`

### Frontend Deployment Flow
1. `deploy-frontend-complete.yml` orchestrates:
   - Calls `deploy-frontend-infra.yml`
   - Calls `deploy-ui-code.yml`

## Environment Management

- Environments are managed through the `environment` parameter
- Default environment is `dev1`
- Production deployments require manual approval
- Environment-specific configurations are managed through Azure

## Security

- Uses Azure OIDC for authentication
- Secrets are managed through Azure Key Vault
- Environment variables are injected at deployment time
- Access is controlled through Azure RBAC

## Manual Deployment

All workflows can be triggered manually through the GitHub Actions UI with the following parameters:
- `environment`: Target environment (dev1, dev, staging, prod)
- `image_tag`: Docker image tag (for backend deployments)

## Monitoring

- Deployment status can be monitored in GitHub Actions
- Application logs are available in Azure Portal
- Infrastructure status can be checked in Azure Resource Manager 