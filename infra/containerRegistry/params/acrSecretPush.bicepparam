using '../acrSecretPush.bicep'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parEnv =  'dev1'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parKvName = 'kv-sdt-uks-aid-${parEnv}'

param parKvRgName = 'rg-sdt-uks-aid-${parEnv}'

param parKvSecretName = 'acrsdtuksaid${parEnv}-password'

param parKvSubId = parSubId

param parRegistryName = 'acrsdtuksaid${parEnv}'
