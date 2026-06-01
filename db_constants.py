"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.
"""

# Model size. NUM_TEAMS=1 and NUM_STORES_PER_TEAM=50 creates 50 independent
# CDC ingestion streams over the same source tables.
NUM_TEAMS: int = 1
NUM_STORES_PER_TEAM: int = 50

# Azure resource values. Replace these literals with the actual provisioned
# Azure values before generating bootstrap artifacts.
AZURE_LOCATION_KEY: str = "Azure:USA/EastUS"
AZURE_SOURCE_SQL_SERVER_HOST: str = "source-replace-me.database.windows.net"
AZURE_MERGE_SQL_SERVER_HOST: str = "merge-replace-me.database.windows.net"
AZURE_CQRS_SQL_SERVER_HOST: str = "cqrs-replace-me.database.windows.net"
AZURE_AIRFLOW_POSTGRES_HOST: str = "airflow-replace-me.postgres.database.azure.com"
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

# Ingestion pod sizing for the Airflow/AKS concurrency test.
INGESTION_REQUEST_MEMORY: str = "512M"
INGESTION_LIMIT_MEMORY: str = "2G"
INGESTION_REQUEST_CPU: float = 0.25
INGESTION_LIMIT_CPU: float = 1.0

# Legacy local/AWS names retained for rte_demo.py/rte_aws.py.
MERGE_HOST: str = "postgres-co"
SQLSERVER_HOST_A: str = AZURE_SOURCE_SQL_SERVER_HOST
SQLSERVER_HOST_B: str = AZURE_CQRS_SQL_SERVER_HOST
