"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.

This is a starter datasurface repository. It defines a simple Ecosystem using YellowDataPlatform with SCD2 modes. It
ingests data from a single source, using a Workspace to produce a masked version of that data and provides consumer Workspaces
to that data in the primary merge Postgres.

It will generate 1 pipelines and it supports full milestoning (SCD2).
"""

from datasurface.dsl import ProductionStatus, \
    RuntimeEnvironment, Ecosystem, PSPDeclaration, \
    DataMilestoningStrategy, ConsumerReplicaGroup
from datasurface.keys import LocationKey
from datasurface.containers import HostPortPair, PostgresDatabase, SQLServerDatabase
from datasurface.security import Credential, CredentialType
from datasurface.documentation import PlainTextDocumentation
from datasurface.platforms.yellow import YellowDataPlatform, YellowPlatformServiceProvider
from datasurface.platforms.yellow.assembly import GitCacheConfig, YellowExternalAirflow3AndMergeDatabase
from datasurface.repos import VersionPatternReleaseSelector, GitHubRepository, ReleaseType, VersionPatterns
from datasurface.triggers import CronTrigger
from db_constants import MERGE_HOST, SQLSERVER_HOST_A, SQLSERVER_HOST_B

# Docker Desktop configuration
KUB_NAME_SPACE: str = "demo1"
AIRFLOW_SERVICE_ACCOUNT: str = "airflow-worker"
MERGE_DBNAME: str = "merge_db"


def createDemoPSP() -> YellowPlatformServiceProvider:
    # Kubernetes merge database configuration
    k8s_merge_datacontainer: PostgresDatabase = PostgresDatabase(
        "K8sMergeDB",  # Container name for Kubernetes deployment
        hostPort=HostPortPair(MERGE_HOST, 5432),
        locations={LocationKey("MyCorp:USA/NY_1")},  # Kubernetes cluster location
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=MERGE_DBNAME
    )

    git_config: GitCacheConfig = GitCacheConfig(
        enabled=True,
        access_mode="ReadWriteOnce",
        storageClass="standard"
    )
    yp_assembly: YellowExternalAirflow3AndMergeDatabase = YellowExternalAirflow3AndMergeDatabase(
        name="Demo",
        namespace=KUB_NAME_SPACE,
        git_cache_config=git_config
    )

    psp: YellowPlatformServiceProvider = YellowPlatformServiceProvider(
        "Demo_PSP",
        {LocationKey("MyCorp:USA/NY_1")},
        PlainTextDocumentation("Demo PSP"),
        gitCredential=Credential("git", CredentialType.API_TOKEN),
        mergeRW_Credential=Credential("postgres-demo-merge", CredentialType.USER_PASSWORD),
        yp_assembly=yp_assembly,
        merge_datacontainer=k8s_merge_datacontainer,
        pv_storage_class="standard",
        datasurfaceDockerImage="registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.3.7",
        dataPlatforms=[
            YellowDataPlatform(
                "SCD2",
                doc=PlainTextDocumentation("SCD2 Yellow DataPlatform"),
                milestoneStrategy=DataMilestoningStrategy.SCD2,
                stagingBatchesToKeep=5
                )
        ],
        consumerReplicaGroups=[
            ConsumerReplicaGroup(
                "SQLServers",
                dataContainers={
                    SQLServerDatabase(
                        "sqlserverCQRS_A",
                        hostPort=HostPortPair(SQLSERVER_HOST_A, 1433),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.NOT_PRODUCTION,
                        databaseName="large_cqrs_db"
                    ),
                    SQLServerDatabase(
                        "sqlserverCQRS_B",
                        hostPort=HostPortPair(SQLSERVER_HOST_B, 1433),
                        locations={LocationKey("MyCorp:USA/NY_1")},
                        productionStatus=ProductionStatus.NOT_PRODUCTION,
                        databaseName="large_cqrs_db"
                    )
                },
                workspaceNames=set(),
                trigger=CronTrigger("CQRS", "*/5 * * * *"),  # Every 5 minutes
                credential=Credential("sqlserver-cqrs", CredentialType.USER_PASSWORD)
            )
        ]
    )
    return psp


def createDemoRTE(ecosys: Ecosystem) -> RuntimeEnvironment:
    assert isinstance(ecosys.owningRepo, GitHubRepository)

    psp: YellowPlatformServiceProvider = createDemoPSP()
    rte: RuntimeEnvironment = ecosys.getRuntimeEnvironmentOrThrow("demo")
    # Allow edits using RTE repository
    rte.configure(VersionPatternReleaseSelector(
        VersionPatterns.VN_N_N+"-demo", ReleaseType.STABLE_ONLY),
        [PSPDeclaration(psp.name, rte.owningRepo)],
        productionStatus=ProductionStatus.NOT_PRODUCTION)
    rte.setPSP(psp)
    return rte
