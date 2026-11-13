---
name: unity-gateway-ops
description: >-
  Add a new model service, model provider service, MCP service, or user-described
  Unity Gateway element to an existing AgentOps Stacks Declarative Automation
  Bundle. Use even when the user names one of those resources without saying
  "Unity Gateway." Authors DAB resource YAML only. Do not use for querying
  existing services, imperative Unity Gateway administration, legacy AI Gateway
  configuration, or migration.
compatibility: Requires Databricks CLI >= 1.17.0 and the DAB direct deployment engine
---

# Unity Gateway operations for AgentOps Stacks

Define new Unity Gateway resources as bundle-owned desired state. The resource
configuration moves through development, validation, and production targets with
the rest of the project.

"Unity Gateway" is the product grouping, not a DAB resource type. A bundle
defines one or more independent `model_services`, `model_provider_services`, or
`mcp_services` resources. Do not invent a `unity_gateway` resource mapping.

The first version uses one configuration in every target. Define the service at
the top-level `resources` mapping and do not add target-level resource
overrides. The target catalog, schema, workspace, and environment-local objects
such as secrets or connections can resolve differently, but service behavior
must remain the same: destination, provider settings, model parameters, rate
limits, inference logging, MCP selectors, and grants.

This skill is the AgentOps Stacks DAB authoring surface for Unity Gateway. It
shares the service definitions, naming rules, and security gates of the
`databricks-unity-gateway` product skill, but not its imperative CLI workflow.

## Selection boundary

Use this skill only when all of the following are true:

- the working directory is an existing AgentOps Stacks project;
- the user wants to define a new Unity Gateway resource;
- that resource will be owned and promoted by the project's DAB.

Recognize requests to add or create any of these, even when the user does not
mention Unity Gateway:

- a model service;
- a model provider service or external model provider service;
- an MCP service;
- a Unity Gateway service, resource, or element.

When the user asks generically for a Unity Gateway element, ask them to select
model service, model provider service, or MCP service. When "model service" is
ambiguous, ask whether they mean a three-part Unity Catalog model service
(`model_services`) or a workspace Model Serving endpoint
(`model_serving_endpoints`). This clarification is resource-type selection, not
legacy gateway detection or migration.

Use the general `databricks-unity-gateway` product skill instead when the user
wants to query or administer an existing service outside an AgentOps Stacks
bundle. Do not load both skills to perform the same resource lifecycle change.

## Authoring workflow

Follow this sequence for every request:

1. Run the preflight checks below. Stop if this is not an AgentOps Stacks DAB,
   the direct engine is absent, or the installed bundle schema lacks the
   requested resource type.
2. Inspect `databricks.yml`, its included resource files, and all target
   variable overrides before proposing a change.
3. Select exactly one supported resource type from the user's intent.
4. Collect its complete required-input set in one prompt. Do not invent or
   discover unspecified resources by broadly listing a workspace.
5. Search the bundle for both the proposed resource key and three-part service
   name. Stop if either is already declared; this version does not update or
   replace it.
6. Confirm the same behavioral configuration will apply in every target. Stop
   if the request requires target-level resource overrides.
7. Add the new definition to the top-level `resources` mapping in
   `resources/unity_gateway.yml`, creating that file only when needed.
8. Add `./resources/unity_gateway.yml` to the existing `include` sequence only
   when it is not already included.
9. Review the diff for a single additive resource, least-privilege grants,
   exact names, and absence of plaintext credentials.
10. With a profile explicitly selected by the user, run strict validation and
    planning for the first target. Fix all errors and inspect the plan before
    offering deployment.
11. Deploy only after a separate, explicit request. Repeat validation and
    planning as the unchanged resource configuration is promoted to each later
    target.

Never combine authoring and deployment into an auto-approved operation.

## Operating boundary

Supported DAB resource types:

- `model_services`
- `model_provider_services`
- `mcp_services`

Primary DAB authoring references:

- [model service](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_services)
  and [model service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_service-config)
