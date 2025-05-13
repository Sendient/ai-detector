using '../containerApp.bicep'


param parEnv =  'dev1'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parUserMi = '/subscriptions/${parSubId}/resourcegroups/${parRgName}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mi-sdt-uks-ca-${parEnv}'

param parRegistriesCredentials = [
  {
    server: 'acrsdtuksaid${parEnv}.azurecr.io'
    username: 'acrsdtuksaid${parEnv}'
    passwordSecretRef: 'acrsdtuksaid${parEnv}-password'
  }
]

param parEnvVariables01 = [
  {
    name: 'ENVIRONMENT'
    value: parEnv
  }
  {
    name: 'MONGODB_URL'
    secretRef: 'cosmos-db-connection-string'
    // value: 'mongodb://cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw:BxElpPHLdWJpyC9hdK8Go8q7k2jibQnN4p80SGYO5rlHi6b3Dvvz0dJwtIqMPgNmKmSbgc7gUlojACDbJRZupw==@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw@'
  }
  {
    name: 'KINDE_CLIENT_SECRET'
    secretRef: 'kinde-client-secret'
  }
  {
    name: 'STRIPE_SECRET_KEY'
    secretRef: 'stripe-secret-key'
  }
  {
    name: 'AZURE_BLOB_CONNECTION_STRING'
    secretRef: 'storage-connection-string'
  }
  {
    name: 'KINDE_DOMAIN'
    value: 'https://aidetector.kinde.com'
  }
  {
    name: 'KINDE_AUDIENCE'
    value: 'https://api.aidetector.sendient.ai'
  }
  {
    name: 'MONGO_DATABASE_NAME'
    value: 'aidetector_${parEnv}'
    // value: 'aidetector_dev'
  }
]

// Follow the secret refs from the env variables and registries
param parSecretList = [
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-aid-${parEnv}.vault.azure.net/secrets/mongodb-aid-cs-${parEnv}'
          name: 'cosmos-db-connection-string'
        }
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-aid-${parEnv}.vault.azure.net/secrets/acrsdtuksaid${parEnv}-password'
          name: 'acrsdtuksaid${parEnv}-password'
        }
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-aid-${parEnv}.vault.azure.net/secrets/sa-connection-string-${parEnv}'
          name: 'storage-connection-string'
        }
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-aid-${parEnv}.vault.azure.net/secrets/kinde-secret-${parEnv}'
          name: 'kinde-client-secret'
        }
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-aid-${parEnv}.vault.azure.net/secrets/stripe-secret-${parEnv}'
          name: 'stripe-secret-key'
        }
      ]

param parProbes01 = [
            // {
            //   type: 'Liveness'
            //   httpGet: { path: '/healthz', port: 8000, scheme: 'HTTP' }
            //   initialDelaySeconds: 45
            //   periodSeconds: 30
            //   failureThreshold: 3
            //   timeoutSeconds: 10
            // }
            // {
            //   type: 'Readiness'
            //   httpGet: { path: '/readyz', port: 8000, scheme: 'HTTP' }
            //   initialDelaySeconds: 60
            //   periodSeconds: 30
            //   failureThreshold: 3
            //   timeoutSeconds: 15
            // }
        ]

param parContainerName01 = 'container-sdt-uks-aid-${parEnv}'

param parContainerResources01 = {
          cpu: '0.5'
          memory: '1Gi'
        }

param parScaleRules = [
    ]

param parScaleMaxReplicas = 2

param parScaleMinReplicas = 0

param parContainerAppName = 'ca-sdt-uks-aid-${parEnv}'

// Set to true to entirely disable ingress and void the other ingress settings
param parDisableIngress = false

param parContainerImage01 = 'acrsdtuksaid${parEnv}.azurecr.io/backend-api:latest'

// For CI/CD, use output of container env deployment
param parContainerEnvResourceId = '/subscriptions/${parSubId}/resourceGroups/${parRgName}/providers/Microsoft.App/managedEnvironments/ce-sdt-uks-aid-${parEnv}'

param parAlowHttp = false

param parTargetPort = 8000

param parLocation = 'uksouth'

param parMiEnabled = true

param parActiveRevisionsMode = 'Single'

param parDapr = {
  
}

param parRoleAssignments = [
    ]

param parIPRules = []
