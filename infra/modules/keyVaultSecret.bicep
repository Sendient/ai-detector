param parKvName string
param parSecretName string
@secure()
param parSecretValue string

// Reference existing Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: parKvName
}

// Deploy the secret into Key Vault
resource keyVaultSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: parSecretName
  properties: {
    value: parSecretValue
  }
}
