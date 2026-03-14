"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

Scalable team definition for performance testing.

This module programmatically generates a large number of ingestion streams (Datastores)
and Consumer Workspaces with CQRS to stress-test DataSurface model processing.

Scale parameters:
  NUM_INGESTION_STREAMS  - number of independent source Datastores to ingest
  NUM_CONSUMER_WORKSPACES - number of Consumer Workspaces that consume the ingested data
  NUM_TABLES_PER_STORE   - number of Dataset tables defined in each Datastore

Increasing these values produces proportionally more pipelines, allowing measurement
of how platform validation and pipeline-generation time grows with model size.
"""

from typing import List

from datasurface.dsl import (
    Team, GovernanceZone, Ecosystem,
    WorkspacePlatformConfig, Datastore, Dataset, Workspace, DatasetGroup, DatasetSink,
    IngestionConsistencyType, ConsumerRetentionRequirements, DataMilestoningStrategy, DataLatency, TeamDeclaration,
    ProductionStatus, DataPlatformManagedDataContainer
)
from datasurface.keys import LocationKey
from datasurface.schema import DDLTable, DDLColumn, NullableStatus, PrimaryKeyStatus
from datasurface.types import VarChar, Date
from datasurface.triggers import CronTrigger
from datasurface.containers import SQLSnapshotIngestion, HostPortPair, PostgresDatabase
from datasurface.security import Credential, CredentialType
from datasurface.documentation import PlainTextDocumentation
from datasurface.repos import GitHubRepository
from datasurface.policy import SimpleDC, SimpleDCTypes

GH_REPO_OWNER: str = "datasurface"
GH_REPO_NAME: str = "demo_large_test"

# ---------------------------------------------------------------------------
# Scale parameters — adjust these to change model size for performance testing
# ---------------------------------------------------------------------------
NUM_INGESTION_STREAMS: int = 10    # Number of independent source Datastores
NUM_CONSUMER_WORKSPACES: int = 10  # Number of Consumer Workspaces
NUM_TABLES_PER_STORE: int = 3      # Tables per Datastore (events, metadata, status)


def _store_name(i: int) -> str:
    return f"Store_{i:03d}"


def _table_names(i: int) -> List[str]:
    """Return the dataset (table) names for store index i."""
    base = [f"events_{i:03d}", f"metadata_{i:03d}", f"status_{i:03d}"]
    # If NUM_TABLES_PER_STORE > 3 add extra generic tables
    for extra in range(3, NUM_TABLES_PER_STORE):
        base.append(f"table_{i:03d}_{extra:02d}")
    return base[:NUM_TABLES_PER_STORE]


def _make_events_schema(i: int) -> DDLTable:
    """Schema for the primary events table in each store."""
    return DDLTable(
        columns=[
            DDLColumn("id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
            DDLColumn("source_id", VarChar(20), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("event_type", VarChar(50), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("event_timestamp", Date(), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("payload", VarChar(4000)),
            DDLColumn("is_processed", VarChar(5)),
            DDLColumn("store_index", VarChar(10)),
        ]
    )


def _make_metadata_schema(i: int) -> DDLTable:
    """Schema for the metadata table in each store."""
    return DDLTable(
        columns=[
            DDLColumn("id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
            DDLColumn("event_id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("key", VarChar(100), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("value", VarChar(1000)),
            DDLColumn("created_at", Date()),
        ]
    )


def _make_status_schema(i: int) -> DDLTable:
    """Schema for the status table in each store."""
    return DDLTable(
        columns=[
            DDLColumn("id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
            DDLColumn("event_id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("status", VarChar(20), nullable=NullableStatus.NOT_NULLABLE),
            DDLColumn("updated_at", Date()),
            DDLColumn("reason", VarChar(500)),
        ]
    )


def _make_extra_table_schema() -> DDLTable:
    """Generic schema for additional tables beyond the first three."""
    return DDLTable(
        columns=[
            DDLColumn("id", VarChar(36), nullable=NullableStatus.NOT_NULLABLE, primary_key=PrimaryKeyStatus.PK),
            DDLColumn("ref_id", VarChar(36)),
            DDLColumn("name", VarChar(200)),
            DDLColumn("value", VarChar(1000)),
            DDLColumn("created_at", Date()),
        ]
    )


def _make_datastore(i: int) -> Datastore:
    """Build a Datastore (ingestion stream) for source index i."""
    store = _store_name(i)
    table_names = _table_names(i)

    datasets: List[Dataset] = []
    for idx, tname in enumerate(table_names):
        if idx == 0:
            schema = _make_events_schema(i)
            classifications = [SimpleDC(SimpleDCTypes.PUB, f"Events from store {i:03d}")]
        elif idx == 1:
            schema = _make_metadata_schema(i)
            classifications = [SimpleDC(SimpleDCTypes.PUB, f"Metadata from store {i:03d}")]
        elif idx == 2:
            schema = _make_status_schema(i)
            classifications = [SimpleDC(SimpleDCTypes.PUB, f"Status from store {i:03d}")]
        else:
            schema = _make_extra_table_schema()
            classifications = [SimpleDC(SimpleDCTypes.PUB, f"Extra table from store {i:03d}")]

        datasets.append(Dataset(tname, schema=schema, classifications=classifications))

    return Datastore(
        store,
        documentation=PlainTextDocumentation(f"Ingestion stream {i:03d} — source database source_db_{i:03d}"),
        capture_metadata=SQLSnapshotIngestion(
            PostgresDatabase(
                f"SourceDB_{i:03d}",
                hostPort=HostPortPair("postgres", 5432),
                locations={LocationKey("MyCorp:USA/NY_1")},
                productionStatus=ProductionStatus.PRODUCTION,
                databaseName=f"source_db_{i:03d}"
            ),
            CronTrigger(f"Every 5 minutes for store {i:03d}", "*/5 * * * *"),
            IngestionConsistencyType.MULTI_DATASET,
            Credential("postgres", CredentialType.USER_PASSWORD),
        ),
        datasets=datasets
    )


def _make_consumer_workspace(j: int) -> Workspace:
    """Build a Consumer Workspace for consumer index j.

    Each workspace has two DatasetGroups demonstrating CQRS:
      LiveDSG   — SCD1 (live / latest-value only), fed by a postgres CRG
      ForensicDSG — SCD2 (full history / milestoned), fed by a sqlserver CRG

    Both groups consume from ALL ingestion stores so that the workspace
    exercises the full breadth of the ingested data.
    """
    ws_name = f"Consumer_{j:03d}"

    # Each workspace consumes the primary events table from every store
    live_sinks: List[DatasetSink] = []
    forensic_sinks: List[DatasetSink] = []
    for i in range(NUM_INGESTION_STREAMS):
        table_names = _table_names(i)
        # Primary (events) table for real-time live view
        live_sinks.append(DatasetSink(_store_name(i), table_names[0]))
        # Primary (events) table for full forensic history
        forensic_sinks.append(DatasetSink(_store_name(i), table_names[0]))

    return Workspace(
        ws_name,
        DataPlatformManagedDataContainer(f"{ws_name} container"),
        DatasetGroup(
            "LiveDSG",
            sinks=live_sinks,
            platform_chooser=WorkspacePlatformConfig(
                hist=ConsumerRetentionRequirements(
                    r=DataMilestoningStrategy.SCD1,
                    latency=DataLatency.MINUTES,
                    regulator=None
                )
            ),
        ),
        DatasetGroup(
            "ForensicDSG",
            sinks=forensic_sinks,
            platform_chooser=WorkspacePlatformConfig(
                hist=ConsumerRetentionRequirements(
                    r=DataMilestoningStrategy.SCD2,
                    latency=DataLatency.MINUTES,
                    regulator=None
                )
            )
        )
    )


def createTeam(ecosys: Ecosystem, git: Credential) -> Team:
    """Create the team and register all Datastores and Consumer Workspaces."""
    gz: GovernanceZone = ecosys.getZoneOrThrow("USA")
    gz.add(TeamDeclaration(
        "team1",
        GitHubRepository(f"{GH_REPO_OWNER}/{GH_REPO_NAME}", "team1_edit", credential=ecosys.owningRepo.credential)
    ))

    team: Team = gz.getTeamOrThrow("team1")

    # Register all ingestion streams (Datastores)
    for i in range(NUM_INGESTION_STREAMS):
        team.add(_make_datastore(i))

    # Register all Consumer Workspaces with CQRS DatasetGroups
    for j in range(NUM_CONSUMER_WORKSPACES):
        team.add(_make_consumer_workspace(j))

    return team
