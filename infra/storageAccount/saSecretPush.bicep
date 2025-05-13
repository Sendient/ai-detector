targetScope = 'subscription'

param parKvName string

param parKvSecretName string

param parRgName string

param parSubId string

param parEnv string

param parSaName string 


resource storageAccountExisting 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: parSaName
  scope: resourceGroup(parSubId, parRgName)
}

var varSaCs = 'DefaultEndpointsProtocol=https;AccountName=${parSaName};AccountKey=${storageAccountExisting.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

module keyVaultSecretModule '../modules/keyVaultSecret.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'setKeyVaultSecret-${parEnv}'
  params: {
    parKvName: parKvName
    parSecretName: parKvSecretName
    parSecretValue: varSaCs
  }
}
