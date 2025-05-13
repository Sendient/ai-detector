using '../acr.bicep'

param parRegistryName =  'acrsdtuksaid${parEnv}'

param paqrSoftDeletePolicyStatus =  'enabled'

param parEnableAdminUser =  true

param parLocation =  'uksouth'

param parLockName = 'deleteLock'

// param parLogAnalyticsWorkspaceId = '/subscriptions/fb011ea5-e0b1-4726-b564-8b1d296fb978/resourceGroups/rg-sdt-uks-logging-${parEnv}/providers/Microsoft.OperationalInsights/workspaces/log-sdt-uks-mgmt-${parEnv}'

param parMiEnabled =  true

param parQuarantinePolicyStatus =  'disabled'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parEnv =  'staging'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parSku =  'Premium'

param parSoftDeletePolicyDays =  7

param parTrustPolicyStatus =  'enabled'

param parZoneRedundancy =  'Disabled'

param parExportPolicyStatus =  'enabled'

param parPublicNetworkAccess =  'Enabled'

param parNetworkRuleBypassOptions =  'AzureServices'

param parIpRules = []

//Private Endpoint params

// param parSubnetId =  '/subscriptions/a957c3f5-b45c-4848-ba9f-48f1eb1a527d/resourceGroups/rg-sdt-uks-hub-prod/providers/Microsoft.Network/virtualNetworks/vnet-sdt-uks-hub-prod/subnets/snet-sdt-uks-pe-prod'

// param parPeName =  'pe-sdt-uks-acr-${parEnv}'

// param parPeRgName =  'rg-sdt-uks-pe-prod'

// param parPeService =  'registry'

// param parDnsRgName =  'rg-sdt-uks-dns-prod'

// param parDnsSubId =  'a957c3f5-b45c-4848-ba9f-48f1eb1a527d'

// param parPeIpConfigurations = [
//         {
//             name: 'primary'
//             properties: {
//               privateIPAddress: '10.2.0.46'
//               groupId: parPeService
//               memaidrName: 'registry'
//           }
//         }
//         {
//             name: 'secondary'
//             properties: {
//               privateIPAddress: '10.2.0.47'
//               groupId: parPeService
//               memaidrName: 'registry_data_uksouth'
//           }
//         }
//     ]


