// Bicep file for core infrastructure
// Creates App Service, Application Insights, Log Analytics, and Key Vault
// Uses parameterized resource names for environment isolation

param environmentName string
param location string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)
var resourcePrefix = 'zebraai'
var appServiceName = '${resourcePrefix}-${resourceToken}-webapp'
var appInsightsName = '${resourcePrefix}-${resourceToken}-ai'
var logAnalyticsName = '${resourcePrefix}-${resourceToken}-logs'
var keyVaultName = '${resourcePrefix}${resourceToken}kv'
var userAssignedIdentityName = '${resourcePrefix}-${resourceToken}-identity'

resource userAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: userAssignedIdentityName
  location: location
}

resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${resourcePrefix}-${resourceToken}-plan'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
}

resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: appServiceName
  location: location
  kind: 'app'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      cors: {
        allowedOrigins: [ '*' ]
        supportCredentials: false
      }
    }
  }
  tags: {
    'azd-env-name': environmentName
    'azd-service-name': 'zebraai-webapp'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2021-06-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    accessPolicies: []
    enabledForDeployment: true
    enabledForTemplateDeployment: true
    enabledForDiskEncryption: true
    enableSoftDelete: true
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}

output webAppName string = webApp.name
output appInsightsName string = appInsights.name
output logAnalyticsName string = logAnalytics.name
output keyVaultName string = keyVault.name
output RESOURCE_GROUP_ID string = resourceGroup().id
