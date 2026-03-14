"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

Production Runtime Environment for the large-scale performance test model.

The CQRS pattern is realised through two ConsumerReplicaGroups:
  postgres   — Postgres database that receives all consumer workspace data using SCD1 and SCD2
  sqlserver  — SQL Server database that independently receives the same data

This means ingestion happens once into the merge database and then is replicated
to both consumer stores in parallel — demonstrating CQRS at scale.
"""

from datasurface.dsl import (
    ProductionStatus, DataMilestoningStrategy,
    ConsumerReplicaGroup, RuntimeEnvironment, Ecosystem, PSPDeclaration
)
from datasurface.keys import LocationKey
from datasurface.containers import HostPortPair, SQLServerDatabase, PostgresDatabase
from datasurface.security import Credential, CredentialType
from datasurface.documentation import PlainTextDocumentation
from datasurface.platforms.yellow import YellowDataPlatform, YellowPlatformServiceProvider
from datasurface.triggers import CronTrigger
from datasurface.platforms.yellow.assembly import GitCacheConfig, YellowExternalAirflow3AndMergeDatabase
from datasurface.repos import VersionPatternReleaseSelector, GitHubRepository, ReleaseType, VersionPatterns

from team1 import NUM_CONSUMER_WORKSPACES

KUB_NAME_SPACE: str = "yp-large-test"
AIRFLOW_SERVICE_ACCOUNT: str = "airflow-worker"
POSTGRES_HOST: str = "postgres"
MERGE_DB_NAME: str = "large_test_merge_db"
CQRS_POSTGRES_DB: str = "large_test_cqrs_postgres"
CQRS_SQLSERVER_DB: str = "large_test_cqrs"


def _all_consumer_workspace_names() -> set:
    """Return the set of all consumer workspace names generated in team1."""
    return {f"Consumer_{j:03d}" for j in range(NUM_CONSUMER_WORKSPACES)}


def createPSP() -> YellowPlatformServiceProvider:
    k8s_merge_datacontainer: PostgresDatabase = PostgresDatabase(
        "K8sMergeDB",
        hostPort=HostPortPair(POSTGRES_HOST, 5432),
        locations={LocationKey("MyCorp:USA/NY_1")},
        productionStatus=ProductionStatus.PRODUCTION,
        databaseName=MERGE_DB_NAME
    )

    git_config: GitCacheConfig = GitCacheConfig(
        enabled=True,
        access_mode="ReadWriteMany",
        storageClass="longhorn"
    )
    yp_assembly: YellowExternalAirflow3AndMergeDatabase = YellowExternalAirflow3AndMergeDatabase(
        name="LargeTest_DP",
        namespace=KUB_NAME_SPACE,
        roMergeCRGCredential=Credential("postgres", CredentialType.USER_PASSWORD),
        git_cache_config=git_config,
        afHostPortPair=HostPortPair(POSTGRES_HOST, 5432),
        airflowServiceAccount=AIRFLOW_SERVICE_ACCOUNT
    )

    all_workspaces = _all_consumer_workspace_names()

    psp: YellowPlatformServiceProvider = YellowPlatformServiceProvider(
        "LargeTest_DP",
        {LocationKey("MyCorp:USA/NY_1")},
        PlainTextDocumentation("Large-scale performance test — production PSP"),
        gitCredential=Credential("git", CredentialType.API_TOKEN),
        connectCredentials=Credential("connect", CredentialType.API_TOKEN),
        mergeRW_Credential=Credential("postgres", CredentialType.USER_PASSWORD),
        yp_assembly=yp_assembly,
        merge_datacontainer=k8s_merge_datacontainer,
        pv_storage_class="longhorn",
        datasurfaceDockerImage="datasurface/datasurface:v0.7.2",
        dataPlatforms=[
            # SCD1 — live / latest-value pipeline for LiveDSG
            YellowDataPlatform(
                name="SCD1",
                doc=PlainTextDocumentation("SCD1 Yellow DataPlatform (live)"),
                milestoneStrategy=DataMilestoningStrategy.SCD1,
                stagingBatchesToKeep=5
            ),
            # SCD2 — full-history / milestoned pipeline for ForensicDSG
            YellowDataPlatform(
                name="SCD2",
                doc=PlainTextDocumentation("SCD2 Yellow DataPlatform (forensic)"),
                milestoneStrategy=DataMilestoningStrategy.SCD2,
                stagingBatchesToKeep=5
            )
        ],
        # CQRS: two Consumer Replica Groups fed from the same ingestion
        consumerReplicaGroups=[
            # Primary read replica — Postgres
            ConsumerReplicaGroup(
                name="postgres",
                dataContainers={
                    PostgresDatabase(
                        "Postgres",
                        hostPort=HostPortPair(POSTGRES_HOST, 5432),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.PRODUCTION,
                        databaseName=CQRS_POSTGRES_DB
                    )
                },
                workspaceNames=all_workspaces,
                trigger=CronTrigger("Every 5 minutes", "*/5 * * * *"),
                credential=Credential("postgres", CredentialType.USER_PASSWORD)
            ),
            # Analytics read replica — SQL Server
            ConsumerReplicaGroup(
                name="sqlserver",
                dataContainers={
                    SQLServerDatabase(
                        "SQLServer",
                        hostPort=HostPortPair("sqlserver", 1433),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.PRODUCTION,
                        databaseName=CQRS_SQLSERVER_DB
                    )
                },
                workspaceNames=all_workspaces,
                trigger=CronTrigger("Every 5 minutes", "*/5 * * * *"),
                credential=Credential("sa", CredentialType.USER_PASSWORD)
            ),
        ]
    )
    return psp


def createProdRTE(ecosys: Ecosystem) -> RuntimeEnvironment:
    assert isinstance(ecosys.owningRepo, GitHubRepository)

    psp: YellowPlatformServiceProvider = createPSP()
    rte: RuntimeEnvironment = ecosys.getRuntimeEnvironmentOrThrow("prod")
    rte.configure(
        VersionPatternReleaseSelector(VersionPatterns.VN_N_N + "-prod", ReleaseType.STABLE_ONLY),
        [PSPDeclaration(psp.name, rte.owningRepo)],
        productionStatus=ProductionStatus.PRODUCTION
    )
    rte.setPSP(psp)
    return rte
