"""
Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
Proprietary Software - See LICENSE.txt for terms.

Concurrent-ingestion scale model for Azure. It creates many logical CDC
datastores over one Azure SQL source database so Airflow/AKS must schedule and
run many independent ingestion streams.
"""

from typing import Optional, cast

from datasurface.containers import AzureSQLDatabase, HostPortPair, SQLCDCIngestion, SQLDatabase
from datasurface.documentation import PlainTextDocumentation
from datasurface.dsl import (
    CloudVendor,
    ConsumerReplicaGroup,
    ConsumerRetentionRequirements,
    DataLatency,
    DataMilestoningStrategy,
    DataPlatform,
    DataPlatformManagedDataContainer,
    DatasetGroup,
    DatasetGroupDataPlatformAssignments,
    DatasetGroupDataPlatformMappingStatus,
    DatasetSink,
    DeprecationsAllowed,
    DSGDataPlatformAssignment,
    EnvRefDataContainer,
    EnvironmentMap,
    Ecosystem,
    GovernanceZone,
    GovernanceZoneDeclaration,
    InfrastructureLocation,
    InfrastructureVendor,
    IngestionConsistencyType,
    ProductionStatus,
    RuntimeDeclaration,
    Team,
    TeamDeclaration,
    Workspace,
    WorkspacePlatformConfig,
)
from datasurface.dsl import Datastore, Dataset
from datasurface.keys import DataPlatformKey, LocationKey
from datasurface.policy import SimpleDC, SimpleDCTypes
from datasurface.repos import GitHubRepository
from datasurface.schema import DDLColumn, DDLTable, NullableStatus, PrimaryKeyStatus
from datasurface.security import Credential, CredentialType
from datasurface.triggers import CronTrigger
from datasurface.types import Date, VarChar
from datasurface.yellow import YellowDataPlatform, YellowPlatformServiceProvider

from db_constants import (
    AZURE_LOCATION_KEY,
    AZURE_SOURCE_DBNAME,
    AZURE_SOURCE_SQL_SERVER_HOST,
    AZURE_SQL_SERVER_PORT,
    AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    NUM_STORES_PER_TEAM,
    NUM_TEAMS,
)
from rte_azure import (
    CRG_NAME as AZURE_CRG_NAME,
    DATA_PLATFORM_NAME as AZURE_DATA_PLATFORM_NAME,
    PSP_NAME as AZURE_PSP_NAME,
    RTE_NAME as AZURE_RTE_NAME,
    createDemoRTE,
)
from rte_azure_sf import (
    CRG_NAME as AZURE_SF_CRG_NAME,
    DATA_PLATFORM_NAME as AZURE_SF_DATA_PLATFORM_NAME,
    PSP_NAME as AZURE_SF_PSP_NAME,
    RTE_NAME as AZURE_SF_RTE_NAME,
    createAzureSfRTE,
)


GIT_REPO_OWNER: str = "datasurface"
GIT_REPO_NAME: str = "demo_large_test"
SOURCE_CONTAINER_REF: str = "customer_db_azuresql"


def _source_container() -> AzureSQLDatabase:
    return AzureSQLDatabase(
        "CustomerDB_AzureSQL",
        hostPort=HostPortPair(AZURE_SOURCE_SQL_SERVER_HOST, AZURE_SQL_SERVER_PORT),
        locations={LocationKey(AZURE_LOCATION_KEY)},
        productionStatus=ProductionStatus.NOT_PRODUCTION,
        databaseName=AZURE_SOURCE_DBNAME,
        trustServerCertificate=AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    )


