targetScope = 'subscription'

param parKvName string

param parKvRgName string

param parKvSecretName string

param parKvSubId string

param parRegistryName string

param parSubId string

param parRgName string

param parEnv string

// Reference the existing Azure Container Registry (ACR)
resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  scope: resourceGroup(parSubId, parRgName)
  name: parRegistryName
}

// Retrieve the admin credentials for ACR
var varAcrCredentials = acr.listCredentials('2025-04-01')

// Extract the ACR admin password
var varAcrAdminPassword = varAcrCredentials.passwords[0].value

module keyVaultSecretModule '../modules/keyVaultSecret.bicep' = {
  scope: resourceGroup(parKvSubId, parKvRgName)
  name: 'setKeyVaultSecret-${parEnv}'
  params: {
    parKvName: parKvName
    parSecretName: parKvSecretName
    parSecretValue: varAcrAdminPassword
  }
  dependsOn: [
    acr
  ]
}
