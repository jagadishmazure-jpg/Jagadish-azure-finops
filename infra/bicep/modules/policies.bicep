// Custom policy definitions, loaded from the same JSON files Terraform uses (infra/policies).
targetScope = 'subscription'

var defs = {
  'require-tags': loadJsonContent('../../policies/require-tags.json')
  'allowed-vm-skus': loadJsonContent('../../policies/allowed-vm-skus.json')
  'deny-untagged-public-ip': loadJsonContent('../../policies/deny-untagged-public-ip.json')
}

resource definitions 'Microsoft.Authorization/policyDefinitions@2023-04-01' = [for d in items(defs): {
  name: 'finops-${d.key}'
  properties: {
    policyType: 'Custom'
    mode: d.value.mode
    displayName: d.value.displayName
    description: d.value.description
    metadata: d.value.metadata
    parameters: d.value.parameters
    policyRule: d.value.policyRule
  }
}]

output ids object = {
  'require-tags': definitions[0].id
  'allowed-vm-skus': definitions[1].id
  'deny-untagged-public-ip': definitions[2].id
}
