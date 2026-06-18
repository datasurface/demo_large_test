---
name: setup-walkthrough-azure-snowflake
description: Deploy and validate a DataSurface Yellow environment on Azure AKS with an Azure SQL CDC source, Azure Blob bulk staging, and an Azure-hosted Snowflake merge/CQRS target. Use when building the azure_sf runtime, adapting the Azure setup walkthrough for Snowflake, provisioning only the functional-test Azure resources, generating bootstrap artifacts, creating secrets, or running the 1-stream then 10/50/100/200-stream Azure Snowflake scale test.
---

# DataSurface Azure Snowflake Setup Walkthrough

Use this skill for the `azure_sf` runtime: Azure hosts AKS, Airflow metadata
PostgreSQL, the Azure SQL CDC source, and Azure Blob bulk staging; Snowflake
hosts both the Yellow merge store and CQRS replica. Start with one stream and
do not scale until functional verification is clean.

For generic AKS, Helm Airflow, Workload Identity, Key Vault, Azure Files NFS,
and DAG deployment mechanics, reuse `.claude/skills/setup-walkthrough-azure/SKILL.md`.
Apply the deltas below instead of the Azure SQL merge/CQRS steps in that skill.

## Current Defaults

- DataSurface image: `registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.4.65`
- Airflow image: `registry.gitlab.com/datasurface-inc/datasurface/airflow:3.2.2-azure-sf`
- Azure region: `westus2`
- Snowflake account: `HORSEQD-DATASURFACE_AZURE_SF`
- Snowflake database/schema: `DATASURFACE_SCALE.YELLOW`
- Snowflake warehouse: `DATASURFACE`
- Snowflake runtime user/role: `DATASURFACE_RUNTIME` / `DATASURFACE_RUNTIME_ROLE`
- Snowflake stage handle: `"datasurface_bulk_ds"`
- Azure Blob staging: `dsdollybulk05310343/datasurface-bulk`
- Recommended test prefix: `yellow/azure-sf-scale`

## Resource Shape

For the 1-stream functional test, provision only:

- AKS with a small fixed node pool.
- PostgreSQL Flexible Server for Airflow metadata.
- One Azure SQL source server/database with CDC enabled.
- Azure Blob staging container, reusing `dsdollybulk05310343/datasurface-bulk` when available.
- Key Vault or Kubernetes secrets, matching the deployment mode.

Do not provision Azure SQL Hyperscale merge or CQRS databases for `azure_sf`.
The captured full scale baseline in `docs/azure-scaletest-current.bicep`
contains those resources; remove or disable `mergeSqlServer`, `mergeDb`,
`cqrsSqlServer`, `cqrsDb`, and their firewall outputs when deriving the lean
functional Bicep. Keep source SQL, AKS, Airflow Postgres, storage, and outputs.

The source database must support Azure SQL CDC. If optimizing cost, downshift
only after proving CDC works; if unsure, mirror the previous source shape first
and reduce later.

## Model Changes

1. Set `NUM_TEAMS = 1` and `NUM_STORES_PER_TEAM = 1` for the functional pass.
2. Add `rte_azure_sf.py` based on `rte_azure.py`.
3. In `rte_azure_sf.py`, replace Azure SQL merge/CQRS containers with
   `SnowFlakeDatabase` containers:

```python
SnowFlakeDatabase(
    "AzureSnowflakeMergeDB",
    locations={_location()},
    databaseName="DATASURFACE_SCALE",
    account="HORSEQD-DATASURFACE_AZURE_SF",
    warehouse="DATASURFACE",
    schema="YELLOW",
    role="DATASURFACE_RUNTIME_ROLE",
    productionStatus=ProductionStatus.NOT_PRODUCTION,
)
```

Use a distinct CQRS container name, for example `AzureSnowflake_CQRS_DB`, with
the same Snowflake account/database/schema/warehouse/role.

4. Use `Credential("snowflake-runtime", CredentialType.PRIVATE_KEY_AUTH)` for
   the merge credential and `Credential("snowflake-cqrs",
   CredentialType.PRIVATE_KEY_AUTH)` for the Snowflake CRG credential.
5. Keep `BulkObjectStorageBinding(AzureObjectContainer(...))` and ensure
   `objectStore.name == "datasurface_bulk_ds"`. DataSurface references that
   name as the Snowflake external stage handle.
6. Set the Blob prefix to `yellow/azure-sf-scale` for clean test separation.
7. Prefer SCD4 when reproducing the documented columnar scale baseline. If the
   current model remains SCD2, call out that it is not the same test as the
   SCD4 baseline.
