"""
// Copyright (c) 2026 William Newport
// SPDX-License-Identifier: BUSL-1.1

This model is intended for load testing. It defines an ecosystem with a single RTE with a CQRS group of 2 servers.
It creates a single GZ with a N blocks. A block is a Team with 50 Datastores. Each datastore is a 2 dataset store using
the simulated customer database datasets and uses CDC for ingestion.
Each Team has a Workspace with all 50 x 2 datasets as DatasetSinks using SCD2 milestoning.

The number of teams is a constant in the model.

The PSP is using postgres (MERGE_HOST). The customer datasimulator runs on SQLSERVER_HOST_A and there are CQRS replicas on both SQLSERVER_HOST_A and B.
"""

from typing import Optional, cast

from datasurface.containers import HostPortPair, SQLCDCIngestion, SQLServerDatabase, SQLDatabase
from datasurface.dsl import (
    ConsumerRetentionRequirements, DataLatency, DataMilestoningStrategy, DataPlatform, DataPlatformManagedDataContainer, DatasetGroup,
    DatasetGroupDataPlatformAssignments, DSGDataPlatformAssignment, DatasetGroupDataPlatformMappingStatus, DeprecationsAllowed, WorkspacePlatformConfig,
    DatasetSink, EnvRefDataContainer, EnvironmentMap, InfrastructureVendor, InfrastructureLocation, Ecosystem,
    CloudVendor, IngestionConsistencyType, ProductionStatus, RuntimeDeclaration, Workspace,
    ConsumerReplicaGroup
)

from datasurface.platforms.yellow import YellowDataPlatform, YellowPlatformServiceProvider
from datasurface.dsl import GovernanceZoneDeclaration, GovernanceZone, TeamDeclaration, Team, Datastore, Dataset
from datasurface.keys import LocationKey, DataPlatformKey
from datasurface.schema import DDLTable, DDLColumn, NullableStatus, PrimaryKeyStatus
from datasurface.policy import SimpleDC, SimpleDCTypes
from datasurface.types import VarChar, Date
from datasurface.security import Credential, CredentialType
from datasurface.documentation import PlainTextDocumentation
from datasurface.repos import GitHubRepository
from datasurface.triggers import CronTrigger
# For AWS deployment, the setup-walkthrough-aws skill changes this to: from rte_aws import createDemoRTE
from rte_demo import createDemoRTE
from db_constants import SQLSERVER_HOST_A

GIT_REPO_OWNER: str = "git_username"  # Change to your github username
GIT_REPO_NAME: str = "gitrepo_name"  # Change to your github repository name containing this project

NUM_TEAMS = 1
NUM_STORES_PER_TEAM = 50


def createGZ(eco: Ecosystem) -> GovernanceZone:
    gz = eco.getZoneOrThrow("gz")
    for i in range(1, NUM_TEAMS):
        gz.add(
            TeamDeclaration(
                f"Team_{i}",
                GitHubRepository(f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}", f"team_{i}_edit", credential=Credential("git", CredentialType.API_TOKEN))
                )
            )
        t: Team = gz.getTeamOrThrow(f"Team_{i}")
        t.add(
            EnvironmentMap(
                "demo",
                dataContainers={
                    frozenset(["customer_db_sqlserver"]): SQLServerDatabase(
                        "CustomerDB",  # Model name for database
                        hostPort=HostPortPair(SQLSERVER_HOST_A, 1433),
                        locations={LocationKey("MyCorp:USA/NY_1")},  # Locations for database
                        productionStatus=ProductionStatus.NOT_PRODUCTION,
                        databaseName="customer_db"  # Database name
                    )
                },
                dtReleaseSelectors=dict(),
                dtDockerImages=dict()
            )
        )
        # Create N Datastores using CDC ingestion from the same customer simulated database, each with 2 datasets (customers and addresses)
        for j in range(1, NUM_STORES_PER_TEAM):
            d: Datastore = Datastore(
                    f"CustomerDB_SQLServer_{j}",
                    documentation=PlainTextDocumentation("Test datastore"),
                    capture_metadata=SQLCDCIngestion(
                        EnvRefDataContainer("customer_db_sqlserver"),
                        CronTrigger("Every 1 minute", "*/1 * * * *"),  # Cron trigger for ingestion
                        IngestionConsistencyType.MULTI_DATASET,  # Ingestion consistency type
                        Credential("customer-sqlserver-source-credential", CredentialType.USER_PASSWORD),  # Credential for platform to read from database
                        ),
                    datasets=[
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
                                    DDLColumn("billingAddressId", VarChar(20))
                                ]
                            ),
                            classifications=[SimpleDC(SimpleDCTypes.CPI, "Customer")]
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
                                    DDLColumn("zipCode", VarChar(30), nullable=NullableStatus.NOT_NULLABLE)
                                ]
                            ),
                            classifications=[SimpleDC(SimpleDCTypes.CPI, "Address")]
                        )
                    ]
                )
            t.add(d)
        # Now create a Workspace with DatasetSinks for all 50 x 2 datasets using SCD2 milestoning
        dsgSinkList: list[DatasetSink] = list()
        for j in range(1, NUM_STORES_PER_TEAM):
            dsgSinkList.append(DatasetSink(f"CustomerDB_SQLServer_{j}", "customers"))
            dsgSinkList.append(DatasetSink(f"CustomerDB_SQLServer_{j}", "addresses"))
        w: Workspace = Workspace(
            f"Team_{i}_Workspace",
            DataPlatformManagedDataContainer("ConsumerCDC container"),
            PlainTextDocumentation("Workspace to consume the datasets in CustomerDB_SQLServer datastore using SCD2"),
            DatasetGroup(
                "SCD2_DSG",
                sinks=dsgSinkList,
                platform_chooser=WorkspacePlatformConfig(
                    hist=ConsumerRetentionRequirements(
                        r=DataMilestoningStrategy.SCD2,
                        latency=DataLatency.MINUTES,
                        regulator=None
                    )
                )
            )
        )
        t.add(w)
    return gz


