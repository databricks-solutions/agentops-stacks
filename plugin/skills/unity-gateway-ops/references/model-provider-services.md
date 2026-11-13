# Model provider services in DAB

Use this reference when adding a `model_provider_services` resource. The
primary schema reference is the Databricks documentation for
[model provider services](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_provider_service)
and
[model provider service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_provider_service-config).
Confirm provider-specific fields against the installed
`databricks bundle schema` before editing.

## V1 contract

- Create one new top-level `model_provider_services` entry.
- Use explicit targets; keep `allow_all_targets: false`.
- Keep all forwarding settings false.
- Reference a customer-owned UC secret or supported service credential. Never
  store plaintext credentials in the project.
- Use the same provider, targets, forwarding policy, rate limits, pricing, and
  grants in every target. Environment-local credentials may have different
  values but should resolve through the same target-aware naming convention.
- Do not adopt, replace, rename, or delete a service.

## Required resource fields

```yaml
resources:
  model_provider_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${resources.schemas.project_schema.name}
      model_provider_service_id: <unqualified-service-id>
      config:
        provider_type: <provider-enum>
        <matching-provider-field>: {}
        allow_all_targets: false
        targets:
          - model: <exact-provider-model>
            native_api_types:
              - <exact-native-api-type>
```

`parent` and `model_provider_service_id` are required. `config.provider_type`
is required by the service API and cannot be changed after creation. Set
exactly one matching provider field.

Supported providers in CLI v1.26.0:

| Provider enum | Config field | Direct configuration |
|---|---|---|
| `EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI` | `openai` | `api_key`; optional `base_url`, `organization` |
| `EXTERNAL_MODEL_PROVIDER_TYPE_AZURE_OPENAI` | `azure_openai` | `base_url` plus one supported authentication mode |
| `EXTERNAL_MODEL_PROVIDER_TYPE_ANTHROPIC` | `anthropic` | exactly one of `direct.api_key` or `relayed` |
| `EXTERNAL_MODEL_PROVIDER_TYPE_AMAZON_BEDROCK` | `amazon_bedrock` | `region` plus one supported authentication mode |
| `EXTERNAL_MODEL_PROVIDER_TYPE_CUSTOM` | `custom` | `base_url` plus bearer `api_key` or `header_auth` |
| `EXTERNAL_MODEL_PROVIDER_TYPE_MICROSOFT_FOUNDRY` | `microsoft_foundry` | `base_url` plus one supported authentication mode |
| `EXTERNAL_MODEL_PROVIDER_TYPE_GEMINI_ENTERPRISE` | `gemini_enterprise` | `project_id`, `region`, and supported authentication |
| `EXTERNAL_MODEL_PROVIDER_TYPE_BEDROCK_MANTLE` | `bedrock_mantle` | Bedrock region and supported authentication |

Provider availability and credential support depend on workspace cloud and
provider. Do not invent a provider-specific field from another provider.

## Targets and forwarding

Each target requires `model`; provider-service targets require at least one
`native_api_types` value. `endpoint_route` is available only for supported
custom-provider targets.

Use these v1 defaults:

```yaml
allow_all_targets: false
forward_headers: false
forward_query_parameters: false
forward_unmanaged_paths: false
```

Enabling forwarding broadens the upstream request surface and is out of scope
for v1. A custom provider must list explicit targets and cannot enable
`allow_all_targets`.

## Secret and credential references

For a provider field that accepts `ProviderSecret`, use a UC secret reference:

```yaml
api_key:
  secret_reference:
    name: secrets/${var.catalog}.${var.schema}.<secret-name>
```

The service owner needs continued access to that secret. Rotation updates the
secret value without changing the provider service.

Where the selected provider and workspace cloud support a UC service
credential, the shape is:

```yaml
service_credential:
  name: credentials/<exact-credential-name>
```

Do not put `plaintext` anywhere in the bundle. Do not request credential values
in conversation. If the exact non-plaintext reference is unavailable, stop
instead of writing a placeholder that appears deployable.

## Minimal OpenAI example

```yaml
resources:
  model_provider_services:
    external_openai:
      parent: schemas/${var.catalog}.${resources.schemas.project_schema.name}
      model_provider_service_id: external-openai
      comment: "Governed external provider for ${bundle.name}"
      config:
        provider_type: EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI
        openai:
          direct:
            api_key:
              secret_reference:
                name: secrets/${var.catalog}.${var.schema}.openai-api-key
        allow_all_targets: false
        targets:
          - model: <exact-provider-model>
            native_api_types:
              - openai/v1/chat/completions
        forward_headers: false
        forward_query_parameters: false
        forward_unmanaged_paths: false
      grants:
        - principal: <consumer-principal>
          privileges:
            - EXECUTE
```

Use an exact API type supported by the selected upstream model. Do not assume
the example API type applies to every model or provider.

## Optional rate limits, inference table, and pricing

`config.rate_limits` uses the same structure and enums as model-service rate
limits. Limits here govern requests sent directly to the provider service;
requests routed through a model service use the model service's limits.

`config.inference_table` contains `parent` and optional `table_name_prefix`.
It logs traffic sent directly to the provider service. Traffic routed through
a model service is logged by that model service instead. Treat payloads as
sensitive and establish retention and access before enabling logging.

`config.pricing` can adjust estimated external-model pricing. Do not add it
without explicit, reviewed commercial inputs.

## Grants and dependencies

Consumers receive `EXECUTE` on the provider service plus parent `USE CATALOG`
and `USE SCHEMA`; they do not need access to the stored provider credential.
The owner must retain access to the credential or secret. Keep provider account
creation, cloud permissions, and secret provisioning as explicit prerequisites
unless they are separately declared with supported DAB resources.