8. Add a `RuntimeDeclaration("azure_sf", ...)`, call `createAzureSfRTE(ecosys)`,
   and map each source `EnvironmentMap` for both `demo` and `azure_sf`.

## Snowflake Preflight

Before deploying AKS jobs, verify Snowflake from the workstation:

```bash
python - <<'PY'
import snowflake.connector
conn = snowflake.connector.connect(
    account="HORSEQD-DATASURFACE_AZURE_SF",
    user="DATASURFACE_RUNTIME",
    authenticator="SNOWFLAKE_JWT",
    private_key_file="/Users/billy/.snowflake/rsa_key.p8",
    warehouse="DATASURFACE",
    database="DATASURFACE_SCALE",
    schema="YELLOW",
    role="DATASURFACE_RUNTIME_ROLE",
)
cur = conn.cursor()
cur.execute('LIST @"datasurface_bulk_ds"')
print("stage rows:", len(cur.fetchall()))
conn.close()
PY
```

This must succeed before attempting DataSurface bulk ingestion. If it fails
with Azure authorization errors, re-check the Snowflake storage integration,
Azure enterprise application consent, and `Storage Blob Data Reader` role on
the staging container.

## Secrets

Create the usual registry, Git, Airflow, source SQL, and Azure bulk-writer
secrets from the Azure walkthrough. For Snowflake key-pair auth, create
Kubernetes secrets with these keys. The model uses different credential names
so platform ACLs can separate merge RW from CQRS access:

```bash
kubectl create secret generic snowflake-runtime \
  --from-literal=USER=DATASURFACE_RUNTIME \
  --from-file=PRIVATE_KEY=/Users/billy/.snowflake/rsa_key.p8 \
  --from-literal=PASSPHRASE="" \
  -n "$NAMESPACE"

kubectl create secret generic snowflake-cqrs \
  --from-literal=USER=DATASURFACE_RUNTIME \
  --from-file=PRIVATE_KEY=/Users/billy/.snowflake/rsa_key.p8 \
  --from-literal=PASSPHRASE="" \
  -n "$NAMESPACE"
```

If using Key Vault-backed secret resolution, store the same JSON fields under
the DataSurface credential naming conventions for `snowflake-runtime` and
`snowflake-cqrs`.

## Bootstrap And Deploy

Use `DATASURFACE_VERSION=1.4.65` everywhere:

```bash
docker pull registry.gitlab.com/datasurface-inc/datasurface/datasurface:v${DATASURFACE_VERSION}
docker run --rm \
  -v "$(pwd)":/workspace/model \
  -w /workspace/model \
  registry.gitlab.com/datasurface-inc/datasurface/datasurface:v${DATASURFACE_VERSION} \
  python -m datasurface.cmd.platform generatePlatformBootstrap \
  --ringLevel 0 \
  --model /workspace/model \
  --output /workspace/model/generated_output \
  --psp AzureSnowflake_PSP \
  --rte-name azure_sf
```

Deploy the generated bootstrap, ring1-init, and model-merge jobs sequentially,
following the existing Azure walkthrough. Do not run model-merge before
ring1-init completes.

## Functional Gate

The 1-stream run is complete only when all checks pass:

- Exactly one generated ingestion DAG for the Azure SQL CDC source.
- Source tables `customers` and `addresses` have CDC enabled and seed rows.
- Initial seed succeeds into Snowflake merge tables.
- At least one insert/update/delete CDC delta succeeds after seed.
- CQRS sync succeeds into the Snowflake CQRS container.
- Snowflake `QUERY_HISTORY` shows `COPY INTO` for the load path.
- Azure Blob contains Parquet parts under `yellow/azure-sf-scale`.
- Snowflake row counts reconcile across source intent, merge, history/current, and CQRS views.
- Airflow, KPO pods, and Snowflake queries show no retry storms, OOMs, queueing, or auth errors.

## Scaling Gate

Scale only after the 1-stream gate is clean. Use this ladder:

```text
1 -> 10 -> 50 -> 100 -> 200 streams
```

At each step, hold for multiple schedule intervals and record:

- DAG count, active runs, failed/retried tasks, and scheduler lag.
- AKS pending pods, image pulls, OOMs, CPU/memory pressure, and KPO launch latency.
- Blob upload latency, throttling, and staged file cleanup behavior.
- Snowflake warehouse queueing, `COPY INTO` duration, merge duration, and credit burn.
- Source Azure SQL CDC latency and cleanup-window health.
- End-to-end row-count reconciliation after seed and delta windows.

Increase AKS node count/size and Airflow Postgres size before high-concurrency
runs if scheduler or pod placement pressure appears. Do not add Azure SQL
merge/CQRS Hyperscale resources to `azure_sf`; tune Snowflake warehouse size
instead.
