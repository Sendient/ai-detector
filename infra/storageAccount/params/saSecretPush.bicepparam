using '../saSecretPush.bicep'

param parKvName = 'kv-sdt-uks-aid-${parEnv}'

param parKvSecretName = 'sa-connection-string-${parEnv}'

param parEnv =  'staging'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parSaName = 'sasdtuksaid${parEnv}'
