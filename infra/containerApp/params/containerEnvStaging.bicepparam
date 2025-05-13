using '../containerEnv.bicep'

param parEnv =  'staging'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parContainerEnvName =  'ce-sdt-uks-aid-${parEnv}'

// param parInfraRg =  'rg-sdt-uks-containerinfra-${parEnv}'

// param parInfraSubnetId =  '/subscriptions/fb011ea5-e0b1-4726-b564-8b1d296fb978/resourceGroups/rg-sdt-uks-spoke-${parEnv}/providers/Microsoft.Network/virtualNetworks/vnet-sdt-uks-spoke-${parEnv}/subnets/snet-sdt-uks-container-${parEnv}'

param parKind =  ''

param parLocation =  'uksouth'

// param parKvName = 'kv-sdt-uks-idty-${parEnv}'

// param parKvSubId = 'fb011ea5-e0b1-4726-b564-8b1d296fb978'

// param parKvRgName = 'rg-sdt-uks-identity-${parEnv}'

// param parKvSecretName = 'log-analytics-workspace-key-${parEnv}'

// param parLogAnalyticsCustomerId =  'fd17a097-9c1a-429a-95dc-43831d3e0295'

// param parPeerAuthEnabled =  false

// param parPeerTrafficEncryptionEnabled =  false

// param parVnetInternalEnabled =  true

// param parPubliicNetworkAccess =  'Enabled'

// param parWorkloadProfiles =  [
//   {
//       workloadProfileType: 'Consumption'
//       name: 'Consumption'
//   }
// ]

// param parZoneRedundantEnabled =  true

// param parDaprConfiguration =  {
//   version: '1.12.5'
// }

// param parKedaConfiguration =  {
//   version: '2.15.1'
// }

//Private Endpoint Params

// param parPeName =  'pe-sdt-uks-ingest-${parEnv}'

// param parDnsSubId =  'a957c3f5-b45c-4848-ba9f-48f1eb1a527d'

// param parDnsRgName = 'rg-sdt-uks-dns-prod'

// param parPeRgName = 'rg-sdt-uks-pe-prod'

// param parPeService = 'managedEnvironments'

// param parSubnetId = '/subscriptions/a957c3f5-b45c-4848-ba9f-48f1eb1a527d/resourceGroups/rg-sdt-uks-hub-prod/providers/Microsoft.Network/virtualNetworks/vnet-sdt-uks-hub-prod/subnets/snet-sdt-uks-pe-prod'

// param parIpConfigurations = [
//           {
//             name: 'primary'
//             properties: {
//               privateIPAddress: '10.2.0.78'
//               groupId: parPeService
//               memberName: 'managedEnvironments'
//           }
//         }
//       ]
