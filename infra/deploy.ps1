
// Deploy user MI
az deployment sub create --name "userMIDeployDev" --location "uksouth" --template-file ".\infra\managedIdentities\mi.bicep" --parameters '.\infra\managedIdentities\params\miDev.bicepparam'
az deployment sub create --name "userMIDeployStaging" --location "uksouth" --template-file ".\bicep\managedIdentities\mi.bicep" --parameters '.\bicep\managedIdentities\params\miStaging.bicepparam'
az deployment sub create --name "userMIDeployProd" --location "uksouth" --template-file ".\bicep\managedIdentities\mi.bicep" --parameters '.\bicep\managedIdentities\params\miProd.bicepparam'

//Deploy Key Vault
az deployment sub create --name "keyVaultDeployDev" --location "uksouth" --template-file ".\infra\keyVault\kv.bicep" --parameters '.\infra\keyVault\params\devKv.bicepparam'
az deployment sub create --name "keyVaultDeployStaging" --location "uksouth" --template-file ".\bicep\keyVault\kv.bicep" --parameters '.\bicep\keyVault\params\stagingKv.bicepparam'
az deployment sub create --name "keyVaultDeployProd" --location "uksouth" --template-file ".\bicep\keyVault\kv.bicep" --parameters '.\bicep\keyVault\params\prodKv.bicepparam'

//Deploy Mongo
az deployment sub create --name "mongoDBDeployDev" --location "uksouth" --template-file ".\infra\cosmosDb\mongo.bicep" --parameters '.\infra\cosmosDb\params\mongoDev.bicepparam'
az deployment sub create --name "mongoDBDeployStaging" --location "uksouth" --template-file ".\bicep\cosmosDb\mongo.bicep" --parameters '.\bicep\cosmosDb\params\mongoStaging.bicepparam'
az deployment sub create --name "mongoDBDeployProd" --location "uksouth" --template-file ".\bicep\cosmosDb\mongo.bicep" --parameters '.\bicep\cosmosDb\params\mongoProd.bicepparam'

//Deploy ACR
az deployment sub create --name "acrDeployDev" --location "uksouth" --template-file ".\infra\containerRegistry\acr.bicep" --parameters '.\infra\containerRegistry\params\acrDev.bicepparam'
az deployment sub create --name "acrDeployStaging" --location "uksouth" --template-file ".\bicep\containerRegistry\acr.bicep" --parameters '.\bicep\containerRegistry\params\acrStaging.bicepparam'
az deployment sub create --name "acrDeployProd" --location "uksouth" --template-file ".\bicep\containerRegistry\acr.bicep" --parameters '.\bicep\containerRegistry\params\acrProd.bicepparam'

//Deploy Storage Account
az deployment sub create --name "storageAccountDeployDev" --location "uksouth" --template-file ".\infra\storageAccount\sa.bicep" --parameters '.\infra\storageAccount\params\saDev.bicepparam'
az deployment sub create --name "storageAccountDeployStaging" --location "uksouth" --template-file ".\bicep\storageAccount\sa.bicep" --parameters '.\bicep\storageAccount\params\saStaging.bicepparam'
az deployment sub create --name "storageAccountDeployProd" --location "uksouth" --template-file ".\bicep\storageAccount\sa.bicep" --parameters '.\bicep\storageAccount\params\saProd.bicepparam'

//Deploy Container App Environment
az deployment sub create --name "containerAppEnvDeployDev" --location "uksouth" --template-file ".\infra\containerApp\containerEnv.bicep" --parameters '.\infra\containerApp\params\containerEnvDev.bicepparam'
az deployment sub create --name "containerAppEnvDeployStaging" --location "uksouth" --template-file ".\bicep\containerApp\containerEnv.bicep" --parameters '.\bicep\containerApp\params\containerEnvStaging.bicepparam'
az deployment sub create --name "containerAppEnvDeployProd" --location "uksouth" --template-file ".\bicep\containerApp\containerEnv.bicepparam" --parameters '.\bicep\containerApp\params\containerEnvProd.bicepparam'

//Deploy Container App
az deployment sub create --name "containerAppDeployDev" --location "uksouth" --template-file ".\infra\containerApp\containerApp.bicep" --parameters '.\infra\containerApp\params\containerAppDev.bicepparam'
az deployment sub create --name "containerAppDeployStaging" --location "uksouth" --template-file ".\bicep\containerApp\containerApp.bicep" --parameters '.\bicep\containerApp\params\containerAppStaging.bicepparam'
az deployment sub create --name "containerAppDeployProd" --location "uksouth" --template-file ".\bicep\containerApp\containerApp.bicep" --parameters '.\bicep\containerApp\params\containerAppProd.bicepparam'