def addDSGPlatformMappingForWorkspace(eco: Ecosystem, workspace: Workspace, dsg: DatasetGroup, dp: DataPlatform[YellowPlatformServiceProvider]):
    """Add a DSG platform mapping for a workspace/dsg pair, gets set to the current chooser for the dsg"""
    # Find PSP which owns DP
    for psp in eco.getAllDefinedPSPs():
        if dp in psp.dataPlatforms.values():
            break
    else:
        raise Exception(f"Data platform {dp.name} not found in any PSP")

    if psp.dsgPlatformMappings.get(f"{workspace.name}#{dsg.name}") is None:
        psp.dsgPlatformMappings[f"{workspace.name}#{dsg.name}"] = DatasetGroupDataPlatformAssignments(
            workspace=workspace.name,
            dsgName=dsg.name,
            assignments=[
                DSGDataPlatformAssignment(
                    workspace=workspace.name,
                    dsgName=dsg.name,
                    dp=DataPlatformKey(dp.name),
                    doc=PlainTextDocumentation("Test docs"),
                    productionStatus=dp.getProductionStatus(),
                    deprecationsAllowed=DeprecationsAllowed.NEVER,
                    status=DatasetGroupDataPlatformMappingStatus.PROVISIONED)]
        )
    else:
        psp.dsgPlatformMappings[f"{workspace.name}#{dsg.name}"].assignments.append(
            DSGDataPlatformAssignment(
                workspace=workspace.name,
                dsgName=dsg.name,
                dp=DataPlatformKey(dp.name),
                doc=PlainTextDocumentation("Test docs"),
                productionStatus=dp.getProductionStatus(),
                deprecationsAllowed=DeprecationsAllowed.NEVER, status=DatasetGroupDataPlatformMappingStatus.PROVISIONED))


def assignWorkspaceToCRG(eco: Ecosystem):
    # Navigate to the RTE/PSP and then the CRG
    psp: YellowPlatformServiceProvider = cast(YellowPlatformServiceProvider, eco.getPSPOrThrow("Demo_PSP"))
    dp: YellowDataPlatform = cast(YellowDataPlatform, eco.getDataPlatformOrThrow("SCD2"))

    crg: Optional[ConsumerReplicaGroup[SQLDatabase]] = psp.consumerReplicaGroups.get("SQLServers")
    assert crg is not None, "CRG SQLServers not found in PSP Demo_PSP"
    # Add Workspaces to CRG which assignes them to SQL HOST A and B (2 replicas for each Workspace)
    crg.workspaceNames = set()
    for i in range(1, NUM_TEAMS):
        w: Workspace = eco.cache_getWorkspaceOrThrow(f"Team_{i}_Workspace").workspace
        crg.workspaceNames.add(w.name)
        addDSGPlatformMappingForWorkspace(eco, w, w.dsgs["SCD2_DSG"], dp)


def createEcosystem() -> Ecosystem:
    """This is a very simple test model with a single datastore and dataset.
    It is used to test the YellowDataPlatform. We are using a monorepo approach
    so all the model fragments use the same owning repository.

    Updated ecosystem documentation for testing workflow.
    """

    git: Credential = Credential("git", CredentialType.API_TOKEN)
    eRepo: GitHubRepository = GitHubRepository(f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}", "main_edit", credential=git)

    ecosys: Ecosystem = Ecosystem(
        name="Demo",
        repo=eRepo,
        runtimeDecls=[
            RuntimeDeclaration("demo", GitHubRepository(f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}", "demo_rte_edit", credential=git))
        ],
        governance_zone_declarations=[
            GovernanceZoneDeclaration("gz", GitHubRepository(f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}", "gz_edit", credential=git))
        ],
        infrastructure_vendors=[
            # Onsite data centers
            InfrastructureVendor(
                name="MyCorp",
                cloud_vendor=CloudVendor.PRIVATE,
                documentation=PlainTextDocumentation("Private company data centers - updated"),
                locations=[
                    InfrastructureLocation(
                        name="USA",
                        locations=[
                            InfrastructureLocation(name="NY_1")
                        ]
                    )
                ]
            )
        ],
        liveRepo=GitHubRepository(f"{GIT_REPO_OWNER}/{GIT_REPO_NAME}", "main", credential=git)
    )
    # Define the demo RTE
    createDemoRTE(ecosys)
    # Create the GZ and teams with their datastores and workspaces
    createGZ(ecosys)
    # Now assign all the workspaces to the CRG
    assignWorkspaceToCRG(ecosys)

    return ecosys
