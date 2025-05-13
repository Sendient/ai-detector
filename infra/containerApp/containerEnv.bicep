targetScope = 'subscription'

param parSubId string

param parRgName string  

param parContainerEnvName string

// param parInfraRg string

// param parInfraSubnetId string

param parKind string

param parLocation string

// param parKvName string

// param parKvSubId string

// param parKvRgName string

// param parKvSecretName string

// param parLogAnalyticsCustomerId string

// param parPeerAuthEnabled bool

// param parPeerTrafficEncryptionEnabled bool

// param parVnetInternalEnabled bool

// param parWorkloadProfiles array

// param parZoneRedundantEnabled bool

// param parDaprConfiguration object

// param parKedaConfiguration object

// param parPubliicNetworkAccess string

param parEnv string

//Private Endpoint Params

// param parPeName string

// param parSubnetId string

// param parIpConfigurations array

// param parPeService string

// param parDnsSubId string

// param parPeRgName string

// param parDnsRgName string

// resource containerEnvPrivDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing =  {
//   name: 'privatelink.uksouth.azurecontainerapps.io'
//   scope: resourceGroup(parDnsSubId, parDnsRgName)
// }

// resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
//   name: parKvName
//   scope: resourceGroup(parKvSubId, parKvRgName)
// }

module containerEnv '../modules/containerAppEnv.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'containerEnvDeployment-${parEnv}'
  params: {
    parContainerEnvName: parContainerEnvName
    // parInfraRg: parInfraRg
    // parInfraSubnetId: parInfraSubnetId
    parKind: parKind
    parLocation: parLocation
    // parLogAnalyticsCustomerId: parLogAnalyticsCustomerId
    // parPeerAuthEnabled: parPeerAuthEnabled
    // parPeerTrafficEncryptionEnabled: parPeerTrafficEncryptionEnabled
    // parVnetInternalEnabled: parVnetInternalEnabled
    // parWorkloadProfiles: parWorkloadProfiles
    // parZoneRedundantEnabled: parZoneRedundantEnabled
    // parDaprConfiguration: parDaprConfiguration
    // parKedaConfiguration: parKedaConfiguration
    // parPublicNetworkAccess: parPubliicNetworkAccess
    // parLogAnalyticsKey: keyVault.getSecret(parKvSecretName)
    }
  }

//   module containerEnvPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.8.0' = {
//   scope: resourceGroup(parDnsSubId, parPeRgName)
//   name: 'ContainerPrivateEndpointDeployment'
//   params: {
//     // Required parameters
//     name: parPeName
//     subnetResourceId: parSubnetId
//     // Non-required parameters
//     ipConfigurations: parIpConfigurations
//     location: parLocation
//     privateDnsZoneGroup: {
//       privateDnsZoneGroupConfigs: [
//         {
//           privateDnsZoneResourceId: containerEnvPrivDnsZone.id
//         }
//       ]
//     }
//     privateLinkServiceConnections: [
//       {
//         name: parPeName
//         properties: {
//           groupIds: [
//             parPeService
//           ]
//           privateLinkServiceId: containerEnv.outputs.containerEnvResourceId
//         }
//       }
//     ]
//   }
// }
