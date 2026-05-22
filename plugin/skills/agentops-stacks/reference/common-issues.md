# Common Issues

| Issue | Solution |
|---|---|
| `databricks: command not found` | Databricks CLI not installed. See [docs.databricks.com](https://docs.databricks.com/dev-tools/cli/install.html). |
| `Error: A new access token could not be retrieved...` | The CLI eagerly refreshes the default profile's token. Run `databricks auth login` to fix, or set `DATABRICKS_CONFIG_FILE` to an empty file for the scaffold call (auth is required for the next step anyway). |
| `Invalid project_name`: must match the pattern | Pattern is `^[a-z][a-z0-9_]{2,}$`: starts with a lowercase letter, then lowercase letters/digits/underscores, min 3 chars. Reject `My-Project`, `1foo`, `ab`. |
| Output directory not empty | `bundle init` refuses to overwrite. Pick an empty path or have the user move/remove existing files. |
| `Error: template path does not contain databricks_template_schema.json` | Wrong source path. The schema must be at the root of the template repo. Use the git URL form if the local-path resolution is uncertain. |
| Genie Code: `databricks --version` returns nothing | Expected — the Genie Code CLI wrapper doesn't expose `--version`. Skip the version check and proceed; surface `bundle init` errors if anything is wrong. |
| Workspace UI Deployments panel doesn't appear on the bundle | Bundle wasn't created inside a Git folder. The workspace UI only surfaces the Deployments panel for bundles under Git folders. Move the scaffold into a Git folder, or use the CLI to deploy (`databricks bundle deploy -t dev`). |
