"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

Governance zone definition for the large-scale performance test model.
"""

from datasurface.dsl import GovernanceZone, GovernanceZoneDeclaration, Ecosystem
from datasurface.security import Credential
from datasurface.repos import GitHubRepository
from team1 import createTeam

GH_REPO_OWNER: str = "datasurface"
GH_REPO_NAME: str = "demo_large_test"


def createGZ(ecosys: Ecosystem, git: Credential) -> GovernanceZone:
    ecosys.add(GovernanceZoneDeclaration("USA", GitHubRepository(f"{GH_REPO_OWNER}/{GH_REPO_NAME}", "gzUSA_edit")))
    gz: GovernanceZone = ecosys.getZoneOrThrow("USA")
    createTeam(ecosys, git)
    return gz
