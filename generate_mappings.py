"""
Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

Utility script to (re-)generate the DSG-to-DataPlatform mapping JSON files
that DataSurface reads to know which DatasetGroup goes to which DataPlatform.

Run this script whenever NUM_CONSUMER_WORKSPACES in team1.py changes:

    python generate_mappings.py

It writes:
  LargeTest_DP_dsg_platform_mapping.json      — production PSP
  LargeTest_DP_UAT_dsg_platform_mapping.json  — UAT PSP
"""

import json
import os
from team1 import NUM_CONSUMER_WORKSPACES


def _consumer_workspace_names():
    return [f"Consumer_{j:03d}" for j in range(NUM_CONSUMER_WORKSPACES)]


def _build_prod_mapping():
    entries = []
    for ws_name in _consumer_workspace_names():
        # LiveDSG -> SCD1 (live pipeline)
        entries.append({
            "dsgName": "LiveDSG",
            "workspace": ws_name,
            "assignments": [
                {
                    "dataPlatform": "SCD1",
                    "documentation": "SCD1 Yellow DataPlatform (live)",
                    "productionStatus": "PRODUCTION",
                    "deprecationsAllowed": "NEVER",
                    "status": "PROVISIONED"
                }
            ]
        })
        # ForensicDSG -> SCD2 (milestoned / forensic pipeline)
        entries.append({
            "dsgName": "ForensicDSG",
            "workspace": ws_name,
            "assignments": [
                {
                    "dataPlatform": "SCD2",
                    "documentation": "SCD2 Yellow DataPlatform (forensic)",
                    "productionStatus": "PRODUCTION",
                    "deprecationsAllowed": "NEVER",
                    "status": "PROVISIONED"
                }
            ]
        })

    # DataSurface system workspace (added by addDatasurfaceModel)
    entries.append({
        "dsgName": "DSG",
        "workspace": "Datasurface_ModelExternalization",
        "assignments": [
            {
                "dataPlatform": "SCD2",
                "documentation": "SCD2 Yellow DataPlatform (forensic)",
                "productionStatus": "PRODUCTION",
                "deprecationsAllowed": "NEVER",
                "status": "PROVISIONED"
            }
        ]
    })
    return entries


def _build_uat_mapping():
    entries = []
    for ws_name in _consumer_workspace_names():
        entries.append({
            "dsgName": "LiveDSG",
            "workspace": ws_name,
            "assignments": [
                {
                    "dataPlatform": "SCD1_UAT",
                    "documentation": "SCD1 Yellow DataPlatform UAT (live)",
                    "productionStatus": "NOT_PRODUCTION",
                    "deprecationsAllowed": "NEVER",
                    "status": "PROVISIONED"
                }
            ]
        })
        entries.append({
            "dsgName": "ForensicDSG",
            "workspace": ws_name,
            "assignments": [
                {
                    "dataPlatform": "SCD2_UAT",
                    "documentation": "SCD2 Yellow DataPlatform UAT (forensic)",
                    "productionStatus": "NOT_PRODUCTION",
                    "deprecationsAllowed": "NEVER",
                    "status": "PROVISIONED"
                }
            ]
        })

    entries.append({
        "dsgName": "DSG",
        "workspace": "Datasurface_ModelExternalization",
        "assignments": [
            {
                "dataPlatform": "SCD2_UAT",
                "documentation": "SCD2 Yellow DataPlatform UAT (forensic)",
                "productionStatus": "NOT_PRODUCTION",
                "deprecationsAllowed": "NEVER",
                "status": "PROVISIONED"
            }
        ]
    })
    return entries


def generate():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    prod_path = os.path.join(script_dir, "LargeTest_DP_dsg_platform_mapping.json")
    uat_path = os.path.join(script_dir, "LargeTest_DP_UAT_dsg_platform_mapping.json")

    prod_mapping = _build_prod_mapping()
    uat_mapping = _build_uat_mapping()

    with open(prod_path, "w") as f:
        json.dump(prod_mapping, f, indent=2)
    print(f"Written {prod_path} ({len(prod_mapping)} entries)")

    with open(uat_path, "w") as f:
        json.dump(uat_mapping, f, indent=2)
    print(f"Written {uat_path} ({len(uat_mapping)} entries)")


if __name__ == "__main__":
    generate()
