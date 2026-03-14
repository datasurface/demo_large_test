"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

UAT Runtime Environment for the large-scale performance test model.

Mirrors the production RTE configuration but targets separate UAT databases
and uses NOT_PRODUCTION status throughout.
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

UAT_KUB_NAME_SPACE: str = "yp-large-test-uat"
UAT_AIRFLOW_SERVICE_ACCOUNT: str = "airflow-worker"
POSTGRES_HOST: str = "postgres"
UAT_MERGE_DB_NAME: str = "large_test_merge_db_uat"
UAT_CQRS_POSTGRES_DB: str = "large_test_cqrs_postgres_uat"
UAT_CQRS_SQLSERVER_DB: str = "large_test_cqrs_uat"


def _all_consumer_workspace_names() -> set:
    """Return the set of all consumer workspace names generated in team1."""
    return {f"Consumer_{j:03d}" for j in range(NUM_CONSUMER_WORKSPACES)}


def createPSP() -> YellowPlatformServiceProvider:
    k8s_merge_datacontainer: PostgresDatabase = PostgresDatabase(
        "K8sMergeDB",
        hostPort=HostPortPair(POSTGRES_HOST, 5432),
        locations={LocationKey("MyCorp:USA/NY_1")},
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=UAT_MERGE_DB_NAME
    )

    git_config: GitCacheConfig = GitCacheConfig(
        enabled=True,
        access_mode="ReadWriteMany",
        storageClass="longhorn"
    )
    yp_assembly: YellowExternalAirflow3AndMergeDatabase = YellowExternalAirflow3AndMergeDatabase(
        name="LargeTest_DP_UAT",
        namespace=UAT_KUB_NAME_SPACE,
        roMergeCRGCredential=Credential("postgres", CredentialType.USER_PASSWORD),
        git_cache_config=git_config,
        afHostPortPair=HostPortPair(POSTGRES_HOST, 5432),
        airflowServiceAccount=UAT_AIRFLOW_SERVICE_ACCOUNT
    )

    all_workspaces = _all_consumer_workspace_names()

    psp: YellowPlatformServiceProvider = YellowPlatformServiceProvider(
        "LargeTest_DP_UAT",
        {LocationKey("MyCorp:USA/NY_1")},
        PlainTextDocumentation("Large-scale performance test — UAT PSP"),
        gitCredential=Credential("git", CredentialType.API_TOKEN),
        connectCredentials=Credential("connect", CredentialType.API_TOKEN),
        mergeRW_Credential=Credential("postgres", CredentialType.USER_PASSWORD),
        yp_assembly=yp_assembly,
        merge_datacontainer=k8s_merge_datacontainer,
        datasurfaceDockerImage="datasurface/datasurface:v0.7.2",
        pv_storage_class="longhorn",
        dataPlatforms=[
            YellowDataPlatform(
                name="SCD1_UAT",
                doc=PlainTextDocumentation("SCD1 Yellow DataPlatform UAT (live)"),
                milestoneStrategy=DataMilestoningStrategy.SCD1
            ),
            YellowDataPlatform(
                name="SCD2_UAT",
                doc=PlainTextDocumentation("SCD2 Yellow DataPlatform UAT (forensic)"),
                milestoneStrategy=DataMilestoningStrategy.SCD2
            )
        ],
        consumerReplicaGroups=[
            ConsumerReplicaGroup(
                name="postgres",
                dataContainers={
                    PostgresDatabase(
                        "Postgres",
                        hostPort=HostPortPair(POSTGRES_HOST, 5432),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.NOT_PRODUCTION,
                        databaseName=UAT_CQRS_POSTGRES_DB
                    )
                },
                workspaceNames=all_workspaces,
                trigger=CronTrigger("Every 5 minutes UAT", "*/5 * * * *"),
                credential=Credential("postgres", CredentialType.USER_PASSWORD)
            ),
            ConsumerReplicaGroup(
                name="sqlserver",
                dataContainers={
                    SQLServerDatabase(
                        "SQLServer-uat",
                        hostPort=HostPortPair("sqlserver", 1433),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.NOT_PRODUCTION,
                        databaseName=UAT_CQRS_SQLSERVER_DB
                    )
                },
                workspaceNames=all_workspaces,
                trigger=CronTrigger("Every 5 minutes UAT", "*/5 * * * *"),
                credential=Credential("sa", CredentialType.USER_PASSWORD)
            ),
        ]
    )
    return psp


def createUATRTE(ecosys: Ecosystem) -> RuntimeEnvironment:
    assert isinstance(ecosys.owningRepo, GitHubRepository)

    psp: YellowPlatformServiceProvider = createPSP()
    rte: RuntimeEnvironment = ecosys.getRuntimeEnvironmentOrThrow("uat")
    rte.configure(
        VersionPatternReleaseSelector(VersionPatterns.VN_N_N + "-uat", ReleaseType.ALL),
        [PSPDeclaration(psp.name, rte.owningRepo)],
        ProductionStatus.NOT_PRODUCTION
    )
    rte.setPSP(psp)
    return rte
