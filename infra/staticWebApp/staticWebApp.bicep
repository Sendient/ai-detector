
targetScope = 'subscription'

param parSubId string

param parRgName string

param parEnv string

param parAppSettings object

param parAppName string

param parAllowConfigFileUpdates bool

param parSku string

param parStagingEnvironmentPolicy string

param parCustomDomainName string

// param parBackendId string

param parLocation string

module staticSite 'br/public:avm/res/web/static-site:0.9.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'staticWebSiteDeploy-${parEnv}'
  params: {
    // Required parameters
    name: parAppName
    location: parLocation
    // Non-required parameters
    allowConfigFileUpdates: parAllowConfigFileUpdates
    appSettings: parAppSettings
    enterpriseGradeCdnStatus: 'Disabled'
    functionAppSettings: parAppSettings
    // linkedBackend: {
    //   resourceId: parBackendId
    // }
    // privateEndpoints: [
    //   {
    //     privateDnsZoneGroup: {
    //       privateDnsZoneGroupConfigs: [
    //         {
    //           privateDnsZoneResourceId: '<privateDnsZoneResourceId>'
    //         }
    //       ]
    //     }
    //     subnetResourceId: '<subnetResourceId>'
    //     tags: {
    //       Environment: 'Non-Prod'
    //       'hidden-title': 'This is visible in the resource name'
    //       Role: 'DeploymentValidation'
    //     }
    //   }
    // ]
    sku: parSku
    stagingEnvironmentPolicy: parStagingEnvironmentPolicy
    customDomains: [
    {
    name: parCustomDomainName
    validationMethod: 'CNAME'
    }
  ]
    tags: {
      AutoDelete: 'No'
    }
    // virtualNetworkResourceId: '<virtualNetworkResourceId>'
  }
}
