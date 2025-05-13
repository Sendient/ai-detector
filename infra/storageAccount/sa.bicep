targetScope = 'subscription'

param parRgName string

param parSubId string

param parEnv string

param parSaName string 

param parSaKind string

param parLocation string 

param parSkuName string


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
  }
}


