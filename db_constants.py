"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.
"""

# Model size. Keep this at one stream for the Azure Snowflake functional
# verification, then scale deliberately through 10, 50, 100, 150, 200, and
# 250 streams.
NUM_TEAMS: int = 1
NUM_STORES_PER_TEAM: int = 10

# Azure resource values. Replace these literals with the actual provisioned
# Azure values before generating bootstrap artifacts.
AZURE_LOCATION_KEY: str = "Azure:USA/WestUS2"
AZURE_SOURCE_SQL_SERVER_HOST: str = "ds-azsf-source-06180941367a.database.windows.net"
AZURE_MERGE_SQL_SERVER_HOST: str = "merge-replace-me.database.windows.net"
AZURE_CQRS_SQL_SERVER_HOST: str = "cqrs-replace-me.database.windows.net"
AZURE_AIRFLOW_POSTGRES_HOST: str = "ds-azsf-airflow-06180941367a.postgres.database.azure.com"
AZURE_SQL_SERVER_PORT: int = 1433
AZURE_AIRFLOW_POSTGRES_PORT: int = 5432
AZURE_SOURCE_DBNAME: str = "customer_db"
AZURE_MERGE_DBNAME: str = "merge_db"
AZURE_CQRS_DBNAME: str = "cqrs_db"
AZURE_SQL_TRUST_SERVER_CERTIFICATE: bool = True

# Azure Blob bulk staging. AZURE_BULK_DATA_SOURCE_NAME must match the external
# data source name created in each Hyperscale database.
AZURE_BULK_STORAGE_ACCOUNT: str = "dsscalebulkstore"
AZURE_BULK_CONTAINER: str = "datasurface-bulk"
AZURE_BULK_PREFIX: str = "yellow/bulk-staging"
AZURE_BULK_DATA_SOURCE_NAME: str = "datasurface_bulk_ds"

# Azure-hosted Snowflake target for the azure_sf runtime.
AZURE_SF_RTE_NAME: str = "azure_sf"
AZURE_SF_PSP_NAME: str = "AzureSnowflake_PSP"
AZURE_SF_DATA_PLATFORM_NAME: str = "SCD2_AZURE_SF"
AZURE_SF_SNOWFLAKE_ACCOUNT: str = "HORSEQD-DATASURFACE_AZURE_SF"
AZURE_SF_SNOWFLAKE_HOST: str = "horseqd-datasurface_azure_sf.snowflakecomputing.com"
AZURE_SF_SNOWFLAKE_DATABASE: str = "DATASURFACE_SCALE"
AZURE_SF_SNOWFLAKE_MERGE_SCHEMA: str = "YELLOW_MERGE"
AZURE_SF_SNOWFLAKE_CQRS_SCHEMA: str = "YELLOW_CQRS"
AZURE_SF_SNOWFLAKE_WAREHOUSE: str = "DATASURFACE"
AZURE_SF_SNOWFLAKE_ROLE: str = "DATASURFACE_RUNTIME_ROLE"
AZURE_SF_BULK_STORAGE_ACCOUNT: str = "dsdollybulk05310343"
AZURE_SF_BULK_CONTAINER: str = "datasurface-bulk"
AZURE_SF_BULK_PREFIX: str = "yellow/azure-sf-scale/06180941367a"
AZURE_SF_BULK_STAGE_NAME: str = "datasurface_bulk_ds"

# Ingestion pod sizing for the Airflow/AKS concurrency test.
INGESTION_REQUEST_MEMORY: str = "512M"
INGESTION_LIMIT_MEMORY: str = "2G"
INGESTION_REQUEST_CPU: float = 0.25
INGESTION_LIMIT_CPU: float = 1.0

# Legacy local/AWS names retained for rte_demo.py/rte_aws.py.
MERGE_HOST: str = "postgres-co"
SQLSERVER_HOST_A: str = AZURE_SOURCE_SQL_SERVER_HOST
SQLSERVER_HOST_B: str = AZURE_CQRS_SQL_SERVER_HOST
