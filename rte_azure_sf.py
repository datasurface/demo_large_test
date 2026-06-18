"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.

Azure AKS runtime environment configuration using Azure Blob bulk staging and
an Azure-hosted Snowflake account for the Yellow merge and CQRS databases.
"""

from datasurface.containers import AzureObjectContainer, HostPortPair, SnowFlakeDatabase
from datasurface.documentation import PlainTextDocumentation
from datasurface.dsl import (
    ConsumerReplicaGroup,
    DataMilestoningStrategy,
    Ecosystem,
    PSPDeclaration,
    ProductionStatus,
    RuntimeEnvironment,
    StorageRequirement,
)
from datasurface.keys import LocationKey
from datasurface.repos import GitHubRepository, ReleaseType, VersionPatternReleaseSelector, VersionPatterns
from datasurface.security import Credential, CredentialType
from datasurface.triggers import CronTrigger
from datasurface.yellow import (
    BulkObjectStorageBinding,
    GitCacheConfig,
    K8sIngestionHint,
    K8sResourceLimits,
    YellowAzureExternalAirflow3AndMergeDatabase,
    YellowDataPlatform,
    YellowPlatformServiceProvider,
)

from db_constants import (
    AZURE_AIRFLOW_POSTGRES_HOST,
    AZURE_AIRFLOW_POSTGRES_PORT,
    AZURE_LOCATION_KEY,
    AZURE_SF_BULK_CONTAINER,
    AZURE_SF_BULK_PREFIX,
    AZURE_SF_BULK_STAGE_NAME,
    AZURE_SF_BULK_STORAGE_ACCOUNT,
    AZURE_SF_DATA_PLATFORM_NAME,
    AZURE_SF_PSP_NAME,
    AZURE_SF_RTE_NAME,
    AZURE_SF_SNOWFLAKE_ACCOUNT,
    AZURE_SF_SNOWFLAKE_DATABASE,
    AZURE_SF_SNOWFLAKE_HOST,
    AZURE_SF_SNOWFLAKE_ROLE,
    AZURE_SF_SNOWFLAKE_SCHEMA,
    AZURE_SF_SNOWFLAKE_WAREHOUSE,
    INGESTION_LIMIT_CPU,
    INGESTION_LIMIT_MEMORY,
    INGESTION_REQUEST_CPU,
    INGESTION_REQUEST_MEMORY,
    NUM_STORES_PER_TEAM,
    NUM_TEAMS,
)


KUB_NAME_SPACE: str = "ds-scale-azure-sf"
AIRFLOW_HOST: str = AZURE_AIRFLOW_POSTGRES_HOST
AIRFLOW_PORT: int = AZURE_AIRFLOW_POSTGRES_PORT
AIRFLOW_SERVICE_ACCOUNT: str = "airflow-worker"
DATASURFACE_VERSION: str = "1.4.65"
RTE_NAME: str = AZURE_SF_RTE_NAME
PSP_NAME: str = AZURE_SF_PSP_NAME
DATA_PLATFORM_NAME: str = AZURE_SF_DATA_PLATFORM_NAME
CRG_NAME: str = "AzureSnowflakeCQRS"
MERGE_CONTAINER_NAME: str = "AzureSnowflakeMergeDB"
CQRS_CONTAINER_NAME: str = "AzureSnowflake_CQRS_DB"
SNOWFLAKE_HOST_NAME: str = AZURE_SF_SNOWFLAKE_HOST


def _location() -> LocationKey:
    return LocationKey(AZURE_LOCATION_KEY)


def _azure_sf_bulk_binding() -> BulkObjectStorageBinding:
    return BulkObjectStorageBinding(
        AzureObjectContainer(
            AZURE_SF_BULK_STAGE_NAME,
            {_location()},
            storageAccountName=AZURE_SF_BULK_STORAGE_ACCOUNT,
            containerName=AZURE_SF_BULK_CONTAINER,
            prefix=AZURE_SF_BULK_PREFIX,
        ),
        writerCredential=Credential("azure-bulk-writer", CredentialType.USER_PASSWORD),
    )


def _snowflake_container(name: str) -> SnowFlakeDatabase:
    return SnowFlakeDatabase(
        name,
        locations={_location()},
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=AZURE_SF_SNOWFLAKE_DATABASE,
        account=AZURE_SF_SNOWFLAKE_ACCOUNT,
        warehouse=AZURE_SF_SNOWFLAKE_WAREHOUSE,
        schema=AZURE_SF_SNOWFLAKE_SCHEMA,
        role=AZURE_SF_SNOWFLAKE_ROLE,
    )


def _ingestion_hints() -> list[K8sIngestionHint]:
    hints: list[K8sIngestionHint] = []
    resources = K8sResourceLimits(
        StorageRequirement(INGESTION_REQUEST_MEMORY),
        StorageRequirement(INGESTION_LIMIT_MEMORY),
        INGESTION_REQUEST_CPU,
        INGESTION_LIMIT_CPU,
    )
    for team_idx in range(1, NUM_TEAMS + 1):
        for store_idx in range(1, NUM_STORES_PER_TEAM + 1):
            hints.append(
                K8sIngestionHint(
                    f"CustomerDB_AzureSQL_T{team_idx}_{store_idx}",
                    resources,
                    kv={
                        "bulkStagingMode": "force",
                        "bulkStagingRowsPerPart": 50000,
                        "bulkStagingMinRows": 1,
                        "bulkUploadMaxSinglePutMiB": 4,
                        "bulkUploadChunkMiB": 4,
                        "bulkUploadMaxConcurrency": 4,
                    },
                )
            )
    return hints


def createAzureSfPSP() -> YellowPlatformServiceProvider:
    merge_datacontainer = _snowflake_container(MERGE_CONTAINER_NAME)
    cqrs_datacontainer = _snowflake_container(CQRS_CONTAINER_NAME)

    git_config = GitCacheConfig(
        enabled=True,
        access_mode="ReadWriteMany",
        storageClass="azurefile-csi-nfs",
    )

    yp_assembly = YellowAzureExternalAirflow3AndMergeDatabase(
        name="AzureSnowflake",
        namespace=KUB_NAME_SPACE,
        git_cache_config=git_config,
        afHostPortPair=HostPortPair(AIRFLOW_HOST, AIRFLOW_PORT),
        airflowServiceAccount=AIRFLOW_SERVICE_ACCOUNT,
    )

    sf_doc = (
        "Azure Snowflake scale PSP. Snowflake host: "
        f"{SNOWFLAKE_HOST_NAME}; connector account: {AZURE_SF_SNOWFLAKE_ACCOUNT}."
    )

    return YellowPlatformServiceProvider(
        PSP_NAME,
        {_location()},
        PlainTextDocumentation(sf_doc),
        gitCredential=Credential("git", CredentialType.API_TOKEN),
        mergeRW_Credential=Credential("snowflake-runtime", CredentialType.PRIVATE_KEY_AUTH),
        yp_assembly=yp_assembly,
        merge_datacontainer=merge_datacontainer,
        pv_storage_class="azurefile-csi-nfs",
        datasurfaceDockerImage=f"registry.gitlab.com/datasurface-inc/datasurface/datasurface:v{DATASURFACE_VERSION}",
        bulkObjectStorage=_azure_sf_bulk_binding(),
        hints=_ingestion_hints(),
        consumerReplicaGroups=[
            ConsumerReplicaGroup(
                name=CRG_NAME,
                dataContainers={cqrs_datacontainer},
                workspaceNames=set(),
                trigger=CronTrigger("Every 2 minutes", "*/2 * * * *"),
                credential=Credential("snowflake-cqrs", CredentialType.PRIVATE_KEY_AUTH),
                bulkObjectStorages={CQRS_CONTAINER_NAME: _azure_sf_bulk_binding()},
            )
        ],
        dataPlatforms=[
            YellowDataPlatform(
                DATA_PLATFORM_NAME,
                doc=PlainTextDocumentation("SCD2 Yellow DataPlatform on Azure-hosted Snowflake"),
                milestoneStrategy=DataMilestoningStrategy.SCD2,
                stagingBatchesToKeep=5,
            )
        ],
    )


def createAzureSfRTE(ecosys: Ecosystem) -> RuntimeEnvironment:
    assert isinstance(ecosys.owningRepo, GitHubRepository)

    psp = createAzureSfPSP()
    rte = ecosys.getRuntimeEnvironmentOrThrow(RTE_NAME)
    rte.configure(
        VersionPatternReleaseSelector(VersionPatterns.VN_N_N + "-demo", ReleaseType.STABLE_ONLY),
        [PSPDeclaration(psp.name, rte.owningRepo)],
        productionStatus=ProductionStatus.NOT_PRODUCTION,
    )
    rte.setPSP(psp)
    return rte
