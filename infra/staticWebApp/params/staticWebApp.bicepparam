using '../staticWebApp.bicep'

param parAppSettings =  {
      // foo: 'bar'
      // setting: 1
    }

param parEnv =  'dev1'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

param parAllowConfigFileUpdates =  true

param parAppName =  'app-sdt-uks-aid-${parEnv}'

// param parBackendId = 'https://ca-sdt-uks-aid-dev1.lemonfield-d5c79fcf.uksouth.azurecontainerapps.io'

param parSku =  'Standard'

param parStagingEnvironmentPolicy =  'Enabled'

param parLocation =  'westeurope'

param parCustomDomains = [
  {
    name: 'dev-app.smartdetector.ai'
    validationMethod: 'CNAME'
  }
]
