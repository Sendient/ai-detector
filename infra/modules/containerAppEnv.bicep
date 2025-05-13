param parContainerEnvName string

// param parInfraRg string

// param parInfraSubnetId string

param parKind string

param parLocation string

// param parLogAnalyticsCustomerId string

// @secure()
// param parLogAnalyticsKey string

// param parPeerAuthEnabled bool

// param parPeerTrafficEncryptionEnabled bool

// param parVnetInternalEnabled bool

// param parWorkloadProfiles array

// param parZoneRedundantEnabled bool

// param parDaprConfiguration object

// param parKedaConfiguration object

// param parPublicNetworkAccess string

resource ContainerEnvironment 'Microsoft.App/managedEnvironments@2024-10-02-preview' = {
  kind: parKind
  location: parLocation
  name: parContainerEnvName
  properties: {
    // appLogsConfiguration: {
    //   destination: 'log-analytics'
    //   logAnalyticsConfiguration: {
    //     customerId: parLogAnalyticsCustomerId
    //     sharedKey: parLogAnalyticsKey
    //     dynamicJsonColumns: false
    //   }
    // }
    // No custom domain needed for environment - will be used at app level
    // customDomainConfiguration: {
    //   certificatePassword: 'string'
    //   certificateValue: any(Azure.Bicep.Types.Concrete.AnyType)
    //   dnsSuffix: 'string'
    // }
    // No dapr yet
    // daprAIConnectionString: 'string'
    // daprAIInstrumentationKey: 'string'
    // daprConfiguration: parDaprConfiguration
    // infrastructureResourceGroup: parInfraRg
    // kedaConfiguration: parKedaConfiguration
    // peerAuthentication: {
    //   mtls: {
    //     enabled: parPeerAuthEnabled
    //   }
    // }
    // peerTrafficConfiguration: {
    //   encryption: {
    //     enabled: parPeerTrafficEncryptionEnabled
    //   }
    // }
    // publicNetworkAccess: parPublicNetworkAccess
    // vnetConfiguration: {
    //   // No docker bridge CIDR yet
    //   // dockerBridgeCidr: 'string'
    //   infrastructureSubnetId: parInfraSubnetId
    //   internal: parVnetInternalEnabled
    //   // Do not need to specify the platform reserved CIDR or DNS IP
    //   // platformReservedCidr: 'string'
    //   // platformReservedDnsIP: 'string'
    // }
    // workloadProfiles: parWorkloadProfiles
    // zoneRedundant: parZoneRedundantEnabled
  }
  // tags: {
  // }
}

output containerEnvResourceId string = ContainerEnvironment.id
