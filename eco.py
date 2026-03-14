"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

This is a large-scale performance test model for DataSurface.
It creates a scalable ecosystem with many ingestion streams and Consumer Workspaces
with CQRS to stress-test the platform's model processing and pipeline generation.
"""

from datasurface.dsl import InfrastructureVendor, InfrastructureLocation, Ecosystem, CloudVendor, RuntimeDeclaration
from datasurface.security import Credential, CredentialType
from datasurface.documentation import PlainTextDocumentation
from datasurface.repos import GitHubRepository
from datasurface.validation import ValidationTree
from datasurface.model import addDatasurfaceModel
from gz import createGZ
from rte_prod import createProdRTE
from rte_uat import createUATRTE

GH_REPO_OWNER: str = "datasurface"
GH_REPO_NAME: str = "demo_large_test"


def createEcosystem() -> Ecosystem:
    """Creates a large-scale DataSurface ecosystem for performance testing.

    This model generates many ingestion streams and Consumer Workspaces with
    CQRS (Command Query Responsibility Segregation) to measure how the platform
    scales as the number of pipelines grows.
    """

    git: Credential = Credential("git", CredentialType.API_TOKEN)
    eRepo: GitHubRepository = GitHubRepository(f"{GH_REPO_OWNER}/{GH_REPO_NAME}", "main_edit", credential=git)

    ecosys: Ecosystem = Ecosystem(
        name="LargeTest",
        repo=eRepo,
        runtimeDecls=[
            RuntimeDeclaration("prod", GitHubRepository(eRepo.repositoryName, "prod_rte_edit", credential=git)),
            RuntimeDeclaration("uat", GitHubRepository(eRepo.repositoryName, "uat_rte_edit", credential=git))
        ],
        infrastructure_vendors=[
            InfrastructureVendor(
                name="MyCorp",
                cloud_vendor=CloudVendor.PRIVATE,
                documentation=PlainTextDocumentation("Private company data centers"),
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
        liveRepo=GitHubRepository(f"{GH_REPO_OWNER}/{GH_REPO_NAME}", "main", credential=git)
    )

    createProdRTE(ecosys)
    createUATRTE(ecosys)
    addDatasurfaceModel(ecosys, ecosys.owningRepo)
    createGZ(ecosys, git)

    _: ValidationTree = ecosys.lintAndHydrateCaches()
    return ecosys
