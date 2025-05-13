targetScope = 'subscription'

param parEnv string

param parSubId string 

param parRgName string


var varUserAssignedIdentity = userAssignedIdentity.outputs.principalId
var location = 'uksouth'
var keyVaultSecretsUserRoleDefinitionId = '4633458b-17de-408a-b874-0445c86b69e6'
var acrPullRoleDefinitionId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

module userAssignedIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'userAssignedIdentityDeployment'
  params: {
    // Required parameters
    name: 'mi-sdt-uks-ca-${parEnv}'
    // Non-required parameters
    location: location
  }
}

// Assign AcrPull role to the user-assigned managed identity for the ACR
module acrRoleAssignment '../modules/roleAssignment.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'roleAssignmentAcrDeploy'
  params: {
    parAssigneeObjectId: varUserAssignedIdentity
    parAssigneePrincipalType: 'ServicePrincipal'
    parRoleDefinitionId: acrPullRoleDefinitionId
  }
}

// Assign Key Vault Secrets User role to the user-assigned managed identity for the Key Vault
module keyVaultRoleAssignment '../modules/roleAssignment.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'roleAssignmentKvDeploy'
  params: {
    parAssigneeObjectId: varUserAssignedIdentity
    parAssigneePrincipalType: 'ServicePrincipal'
    parRoleDefinitionId: keyVaultSecretsUserRoleDefinitionId
  }
}

