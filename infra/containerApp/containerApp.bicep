targetScope = 'subscription'

param parEnv string

param parSubId string

param parRgName string

param parEnvVariables01 array

param parProbes01 array

param parContainerResources01 object

param parContainerAppName string

param parContainerEnvResourceId string

param parSecretList array

param parAlowHttp bool

param parRoleAssignments array

param parLocation string

param parMiEnabled bool

param parScaleRules array

param parRegistriesCredentials array

param parContainerName01 string

param parContainerImage01 string

param parActiveRevisionsMode string

param parDisableIngress bool

param parDapr object

param parScaleMaxReplicas int

param parScaleMinReplicas int

param parTargetPort int

param parUserMi string

param parIPRules array

param parCorsAllowedOrigins array

param parAllowCredentials bool

param parFrontendUrl string

param parAllowedMethods array

module containerApp 'br/public:avm/res/app/container-app:0.11.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'containerAppDeployment-${parEnv}'
  params: {
    // Required parameters
    name: parContainerAppName
    containers: [
      {
        name: parContainerName01
        env: parEnvVariables01
        image: parContainerImage01
        probes: parProbes01
        resources: parContainerResources01
      }
    ]
    registries: parRegistriesCredentials
    activeRevisionsMode: parActiveRevisionsMode
    dapr: parDapr
    environmentResourceId: parContainerEnvResourceId
    // Non-required parameters
    location: parLocation
    managedIdentities: {
      systemAssigned: parMiEnabled
      userAssignedResourceIds: [
        parUserMi
      ]
    }
    scaleRules: parScaleRules
    scaleMaxReplicas: parScaleMaxReplicas
    scaleMinReplicas: parScaleMinReplicas
    disableIngress: parDisableIngress
    ingressAllowInsecure: parAlowHttp
    ingressTargetPort: parTargetPort
    ipSecurityRestrictions: parIPRules
    roleAssignments: parRoleAssignments
    corsPolicy: {
      allowCredentials: parAllowCredentials
      allowedOrigins: parCorsAllowedOrigins
      allowedMethods: parAllowedMethods
    }
    secrets: {
      secureList: parSecretList
    }
    lock: {
      kind: 'CanNotDelete'
      name: 'AccidentalDeletionPrevention'
    }
    tags: {
      frontendUrl: parFrontendUrl
    }
  }
}

