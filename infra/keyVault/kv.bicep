targetScope = 'subscription'

param parSubId string

param parRgName string

param parKvName string

param parLocation string

param parLockName string

// param parLogAnalyticsWorkspaceId string

param parSoftDeleteRetentionInDays int

param parNetworkAcls object

param parEnv string

// param parDnsRgName string

// param parPeService string

// param parIpConfigurations array

// param parPeName string

// param parSubnetId string

// param parDnsSubId string

// param parPeRgName string

// param parMiNameDev string

// resource kvPrivDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing =  {
//   name: 'privatelink.vaultcore.azure.net'
//   scope: resourceGroup(parDnsSubId, parDnsRgName)
// }

module vault 'br/public:avm/res/key-vault/vault:0.9.0' = {
  name: 'vaultDeployment-${parEnv}'
  scope: resourceGroup(parSubId, parRgName)
  params: {
    // Required parameters
    name: parKvName
    // Non-required parameters
    enableVaultForDeployment: false
    enableVaultForDiskEncryption: false
    enableVaultForTemplateDeployment: false
    location: parLocation
    lock: {
      kind: 'CanNotDelete'
      name: parLockName
    }
    // diagnosticSettings: [
    //   {
    //     workspaceResourceId: parLogAnalyticsWorkspaceId
    //   }
    // ]
    softDeleteRetentionInDays: parSoftDeleteRetentionInDays
    networkAcls: parNetworkAcls
  }
}

// module keyVaultPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.8.0' = {
//   scope: resourceGroup(parDnsSubId, parPeRgName)
//   name: 'kvPrivateEndpointDeployment'
//   params: {
//     // Required parameters
//     name: parPeName
//     subnetResourceId: parSubnetId
//     // Non-required parameters
//     ipConfigurations: parIpConfigurations
//     location: parLocation
//     lock: {
//       kind: 'CanNotDelete'
//       name: parLockName
//     }
//     privateDnsZoneGroup: {
//       privateDnsZoneGroupConfigs: [
//         {
//           privateDnsZoneResourceId: kvPrivDnsZone.id
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
//           privateLinkServiceId: vault.outputs.resourceId
//         }
//       }
//     ]
//   }
// }

// module KvUserAssignedIdentity 'br:mcr.microsoft.com/bicep/avm/res/managed-identity/user-assigned-identity:0.4.0' = {
//   scope: resourceGroup(parSubId, parRgName)
//   name: 'kvUserAssignedIdentityDeployment'
//   params: {
//     // Required parameters
//     name: parMiNameDev
//     // Non-required parameters
//     location: parLocation
//   }
// }

// module KvRoleAssignment '../modules/roleAssignment.bicep' = {
//   scope: resourceGroup(parSubId, parRgName)
//   name: 'devKvRoleAssignment'
//   params: {
//     parAssigneeObjectId: KvUserAssignedIdentity.outputs.principalId
//     parAssigneePrincipalType: 'ServicePrincipal'
//     parRoleDefinitionId: '4633458b-17de-408a-b874-0445c86b69e6'
//   }
// }

