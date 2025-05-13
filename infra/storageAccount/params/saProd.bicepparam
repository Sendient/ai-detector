using '../sa.bicep'

param parEnv =  'prod'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parSkuName =  'Standard_LRS'

param parLocation =  'uksouth'

param parSaName =  'sasdtuksaid${parEnv}'

param parSaKind =  'StorageV2'
