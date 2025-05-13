targetScope = 'subscription'

param parSubId string

param parRgName string

// param parPeRgName string

// param parPeName string

// param parDnsSubId string

// param parDnsRgName string

param parEnv string

param parLocation string

param parLockName string

param parMiEnabled bool

param parQuarantinePolicyStatus string

param parSoftDeletePolicyDays int

param paqrSoftDeletePolicyStatus string

param parTrustPolicyStatus string

param parExportPolicyStatus string

// param parPeService string

// param parSubnetId string

// param parPeIpConfigurations array

param parEnableAdminUser bool

param parSku string

// param parLogAnalyticsWorkspaceId string

param parRegistryName string

param parZoneRedundancy string

param parPublicNetworkAccess string

param parNetworkRuleBypassOptions string

param parIpRules array



// resource acrPrivDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing =  {
//   name: 'privatelink.azurecr.io'
//   scope: resourceGroup(parDnsSubId, parDnsRgName)
// }


module registry 'br/public:avm/res/container-registry/registry:0.6.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'registryDeployment-${parEnv}'
  params: {
    // Required parameters
    name: parRegistryName
    // Non-required parameters
    acrAdminUserEnabled: parEnableAdminUser
    acrSku: parSku
    // diagnosticSettings: [
    //   {
    //     metricCategories: [
    //       {
    //         category: 'AllMetrics'
    //       }
    //     ]
    //     name: 'acrDiagnosticSettings'
    //     workspaceResourceId: parLogAnalyticsWorkspaceId
    //   }
    // ]
    location: parLocation
    lock: {
      kind: 'CanNotDelete'
      name: parLockName
    }
    managedIdentities: {
      systemAssigned: parMiEnabled
    }
    networkRuleSetIpRules: parIpRules
    quarantinePolicyStatus: parQuarantinePolicyStatus
    roleAssignments: [
    ]
    softDeletePolicyDays: parSoftDeletePolicyDays
    softDeletePolicyStatus: paqrSoftDeletePolicyStatus
    trustPolicyStatus: parTrustPolicyStatus
    zoneRedundancy: parZoneRedundancy
    publicNetworkAccess: parPublicNetworkAccess
    networkRuleBypassOptions: parNetworkRuleBypassOptions
    exportPolicyStatus: parExportPolicyStatus
    // webhooks: [
    //   {
    //     name: 'acrx001webhook'
    //     serviceUri: 'https://www.contoso.com/webhook'
    //   }
    // ]
  }
}

// module acrPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.8.0' = {
//   scope: resourceGroup(parDnsSubId, parPeRgName)
//   name: 'acrPrivateEndpointDeployment'
//   params: {
//     // Required parameters
//     name: parPeName
//     subnetResourceId: parSubnetId
//     // Non-required parameters
//     ipConfigurations: parPeIpConfigurations
//     location: parLocation
//     privateDnsZoneGroup: {
//       privateDnsZoneGroupConfigs: [
//         {
//           privateDnsZoneResourceId: acrPrivDnsZone.id
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
//           privateLinkServiceId: registry.outputs.resourceId
//         }
//       }
//     ]
//   }
// }


