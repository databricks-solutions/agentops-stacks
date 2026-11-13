# Model services in DAB

Use this reference when adding a `model_services` resource. The primary schema
reference is the Databricks documentation for
[model services](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_services)
and
[model service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_service-config).
Confirm fields against the installed `databricks bundle schema` before editing.

## V1 contract

- Create one new top-level `model_services` entry.
- Use one primary destination.
- Use the same routing, limits, inference logging, and grants in every target.
- Do not add fallback routing or traffic splitting in v1.
- Do not adopt, replace, rename, or delete a service.

## Required resource fields

```yaml
resources:
  model_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${var.schema}
      model_service_id: <unqualified-service-id>
      config:
        routing:
          destinations:
            - name: primary
              destination_type: <destination-enum>
              <matching-config>: {}
```

`parent` and `model_service_id` are required. `comment`, `grants`, and
`lifecycle` are optional top-level fields. The configuration requires at least
one primary destination on creation.

Each destination requires `name`, `destination_type`, and exactly one matching
configuration:

| Destination | Enum | Matching configuration |
|---|---|---|
| Databricks pay-per-token foundation model | `DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL` | `pay_per_token_config.model: models/<catalog>.<schema>.<model>` |
| Provisioned-throughput foundation model | `DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL` | `provisioned_throughput_config.model_serving_endpoint: serving-endpoints/<endpoint>` |
| External model | `DESTINATION_TYPE_EXTERNAL_FOUNDATION_MODEL` | `external_model_config.model_provider_service` plus `external_model_config.target` |

For the v1 single destination, omit `traffic_percentage`. Do not put the
three-part model service name in the resource body; DAB derives it from
`parent` and `model_service_id`.

## Minimal pay-per-token service

```yaml
resources:
  model_services:
    assistant_model:
      parent: schemas/${var.catalog}.${var.schema}
      model_service_id: assistant-model
      comment: "Governed model service for ${bundle.name}"
      config:
        routing:
          destinations:
            - name: primary
              destination_type: DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL
              pay_per_token_config:
                model: models/system.ai.<exact-model-name>
      grants:
        - principal: <consumer-principal>
          privileges:
            - EXECUTE
```

Use the exact model resource name selected by the user. Do not normalize names
or substitute a similar model.

## Other destination shapes

Provisioned throughput:

```yaml
destination_type: DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL
provisioned_throughput_config:
  model_serving_endpoint: serving-endpoints/<exact-endpoint-name>
```

External provider:

```yaml
destination_type: DESTINATION_TYPE_EXTERNAL_FOUNDATION_MODEL
external_model_config:
  model_provider_service: model-provider-services/${var.catalog}.${var.schema}.<provider-service-id>
  target:
    model: <exact-provider-model>
    native_api_types:
      - <exact-native-api-type>
```

The referenced provider service must already exist or be declared in the same
bundle. Its target policy must permit the selected model and API type.

## Optional rate limits

`config.rate_limits` is a sequence. Each entry requires `key` and
`renewal_period`:

```yaml
rate_limits:
  - key: RATE_LIMIT_KEY_USER_GROUP
    principal: <account-group>
    renewal_period: RATE_LIMIT_RENEWAL_PERIOD_MINUTE
    requests: 60
    tokens: 100000
```

Supported keys:

- `RATE_LIMIT_KEY_USER`
- `RATE_LIMIT_KEY_USER_GROUP`
- `RATE_LIMIT_KEY_SERVICE_PRINCIPAL`
- `RATE_LIMIT_KEY_SERVICE`
- `RATE_LIMIT_KEY_USER_DEFAULT`

Supported periods are `RATE_LIMIT_RENEWAL_PERIOD_MINUTE` and
`RATE_LIMIT_RENEWAL_PERIOD_HOUR`. Set `principal` only for a specific user,
group, or service principal. `requests` and `tokens` are independent optional
limits. A value of `0` denies requests; omission means no limit for that
dimension.

Under the v1 invariant, either omit rate limits everywhere or apply this same
list in every target.

## Optional inference table

```yaml
inference_table:
  parent: schemas/${var.catalog}.${var.schema}
  table_name_prefix: <prefix>
```

`parent` is required when inference logging is enabled. The service appends
`_payload` to the prefix. The parent and prefix cannot be changed after the
table is created. Payloads can contain prompts, responses, identities, and
sensitive data: establish access and retention before enabling this in any
target.

## Grants and dependencies

The service resource accepts `grants` entries with a `principal` and
`privileges: [EXECUTE]`. A caller also needs `USE CATALOG` and `USE SCHEMA` on
the parents. Grant `MANAGE` only to administrators outside this consumer grant
pattern.

The deployer needs the parent privileges required to create a service and must
be able to use the exact destination. Provisioned throughput also has separate
Model Serving permissions. Model services use the owner's access to their
destinations; callers should not receive destination credentials.
