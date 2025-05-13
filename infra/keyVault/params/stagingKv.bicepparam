using '../kv.bicep'

param parKvName =  'kv-sdt-uks-aid-${parEnv}'

param parLocation =  'uksouth'

param parLockName = 'deleteLock'

param parEnv =  'staging'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parSoftDeleteRetentionInDays =  7

param parNetworkAcls = {
  bypass: 'AzureServices'
  defaultAction: 'Allow'
  ipRules: []
  virtualNetworkRules: []
}

// param parLogAnalyticsWorkspaceId =  '/subscriptions/fb011ea5-e0b1-4726-b564-8b1d296fb978/resourceGroups/rg-sdt-uks-logging-dev/providers/Microsoft.OperationalInsights/workspaces/log-sdt-uks-mgmt-dev'

// param parDnsRgName = 'rg-sdt-uks-dns-prod'

// param parPeService = 'vault'

// param parIpConfigurations = [
//           {
//             name: 'primary'
//             properties: {
//               privateIPAddress: '10.2.0.24'
//               groupId: parPeService
//               memberName: 'default'
//           }
//         }
//     ]

// param parPeName = 'pe-sdt-uks-kv-dev'

// param parSubnetId = '/subscriptions/a957c3f5-b45c-4848-ba9f-48f1eb1a527d/resourceGroups/rg-sdt-uks-hub-prod/providers/Microsoft.Network/virtualNetworks/vnet-sdt-uks-hub-prod/subnets/snet-sdt-uks-pe-prod'

// param parDnsSubId =  'a957c3f5-b45c-4848-ba9f-48f1eb1a527d'

// param parPeRgName = 'rg-sdt-uks-pe-prod'

// param parMiNameDev = 'mi-sdt-uks-kv-dev'
