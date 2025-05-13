
targetScope = 'subscription'

param parSubId string

param parRgName string

param parEnv string

module staticSite 'br/public:avm/res/web/static-site:0.9.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'staticSiteDeployment'
  params: {
    // Required parameters
    name: 'wsswaf001'
    // Non-required parameters
    allowConfigFileUpdates: true
    appSettings: {
      foo: 'bar'
      setting: 1
    }
    enterpriseGradeCdnStatus: 'Disabled'
    functionAppSettings: {
      foo: 'bar'
      setting: 1
    }
    linkedBackend: {
      resourceId: '<resourceId>'
    }
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
    sku: 'Standard'
    stagingEnvironmentPolicy: 'Enabled'
    tags: {
      AutoDelete: 'No'
    }
    // virtualNetworkResourceId: '<virtualNetworkResourceId>'
  }
}
