# AI Detector Infrastructure

This repository contains the Azure Bicep infrastructure as code (IaC) for the AI Detector application. The infrastructure is built using Azure Verified Modules (AVM) and follows Azure best practices for security and scalability.

## Overview

The infrastructure is designed to support a containerized application with multiple environments (dev, dev1, stg, prod) deployed through GitHub workflows. The environment selection is controlled via the `parEnv` parameter in the workflow files rather than using separate parameter files for each environment.

## Infrastructure Structure

The infrastructure is organized into modular components, each in its own directory:
- `containerApp/`: Container App configuration
- `containerRegistry/`: Azure Container Registry setup
- `cosmosDb/`: Cosmos DB with MongoDB API configuration
- `keyVault/`: Key Vault and secrets management
- `managedIdentities/`: User-assigned managed identities
- `modules/`: Reusable Bicep modules
- `staticWebApp/`: Static Web App configuration
- `storageAccount/`: Storage account setup

## Deployed Resources

### 1. Azure Container Registry (ACR)
- Standard SKU
- Admin user disabled for security
- Used for storing and managing container images

### 2. Azure Key Vault
- Standard SKU
- RBAC authorization enabled
- Purge protection enabled
- Soft delete retention:
  - Production: 90 days
  - Non-production: 7 days
- Stores sensitive configuration:
  - MongoDB connection string
  - Kinde client secret
  - Stripe secret key
  - Storage connection string

### 3. Azure Storage Account
- Standard LRS SKU
- StorageV2 kind
- Public blob access disabled
- TLS 1.2 minimum version
- Hierarchical namespace disabled

### 4. Azure Cosmos DB
- MongoDB API
- Serverless capability enabled
- Session consistency level
- Single region deployment

### 5. Azure Container Apps Environment
- Managed environment for container apps
- Supports scaling and networking features

### 6. Azure Container App
- Configurable CPU and memory allocation:
  - Production: 1.0 CPU, 2.0 GiB memory
  - Non-production: 0.5 CPU, 1.0 GiB memory
- Auto-scaling configuration:
  - Production: 1-5 replicas
  - Non-production: 1-2 replicas
- System and User-assigned managed identity

### 7. Managed Identities
- User-assigned managed identity for container app
- Role assignments:
  - ACR Pull role for container registry access
  - Key Vault Secrets User role for secret access

## Deployment

The infrastructure is deployed through GitHub workflows. The `deploy.ps1` script in this repository is maintained for local reference and documentation of deployment commands, but actual deployments are performed through CI/CD pipelines.

The deployment process:
1. Creates a resource group if it doesn't exist
2. Deploys the main Bicep template and its modules
3. Sets up all required resources and their configurations
4. Configures necessary role assignments and permissions

## Security Features

- RBAC authorization for Key Vault
- Purge protection enabled
- Soft delete retention periods
- TLS 1.2 enforcement
- Public access disabled where applicable
- Managed identities for secure access
- Secure parameter handling for sensitive data

## Naming Conventions

Resources follow a consistent naming pattern:
- Resource Group: `rg-{companyPrefix}-{locationShort}-{purpose}-{environment}`
- Key Vault: `kv-{companyPrefix}-{locationShort}-{environment}-{uniqueSeed}`
- Storage Account: `st{companyPrefix}{locationShort}{purpose}{environment}{uniqueSeed}`
- Cosmos DB: `cosmos-{companyPrefix}-{locationShort}-{purpose}-{environment}`
- Container Apps Environment: `cae-{companyPrefix}-{locationShort}-{purpose}-{environment}`
- Container App: `ca-{companyPrefix}-{locationShort}-{purpose}-{environment}`
- ACR: `acr{companyPrefix}{purpose}{environment}`

## Environment Management

Instead of using separate parameter files for different environments, the infrastructure uses a single parameter file with environment-specific values controlled through GitHub workflow variables. This approach:

- Simplifies maintenance
- Reduces duplication
- Ensures consistency across environments
- Allows for easy environment switching through CI/CD

## Required Parameters

The following parameters must be provided during deployment:

- `companyPrefix`: Company prefix for resource names
- `purpose`: Application purpose/name
- `environment`: Deployment environment
- `location`: Azure region
- `deploymentSuffix`: Unique suffix for deployment
- `containerImage`: Container image to deploy
- Secure parameters (MongoDB URL, Kinde secrets, Stripe key, Storage connection string)
- Kinde configuration (domain and audience) 