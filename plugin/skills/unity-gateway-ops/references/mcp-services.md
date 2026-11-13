# MCP services in DAB

Use this reference when adding an `mcp_services` resource. The primary schema
reference is the Databricks documentation for
[MCP services](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#mcp_service)
and
[MCP service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#mcp_service-config).
Confirm fields against the installed `databricks bundle schema` before editing.

## V1 contract

- Create one new top-level `mcp_services` entry.
- Reference an exact existing UC HTTP connection.
- Expose explicit tools or prefixes. Exposing every tool requires explicit
  confirmation.
- Use the same connection naming convention, selectors, limits, and grants in
  every target. Each target can resolve to its own environment-local connection.
- Do not manage user-mapped credentials, service policies, adoption,
  replacement, rename, or deletion.

## Required resource fields

```yaml
resources:
  mcp_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${resources.schemas.project_schema.name}
      mcp_service_id: <unqualified-service-id>
      config:
        source_connection:
          name: connections/<catalog>.<schema>.<connection>
```

`parent`, `mcp_service_id`, `config`, and
`config.source_connection.name` are required on creation. `comment`, `grants`,
and `lifecycle` are optional top-level fields. Do not include output-only
connection options.

## Tool selectors

`config.include_tool_selectors` accepts exact tool names and prefix patterns
such as `read_*`. It does not support exclusion patterns. An omitted or empty
list exposes every tool.

Use no more than 1,024 selectors; each selector can contain at most 256
characters. Prefer the narrowest set that satisfies the use case. Require the
user to explicitly approve exposing every tool.

## Minimal MCP service

```yaml
resources:
  mcp_services:
    support_tools:
      parent: schemas/${var.catalog}.${resources.schemas.project_schema.name}
      mcp_service_id: support-tools
      comment: "Governed MCP service for ${bundle.name}"
      config:
        source_connection:
          name: connections/${var.catalog}.${var.schema}.support-mcp
        include_tool_selectors:
          - read_*
      grants:
        - principal: <consumer-principal>
          privileges:
            - EXECUTE
```

Keep every catalog, schema, connection, service, and tool name exact. Do not
normalize hyphens or other characters.

## Optional rate limits

```yaml
rate_limits:
  - key: RATE_LIMIT_KEY_USER_GROUP
    principal: <account-group>
    renewal_period: RATE_LIMIT_RENEWAL_PERIOD_MINUTE
    requests: 60
```

Each entry requires `key` and `renewal_period`. Supported keys are:

- `RATE_LIMIT_KEY_USER`
- `RATE_LIMIT_KEY_USER_GROUP`
- `RATE_LIMIT_KEY_SERVICE_PRINCIPAL`
- `RATE_LIMIT_KEY_SERVICE`
- `RATE_LIMIT_KEY_USER_DEFAULT`

Supported periods are `RATE_LIMIT_RENEWAL_PERIOD_MINUTE` and
`RATE_LIMIT_RENEWAL_PERIOD_HOUR`. `requests` and `tokens` are independent
optional limits. A value of `0` denies requests. Under the v1 invariant, either
omit limits everywhere or apply the same list in every target.

## Grants and connection boundary

Consumers receive `EXECUTE` on the MCP service plus parent `USE CATALOG` and
`USE SCHEMA`. They normally do not receive `USE CONNECTION` on the backing
connection, because direct connection access can bypass the service's tool
selection and governance boundary.

The deployer needs permission to create the service in the parent schema and
`USE CONNECTION` on the source connection. The source connection owns the
external server URL and authentication configuration. Document where tool
arguments and results flow, what the external server stores, and whether user
identity is propagated.

After deployment, list tools and confirm the selectors. Invoke only a read-only
tool during the initial smoke test; side-effecting tools require separate user
approval.
