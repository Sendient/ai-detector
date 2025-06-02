targetScope = 'subscription'

param parRgName string

param parSubId string

param parEnv string

param parSaName string 

param parSaKind string

param parLocation string 

param parSkuName string

param parBlobContainers array

param parPublicNetworkAccess string

param parDefaultAction string

module storageAccount 'br/public:avm/res/storage/storage-account:0.19.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'storageAccountDeployment-${parEnv}'
  params: {
    // Required parameters
    name: parSaName
    // Non-required parameters
    kind: parSaKind
    location: parLocation
    skuName: parSkuName
    blobServices: {
      containers: parBlobContainers
    }
    publicNetworkAccess: parPublicNetworkAccess
    networkAcls: {
      defaultAction: parDefaultAction
    }
  }
}