def _customer_datasets() -> list[Dataset]:
    return [
        Dataset(
            "customers",
            schema=DDLTable(
                columns=[
                    DDLColumn("id", VarChar(20), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
                    DDLColumn("firstName", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("lastName", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("dob", Date(), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("email", VarChar(100)),
                    DDLColumn("phone", VarChar(100)),
                    DDLColumn("primaryAddressId", VarChar(20)),
                    DDLColumn("billingAddressId", VarChar(20)),
                ]
            ),
            classifications=[SimpleDC(SimpleDCTypes.CPI, "Customer")],
        ),
        Dataset(
            "addresses",
            schema=DDLTable(
                columns=[
                    DDLColumn("id", VarChar(20), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
                    DDLColumn("customerId", VarChar(20), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("streetName", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("city", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("state", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
                    DDLColumn("zipCode", VarChar(30), nullable=NullableStatus.NOT_NULLABLE),
                ]
            ),
            classifications=[SimpleDC(SimpleDCTypes.CPI, "Address")],
        ),
    ]


def _store_name(team_idx: int, store_idx: int) -> str:
    return f"CustomerDB_AzureSQL_T{team_idx}_{store_idx}"


def _workspace_name(team_idx: int) -> str:
    return f"Team_{team_idx}_Workspace"


def addDSGPlatformMappingForWorkspace(
    eco: Ecosystem,
    workspace: Workspace,
    dsg: DatasetGroup,
    dp: DataPlatform[YellowPlatformServiceProvider],
) -> None:
    for psp in eco.getAllDefinedPSPs():
        if dp in psp.dataPlatforms.values():
            break
    else:
        raise Exception(f"Data platform {dp.name} not found in any PSP")

    assignment = DSGDataPlatformAssignment(
        workspace=workspace.name,
        dsgName=dsg.name,
        dp=DataPlatformKey(dp.name),
        doc=PlainTextDocumentation("Azure scale test workspace assignment"),
        productionStatus=dp.getProductionStatus(),
        deprecationsAllowed=DeprecationsAllowed.NEVER,
        status=DatasetGroupDataPlatformMappingStatus.PROVISIONED,
    )

    key = f"{workspace.name}#{dsg.name}"
    if psp.dsgPlatformMappings.get(key) is None:
        psp.dsgPlatformMappings[key] = DatasetGroupDataPlatformAssignments(
            workspace=workspace.name,
            dsgName=dsg.name,
            assignments=[assignment],
        )
    else:
        psp.dsgPlatformMappings[key].assignments.append(assignment)


def createGZ(eco: Ecosystem) -> GovernanceZone:
    gz = eco.getZoneOrThrow("gz")
    for team_idx in range(1, NUM_TEAMS + 1):
        gz.add(
            TeamDeclaration(
                f"Team_{team_idx}",
                GitHubRepository(
                    f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}",
                    f"team_{team_idx}_edit",
                    credential=Credential("git", CredentialType.API_TOKEN),
                ),
            )
        )

        team: Team = gz.getTeamOrThrow(f"Team_{team_idx}")
        team.add(
            EnvironmentMap(
                AZURE_RTE_NAME,
                dataContainers={frozenset([SOURCE_CONTAINER_REF]): _source_container()},
                dtReleaseSelectors=dict(),
                dtDockerImages=dict(),
            )
        )
        team.add(
            EnvironmentMap(
                AZURE_SF_RTE_NAME,
                dataContainers={frozenset([SOURCE_CONTAINER_REF]): _source_container()},
                dtReleaseSelectors=dict(),
                dtDockerImages=dict(),
            )
        )

        dsg_sinks: list[DatasetSink] = []
        for store_idx in range(1, NUM_STORES_PER_TEAM + 1):
            store_name = _store_name(team_idx, store_idx)
            team.add(
                Datastore(
                    store_name,
                    documentation=PlainTextDocumentation("Azure SQL CDC scale-test datastore"),
                    capture_metadata=SQLCDCIngestion(
                        EnvRefDataContainer(SOURCE_CONTAINER_REF),
                        CronTrigger("Every 1 minute", "*/1 * * * *"),
                        IngestionConsistencyType.MULTI_DATASET,
                        Credential("customer-sqlserver-source-credential", CredentialType.USER_PASSWORD),
                    ),
                    datasets=_customer_datasets(),
                )
            )
            dsg_sinks.append(DatasetSink(store_name, "customers"))
            dsg_sinks.append(DatasetSink(store_name, "addresses"))

        workspace = Workspace(
            _workspace_name(team_idx),
            DataPlatformManagedDataContainer("Azure scale consumer container"),
            PlainTextDocumentation("Workspace consuming all generated Azure SQL CDC datastores"),
            DatasetGroup(
                "SCD2_DSG",
                sinks=dsg_sinks,
                platform_chooser=WorkspacePlatformConfig(
                    hist=ConsumerRetentionRequirements(
                        r=DataMilestoningStrategy.SCD2,
                        latency=DataLatency.MINUTES,
                        regulator=None,
                    )
                ),
            ),
        )
        team.add(workspace)
        assignWorkspaceToCRG(eco, workspace)
    return gz


def assignWorkspaceToCRG(eco: Ecosystem, workspace: Workspace) -> None:
    _assignWorkspaceToPlatform(eco, workspace, AZURE_PSP_NAME, AZURE_DATA_PLATFORM_NAME, AZURE_CRG_NAME)
    _assignWorkspaceToPlatform(eco, workspace, AZURE_SF_PSP_NAME, AZURE_SF_DATA_PLATFORM_NAME, AZURE_SF_CRG_NAME)


def _assignWorkspaceToPlatform(
    eco: Ecosystem,
    workspace: Workspace,
    psp_name: str,
    data_platform_name: str,
    crg_name: str,
) -> None:
    psp = cast(YellowPlatformServiceProvider, eco.getPSPOrThrow(psp_name))
    dp = cast(YellowDataPlatform, eco.getDataPlatformOrThrow(data_platform_name))

    crg: Optional[ConsumerReplicaGroup[SQLDatabase]] = psp.consumerReplicaGroups.get(crg_name)
    assert crg is not None, f"CRG {crg_name} not found in PSP {psp_name}"
    crg.workspaceNames.add(workspace.name)
    addDSGPlatformMappingForWorkspace(eco, workspace, workspace.dsgs["SCD2_DSG"], dp)


def createEcosystem() -> Ecosystem:
    git = Credential("git", CredentialType.API_TOKEN)
    repo_name = f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}"
    e_repo = GitHubRepository(repo_name, "main_edit", credential=git)

    ecosys = Ecosystem(
        name="Demo",
        repo=e_repo,
        runtimeDecls=[
            RuntimeDeclaration(AZURE_RTE_NAME, GitHubRepository(repo_name, "demo_rte_edit", credential=git)),
            RuntimeDeclaration(AZURE_SF_RTE_NAME, GitHubRepository(repo_name, "azure_sf_rte_edit", credential=git)),
        ],
        governance_zone_declarations=[
            GovernanceZoneDeclaration("gz", GitHubRepository(repo_name, "gz_edit", credential=git))
        ],
        infrastructure_vendors=[
            InfrastructureVendor(
                name="Azure",
                cloud_vendor=CloudVendor.AZURE,
                documentation=PlainTextDocumentation("Microsoft Azure"),
                locations=[
                    InfrastructureLocation(
                        name="USA",
                        locations=[
                            InfrastructureLocation(name="EastUS"),
                            InfrastructureLocation(name="WestUS2"),
                        ],
                    )
                ],
            )
        ],
        liveRepo=GitHubRepository(repo_name, "main", credential=git),
    )

    createDemoRTE(ecosys)
    createAzureSfRTE(ecosys)
    createGZ(ecosys)
    return ecosys