- [model provider service](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_provider_service)
  and [model provider service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#model_provider_service-config)
- [MCP service](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#mcp_service)
  and [MCP service config](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources#mcp_service-config)

Use these resource-specific DAB sections for supported keys, types, constraints,
and examples. Use `databricks bundle schema` to confirm what the installed CLI
accepts. Consult the REST API documentation only for runtime semantics that are
not described by the DAB reference; do not translate REST request payloads into
an assumed aggregate resource.

Use only these bundle commands for resource lifecycle:

```bash
databricks bundle schema
databricks bundle validate --strict -t <target> --profile <PROFILE>
databricks bundle plan -t <target> --profile <PROFILE>
databricks bundle deploy -t <target> --profile <PROFILE>
databricks bundle summary -t <target> --profile <PROFILE>
```

Do not create, update, or delete Unity Gateway resources with product-specific
CLI commands, REST calls, or SDK methods. DAB configuration is the source of
truth.

This first version creates new resources. It does not:

- detect or migrate legacy Model Serving AI Gateway configuration;
- import or adopt existing Unity Gateway resources;
- replace, delete, or rename resources;
- create target-specific variants or overrides of a service;
- manage Unity Gateway Skills, Agent Services, service policies, budgets,
  unified trace tables, or MCP user-mapped credentials.

If the requested bundle resource key already exists, stop and show the existing
definition. Do not overwrite it. If deployment reports that the three-part
service name already exists outside the bundle, stop and report that adoption is
not supported.

## Preflight

Before editing files:

1. Confirm `.agentops-stacks/manifest.yml` and `databricks.yml` exist.
2. Confirm `databricks.yml` contains:

   ```yaml
   bundle:
     engine: direct
   ```

3. Run `databricks --version`. DAB support for these resources requires CLI
   1.17.0 or later.
4. Run `databricks bundle schema` locally and verify that its resource map
   contains the requested resource type. Treat this installed schema as
   authoritative for supported fields. Missing sibling resource types do not
   block authoring the requested supported type.
5. Inspect the bundle's existing targets, `catalog` and `schema` variables, and
   resource includes. Do not assume the project has a target named `qa`. Confirm
   that the same service configuration is acceptable in every target.
6. If workspace validation or deployment is requested, list every configured
   Databricks profile and workspace URL and ask the user to select one. Never
   select a profile automatically. Verify the selected profile points to the
   workspace the user named before continuing.

## Select the resource type

| User intent | DAB resource |
|---|---|
| Governed endpoint that routes inference to one model | `model_services`; read [Model services](references/model-services.md) |
| Governed authentication and request configuration for an external model provider | `model_provider_services`; read [Model provider services](references/model-provider-services.md) |
| Governed access to an external MCP server through a UC HTTP connection | `mcp_services`; read [MCP services](references/mcp-services.md) |

This skill does not configure legacy per-endpoint AI Gateway settings.

Read the complete reference for the selected type before collecting inputs or
editing YAML. Those references are the v1 resource contracts; do not combine
fields from different service types.

## Resolve required inputs

Ask for all missing required inputs together. Do not infer a catalog, schema,
service ID, destination, connection, credential, or principal by listing
unrelated workspace resources.

All service types require:

- bundle resource key;
- unqualified service ID;
- confirmation that one service configuration applies throughout the bundle
  lifecycle;
- intended callers and their least-privilege grants;
- data classification and whether requests or responses may contain sensitive
  data.

Use `schemas/${var.catalog}.${var.schema}` as the parent unless the project has
an established, target-aware alternative.

Users, service principals, catalogs, and schemas are environment prerequisites;
this skill does not create them. Confirm that each target catalog and schema
exists or is declared in the same bundle. Confirm that the deploying user in
development or pipeline service principal in later environments exists in the
target workspace and has the parent privileges required to create the service.
Runtime callers must exist and have `USE CATALOG`, `USE SCHEMA`, and `EXECUTE`
on the service. Document missing identity or parent grants as blocking
prerequisites rather than assuming deployment or invocation access.

### Model service

Also require:

- exact destination type;
- exact backing model, model provider service, or Model Serving endpoint;
- whether rate limits are required;
- whether inference-table payload logging is required and, if so, its target
  schema and table prefix.

For the initial implementation, define exactly one primary destination. Do not
add traffic splitting or fallbacks unless this skill is extended and tested for
them.

### Model provider service

Also require:

- provider type and provider-specific endpoint, region, project, or
  organization values;
- authentication mode and the exact existing UC secret or supported service
  credential reference;
- explicit upstream model targets and native API types;
- an explicit decision for each forwarding setting.

Default `forward_headers`, `forward_query_parameters`, and
`forward_unmanaged_paths` to `false`. Default `allow_all_targets` to `false`.
Never request a secret value in conversation, place plaintext credentials in
bundle files, or pass secrets on a command line.

### MCP service

Also require:

- exact existing UC HTTP connection in
  `connections/<catalog>.<schema>.<connection>` form;
- exact tool names or prefix selectors to expose;
- whether rate limits are required.

An omitted or empty `include_tool_selectors` list exposes every tool. Require
explicit confirmation before doing that; otherwise use the narrowest selectors
that satisfy the request. Consumers normally receive `EXECUTE` on the MCP
service, not `USE CONNECTION` on its source connection.

## Author the bundle change

Prefer one project-level file, `resources/unity_gateway.yml`. Preserve existing
comments and resource definitions if the file already exists. Add this include
to `databricks.yml` once:

```yaml
include:
  - ./resources/unity_gateway.yml
```

Do not add a second top-level `include` or `resources` mapping. Follow the
project's existing ordering and formatting. Keep each service resource in the
top-level resource file; do not copy or patch it under individual targets.

The filename groups related resources for project organization only. Its YAML
must still contain the distinct supported mappings (`model_services`,
`model_provider_services`, or `mcp_services`) under `resources`; it must never
contain a `unity_gateway` mapping.

Use existing target variables for environment resolution. For example,
`schemas/${var.catalog}.${var.schema}` creates the same logical service in each
target's schema. When a provider secret or MCP connection is environment-local,
use a stable target-aware name or variable that resolves to a corresponding
object in each workspace. This does not authorize sharing secret values or data
between environments.

### Minimal model service pattern

Use the installed bundle schema to confirm every field before writing it:

```yaml
resources:
  model_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${var.schema}
      model_service_id: <service_id>
      comment: "Governed model service for ${bundle.name}"
      config:
        routing:
          destinations:
            - name: primary
              destination_type: DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL
              pay_per_token_config:
                model: models/system.ai.<exact_model_name>
      grants:
        - principal: <consumer-principal>
          privileges:
            - EXECUTE
```

This is the simplest sandbox validation path when the user selects an exact
`system.ai` model available in that workspace. Do not substitute a similarly
named model.

### Minimal MCP service pattern

```yaml
resources:
  mcp_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${var.schema}
      mcp_service_id: <service_id>
      comment: "Governed MCP service for ${bundle.name}"
      config:
        source_connection:
          name: connections/<catalog>.<schema>.<connection>
        include_tool_selectors:
          - <tool-or-prefix-selector>
      grants:
        - principal: <consumer-principal>
          privileges:
            - EXECUTE
```

Keep the connection name exact. Do not replace hyphens or otherwise normalize
any catalog, schema, connection, model, or service name.

### Model provider service pattern

Provider fields differ by provider. Read the installed DAB schema for
`model_provider_services` and write only the selected provider's matching
configuration. The common shape is:

```yaml
resources:
  model_provider_services:
    <resource_key>:
      parent: schemas/${var.catalog}.${var.schema}
      model_provider_service_id: <service_id>
      comment: "Governed external model provider for ${bundle.name}"
      config:
        provider_type: <exact-provider-enum>
        allow_all_targets: false
        forward_headers: false
        forward_query_parameters: false
        forward_unmanaged_paths: false
        targets:
          - model: <exact-provider-model>
            native_api_types:
              - <exact-native-api-type>
        <provider_field>:
          <authentication_mode>:
            # Use the provider-specific UC secret or service credential
            # reference shape from the installed bundle schema.
```

Do not leave a credential placeholder that could be mistaken for a deployable
value. Stop until the exact non-plaintext reference is known.

## Validate and plan

After editing, validate every affected target. Validation and planning contact a
workspace, so use only the profile the user selected:

```bash
databricks bundle validate --strict -t <target> --profile <PROFILE>
databricks bundle plan -t <target> --profile <PROFILE>
```

Resolve every validation error and warning. Review the plan for:

- exactly one new intended Unity Gateway resource;
- the expected target catalog and schema;
- no replacement or deletion;
- the intended grants only;
- no plaintext secrets.

Before promotion, compare the resolved plans and confirm that differences are
limited to target identity and environment-local references. If the user asks
for different destinations, rate limits, selectors, provider settings, or other
service behavior by target, stop and explain that granular target configuration
is deferred from this version.

Do not deploy merely because validation passes. Show the plan summary and wait
for an explicit deployment request.

## Deploy and verify

When explicitly requested:

```bash
databricks bundle deploy -t <target> --profile <PROFILE>
databricks bundle summary -t <target> --profile <PROFILE>
```

Use a minimal invocation test appropriate to the service type. Invocation is a
runtime verification, not a second resource-management path:

- model service: send one non-sensitive request and verify a successful
  response;
- model provider service: call one explicitly allowed target with a
  non-sensitive request;
- MCP service: list tools, confirm only the intended selectors are visible,
  and call a read-only tool when one is available.

Do not test a side-effecting MCP tool without separate user approval.

## Security and operational record

Before declaring the change complete, report and document:

- **Data flow:** caller, Unity Gateway service, destination, and any external
  processor.
- **Storage and logging:** inference table or other payload logging, unified
  tracing if separately enabled, audit records, and retention ownership.
- **Credentials:** where credentials live, who can access them, and who owns
  rotation.
- **Permissions:** deployer privileges, owner, consumer grants, and parent
  `USE CATALOG` / `USE SCHEMA` requirements.
- **Compliance:** data classification, provider-region implications, and any
  preview features involved. Do not infer compliance eligibility.
- **DASF posture:** UC governance and least privilege supplied by the pattern;
  customer-configured retention, identity propagation, network controls,
  service policies, and budgets; unsupported controls that remain out of
  scope.
- **Closed loop:** which validation, evaluation, monitoring alert, or runbook
  will turn a production failure into a development change.

Persist this record in the project's governance artifacts when they exist:
update `governance/data_flows.md` for data movement and storage, and
`governance/posture.md` for permissions, compliance, DASF posture, and the
closed loop. If those files do not exist, include the complete record in the
review and identify application of the governance posture pattern as a
prerequisite before production promotion. Do not create or mark that production
pattern as applied without the user's approval.

End every review with: **What are we missing?**

## Done when

- the new resource is declared in `resources/unity_gateway.yml`;
- the include exists exactly once;
- no target-level Unity Gateway resource override exists;
- strict validation passes for every affected target;
- the plan contains no unexpected replacement or deletion;
- no plaintext secret is present;
- deployment occurred only if the user requested it;
- the security and operational record is complete and either persisted in
  existing governance artifacts or recorded as a prerequisite before production.
