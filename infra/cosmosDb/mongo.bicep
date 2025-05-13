targetScope = 'subscription'

param parSubId string

param parRgName string

param parLocation string

param parLockName string

// param parLogAnalyticsWorkspaceId string

param parMongoDbName string

param parMongoCollections array

param parMongoDbAccountName string

param parReplicationLocations array

// param parDnsRgName string

// param parPeService string

// param parIpConfigurations array

// param parPeName string

// param parSubnetId string

param parNetworkAclBypass string

param parBackupPolicyContinuousTier string

// param parDnsSubId string

// param parPeRgName string

param parAllowedIPs string[]

param parKvResourceId string

param parMongoCsSecretName string

param parEnv string

// param parServerVersion string

// resource mongoPrivDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing =  {
//   name: 'privatelink.mongo.cosmos.azure.com'
//   scope: resourceGroup(parDnsSubId, parDnsRgName)
// }

module mongoDB 'br/public:avm/res/document-db/database-account:0.6.0' = {
  name: 'mongoDBDeploy-${parEnv}'
  scope: resourceGroup(parSubId, parRgName)
  params: {
    // Required parameters
    name: parMongoDbAccountName
    // serverVersion: parServerVersion
    // Non-required parameters
    capabilitiesToAdd: [
      'EnableMongo'
      'EnableServerless'
    ]
    // diagnosticSettings: [
    //   {
    //     metricCategories: [
    //       {
    //         category: 'AllMetrics'
    //       }
    //     ]
    //     name: 'DiagnosticSetting'
    //     workspaceResourceId: parLogAnalyticsWorkspaceId
    //     logAnalyticsDestinationType: 'Dedicated'
    //   }
    // ]
    location: parLocation
    lock: {
      kind: 'CanNotDelete'
      name: parLockName
    }
    locations: parReplicationLocations
    backupPolicyContinuousTier: parBackupPolicyContinuousTier
    managedIdentities: {
      systemAssigned: true
    }
    networkRestrictions: {
      ipRules: parAllowedIPs
      virtualNetworkRules: []
      networkAclBypass: parNetworkAclBypass
    }
    mongodbDatabases: [
      {
        name: parMongoDbName
        collections: parMongoCollections
      }
    ]
    secretsExportConfiguration: {
      keyVaultResourceId: parKvResourceId
      primaryWriteConnectionStringSecretName: parMongoCsSecretName
    }
    // commented out to deploy private endpoints in separate subscription
    // privateEndpoints: [
    //   {
    //     privateDnsZoneGroup: {
    //       privateDnsZoneGroupConfigs: [
    //         {
    //           privateDnsZoneResourceId: mongoPrivDnsZone.id
    //         }
    //       ]
    //     }
    //     service: parPeService
    //     subnetResourceId: parSubnetId
    //     name: parPeName
    //     resourceGroupName: parRgName
    //     ipConfigurations: parIpConfigurations
    //   }
    // ]
  }
}

// module mongoPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.8.0' = {
//   scope: resourceGroup(parDnsSubId, parPeRgName)
//   name: 'mongoPrivateEndpointDeployment'
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
//           privateDnsZoneResourceId: mongoPrivDnsZone.id
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
//           privateLinkServiceId: mongoDB.outputs.resourceId
//         }
//       }
//     ]
//   }
//   dependsOn: [
//     mongoDB
//   ]
// }
