"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.

Azure AKS runtime environment configuration for the concurrent-ingestion scale
model. Replace the literal host/database/storage values after Azure resources
are provisioned, then commit the updated model.
"""

from datasurface.containers import AzureObjectContainer, AzureSQLHyperscaleDatabase, HostPortPair
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
    AZURE_BULK_CONTAINER,
    AZURE_BULK_DATA_SOURCE_NAME,
    AZURE_BULK_PREFIX,
    AZURE_BULK_STORAGE_ACCOUNT,
    AZURE_AIRFLOW_POSTGRES_HOST,
    AZURE_AIRFLOW_POSTGRES_PORT,
    AZURE_CQRS_DBNAME,
    AZURE_CQRS_SQL_SERVER_HOST,
    AZURE_LOCATION_KEY,
    AZURE_MERGE_DBNAME,
    AZURE_MERGE_SQL_SERVER_HOST,
    AZURE_SQL_SERVER_PORT,
    AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    INGESTION_LIMIT_CPU,
    INGESTION_LIMIT_MEMORY,
    INGESTION_REQUEST_CPU,
    INGESTION_REQUEST_MEMORY,
    NUM_STORES_PER_TEAM,
    NUM_TEAMS,
)


KUB_NAME_SPACE: str = "ds-scale"
AIRFLOW_HOST: str = AZURE_AIRFLOW_POSTGRES_HOST
AIRFLOW_PORT: int = AZURE_AIRFLOW_POSTGRES_PORT
AIRFLOW_SERVICE_ACCOUNT: str = "airflow-worker"
DATASURFACE_VERSION: str = "1.4.20"
CRG_NAME: str = "AzureHyperscaleCQRS"
CQRS_CONTAINER_NAME: str = "AzureHyperscale_CQRS_DB"


def _location() -> LocationKey:
    return LocationKey(AZURE_LOCATION_KEY)


def _azure_bulk_binding() -> BulkObjectStorageBinding:
    return BulkObjectStorageBinding(
        AzureObjectContainer(
            AZURE_BULK_DATA_SOURCE_NAME,
            {_location()},
            storageAccountName=AZURE_BULK_STORAGE_ACCOUNT,
            containerName=AZURE_BULK_CONTAINER,
            prefix=AZURE_BULK_PREFIX,
        )
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


def createDemoPSP() -> YellowPlatformServiceProvider:
    merge_datacontainer = AzureSQLHyperscaleDatabase(
        "AzureHyperscaleMergeDB",
        hostPort=HostPortPair(AZURE_MERGE_SQL_SERVER_HOST, AZURE_SQL_SERVER_PORT),
        locations={_location()},
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=AZURE_MERGE_DBNAME,
        trustServerCertificate=AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    )

    cqrs_datacontainer = AzureSQLHyperscaleDatabase(
        CQRS_CONTAINER_NAME,
        hostPort=HostPortPair(AZURE_CQRS_SQL_SERVER_HOST, AZURE_SQL_SERVER_PORT),
        locations={_location()},
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=AZURE_CQRS_DBNAME,
        trustServerCertificate=AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    )

    git_config = GitCacheConfig(
        enabled=True,
        access_mode="ReadWriteMany",
        storageClass="azurefile-csi-nfs",
    )

    yp_assembly = YellowAzureExternalAirflow3AndMergeDatabase(
        name="Demo",
        namespace=KUB_NAME_SPACE,
        git_cache_config=git_config,
        afHostPortPair=HostPortPair(AIRFLOW_HOST, AIRFLOW_PORT),
        airflowServiceAccount=AIRFLOW_SERVICE_ACCOUNT,
    )

    return YellowPlatformServiceProvider(
        "Demo_PSP",
        {_location()},
        PlainTextDocumentation("Azure concurrent-ingestion scale PSP"),
        gitCredential=Credential("git", CredentialType.API_TOKEN),
        mergeRW_Credential=Credential("sqlserver-demo-merge", CredentialType.USER_PASSWORD),
        yp_assembly=yp_assembly,
        merge_datacontainer=merge_datacontainer,
        pv_storage_class="azurefile-csi-nfs",
        datasurfaceDockerImage=f"registry.gitlab.com/datasurface-inc/datasurface/datasurface:v{DATASURFACE_VERSION}",
        bulkObjectStorage=_azure_bulk_binding(),
        hints=_ingestion_hints(),
        consumerReplicaGroups=[
            ConsumerReplicaGroup(
                name=CRG_NAME,
                dataContainers={cqrs_datacontainer},
                workspaceNames=set(),
                trigger=CronTrigger("Every 2 minutes", "*/2 * * * *"),
                credential=Credential("sqlserver-cqrs", CredentialType.USER_PASSWORD),
                bulkObjectStorages={CQRS_CONTAINER_NAME: _azure_bulk_binding()},
            )
        ],
        dataPlatforms=[
            YellowDataPlatform(
                "SCD2",
                doc=PlainTextDocumentation("SCD2 Yellow DataPlatform"),
                milestoneStrategy=DataMilestoningStrategy.SCD2,
                stagingBatchesToKeep=5,
            )
        ],
    )


def createDemoRTE(ecosys: Ecosystem) -> RuntimeEnvironment:
    assert isinstance(ecosys.owningRepo, GitHubRepository)

    psp = createDemoPSP()
    rte = ecosys.getRuntimeEnvironmentOrThrow("demo")
    rte.configure(
        VersionPatternReleaseSelector(VersionPatterns.VN_N_N + "-demo", ReleaseType.STABLE_ONLY),
        [PSPDeclaration(psp.name, rte.owningRepo)],
        productionStatus=ProductionStatus.NOT_PRODUCTION,
    )
    rte.setPSP(psp)
    return rte
