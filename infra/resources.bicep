// -------- infra/resources.bicep --------
// MODIFIED (Policy Fix):
// - Set 'enablePurgeProtection' to true for all environments to comply with Azure Policy.
// - Note: Soft delete is automatically enabled when purge protection is enabled.
//   The 'softDeleteRetentionInDays' property is still relevant.

targetScope = 'resourceGroup'

@description('Company prefix for resource names.')
param companyPrefix string = 'sdt'

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string

@description('The environment (e.g., dev, test, prod).')
param environment string // This will be 'dev', 'dev1', 'stg', or 'prod'

@description('Primary Azure region for resource deployment.')
param location string

@description('Short location code for naming convention.')
param locationShort string

// --- Container App Config Parameters ---
@description('Specifies the container image to deploy (e.g., myacr.azurecr.io/myapp:latest).')
param containerImage string

@description('Specifies the CPU allocation for the container app.')
param containerAppCpuCoreCount string = (environment == 'prod') ? '1.0' : '0.5'

@description('Specifies the memory allocation for the container app.')
param containerAppMemoryGiB string = (environment == 'prod') ? '2.0Gi' : '1.0Gi'

@description('Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 1

@description('Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2

// --- Secure Parameters for Secrets ---
@secure()
@description('Required. MongoDB connection string.')
param mongoDbUrl string

@secure()
@description('Required. Kinde client secret for backend validation.')
param kindeClientSecret string

@secure()
@description('Required. Stripe secret key.')
param stripeSecretKey string

@secure()
@description('Required. Connection string for Azure Blob Storage.')
param storageConnectionString string

// --- Kinde non-secret parameters ---
@description('Required. Kinde domain for authentication.')
param kindeDomain string

@description('Required. Kinde audience for authentication.')
param kindeAudience string

param parSubId string = '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parRgName string = 'rg-sdt-uks-aidetector-dev1'

// --- Variables ---
var uniqueSeed = uniqueString(resourceGroup().id)
var shortUniqueSeed = take(uniqueSeed, 8)

var vaultEnvSuffix = (environment == 'stg') ? 'stg' : environment
var storageEnvSuffix = (environment == 'stg') ? 'stg' : environment

var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${vaultEnvSuffix}-${shortUniqueSeed}'
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${storageEnvSuffix}${shortUniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppName = 'ca-${companyPrefix}-${locationShort}-${purpose}-${environment}'

var acrName = toLower('acr${companyPrefix}${purpose}${environment}')
var acrLoginServer = '${acrName}.azurecr.io'

var secretNameCosmosConnectionString = 'cosmos-db-connection-string'
var secretNameKindeClientSecret = 'kinde-client-secret'
var secretNameStripeSecretKey = 'stripe-secret-key'
var secretNameStorageConnectionString = 'storage-connection-string'

var keyVaultSecretsUserRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var acrPullRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

var varUserAssignedIdentity = '/subscriptions/${parSubId}/resourcegroups/${parRgName}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${userAssignedIdentity.name}'

// --- Resource Definitions ---

// Azure Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false
  }
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
}

// Key Vault
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enablePurgeProtection: true // MODIFIED: Set to true to comply with policy for all environments
    softDeleteRetentionInDays: (environment == 'prod') ? 90 : 7 // Keep configurable or set to a standard value like 90
  }

  resource cosmosConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameCosmosConnectionString
    properties: { value: mongoDbUrl }
  }
  resource kindeSecret 'secrets@2023-07-01' = {
    name: secretNameKindeClientSecret
    properties: { value: kindeClientSecret }
  }
  resource stripeSecret 'secrets@2023-07-01' = {
    name: secretNameStripeSecretKey
    properties: { value: stripeSecretKey }
  }
  resource storageConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameStorageConnectionString
    properties: { value: storageConnectionString }
  }
}

// Storage Account
resource st 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    isHnsEnabled: false
  }
}

// Cosmos DB Account with MongoDB API
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: cosmosDbAccountName
  location: location
  kind: 'MongoDB'
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
    capabilities: [ { name: 'EnableMongo' }, { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

// Container Apps Environment
resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppsEnvName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    // zoneRedundant: (environment == 'prod')
  }
}

module userAssignedIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'userAssignedIdentityDeployment'
  params: {
    // Required parameters
    name: 'mi-sdt-uks-ca-${environment}'
    // Non-required parameters
    location: location
  }
}

// Assign AcrPull role to the user-assigned managed identity for the ACR
module acrRoleAssignment './modules/roleAssignment.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'roleAssignmentAcrDeploy'
  params: {
    parAssigneeObjectId: varUserAssignedIdentity
    parAssigneePrincipalType: 'ServicePrincipal'
    parRoleDefinitionId: acrPullRoleDefinitionId
  }
}

// Assign Key Vault Secrets User role to the user-assigned managed identity for the Key Vault
module keyVaultRoleAssignment './modules/roleAssignment.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'roleAssignmentKvDeploy'
  params: {
    parAssigneeObjectId: varUserAssignedIdentity
    parAssigneePrincipalType: 'ServicePrincipal'
    parRoleDefinitionId: keyVaultSecretsUserRoleDefinitionId
  }
}

// Container App
resource ca 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  identity: {
    type: 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '${varUserAssignedIdentity}': {
      }
    }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      identitySettings: [
        {
          identity: varUserAssignedIdentity
          lifecycle: 'All'
        }
      ]
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
      secrets: [
        { name: secretNameCosmosConnectionString, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameCosmosConnectionString}', identity: 'system' }
        { name: secretNameKindeClientSecret, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameKindeClientSecret}', identity: 'system' }
        { name: secretNameStripeSecretKey, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStripeSecretKey}', identity: 'system' }
        { name: secretNameStorageConnectionString, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStorageConnectionString}', identity: 'system' }
      ]
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'backend-api'
          image: containerImage
          resources: {
            cpu: json(containerAppCpuCoreCount)
            memory: containerAppMemoryGiB
          }
          env: [
            { name: 'ENVIRONMENT', value: environment }
            { name: 'MONGODB_URL', secretRef: secretNameCosmosConnectionString }
            { name: 'KINDE_CLIENT_SECRET', secretRef: secretNameKindeClientSecret }
            { name: 'STRIPE_SECRET_KEY', secretRef: secretNameStripeSecretKey }
            { name: 'AZURE_BLOB_CONNECTION_STRING', secretRef: secretNameStorageConnectionString }
            { name: 'KINDE_DOMAIN', value: kindeDomain }
            { name: 'KINDE_AUDIENCE', value: kindeAudience }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 45
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 10
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 60
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: containerAppMinReplicas
        maxReplicas: containerAppMaxReplicas
      }
    }
  }
  dependsOn: [
    keyVaultRoleAssignment
    acrRoleAssignment
  ]
}


// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
output containerAppName string = ca.name
output containerAppPrincipalId string = ca.identity.principalId
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
