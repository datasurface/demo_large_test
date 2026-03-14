# Copyright (c) 2025 DataSurface Inc. All Rights Reserved.

import time
import unittest
from typing import Any, Optional

from datasurface.dsl import Ecosystem, DataPlatform, EcosystemPipelineGraph, PlatformPipelineGraph
from datasurface.validation import ValidationTree
from datasurface.model import loadEcosystemFromEcoModule

from team1 import NUM_INGESTION_STREAMS, NUM_CONSUMER_WORKSPACES, NUM_TABLES_PER_STORE


class TestLargeScaleEcosystem(unittest.TestCase):
    """Validates the large-scale performance test ecosystem."""

    def _validate_tree(self, ecoTree: ValidationTree, label: str) -> None:
        if ecoTree.hasErrors():
            print(f"[{label}] Ecosystem validation failed with errors:")
            ecoTree.printTree()
            raise AssertionError(f"[{label}] Ecosystem validation failed")
        print(f"[{label}] Ecosystem validated OK")
        if ecoTree.hasWarnings():
            print(f"[{label}] Warnings:")
            ecoTree.printTree()

    def test_ecosystem_loads_and_validates(self):
        """The ecosystem must load and pass validation without errors."""
        start = time.monotonic()
        ecosys: Optional[Ecosystem]
        ecoTree: Optional[ValidationTree]

        ecosys, ecoTree = loadEcosystemFromEcoModule(".")
        self.assertIsNotNone(ecosys)
        self.assertIsNotNone(ecoTree)
        assert ecoTree is not None
        assert ecosys is not None
        self._validate_tree(ecoTree, "base")
        elapsed = time.monotonic() - start
        print(f"Base load time: {elapsed:.2f}s  "
              f"(streams={NUM_INGESTION_STREAMS}, workspaces={NUM_CONSUMER_WORKSPACES}, "
              f"tables_per_store={NUM_TABLES_PER_STORE})")

    def test_prod_rte_loads_and_validates(self):
        """The ecosystem must load and validate with the production RTE attached."""
        start = time.monotonic()
        ecosys: Optional[Ecosystem]
        ecoTree: Optional[ValidationTree]

        ecosys, ecoTree = loadEcosystemFromEcoModule(".", "prod")
        self.assertIsNotNone(ecosys)
        self.assertIsNotNone(ecoTree)
        assert ecoTree is not None
        assert ecosys is not None
        self._validate_tree(ecoTree, "prod RTE")

        # Additional hydration pass
        vTree: ValidationTree = ecosys.lintAndHydrateCaches()
        self._validate_tree(vTree, "prod hydration")

        elapsed = time.monotonic() - start
        print(f"Prod RTE load time: {elapsed:.2f}s")

    def test_data_platforms_exist(self):
        """SCD1 and SCD2 data platforms must be present in the production RTE."""
        ecosys, ecoTree = loadEcosystemFromEcoModule(".", "prod")
        assert ecosys is not None

        scd1: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD1")  # type: ignore
        self.assertIsNotNone(scd1)

        scd2: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD2")  # type: ignore
        self.assertIsNotNone(scd2)

    def test_pipeline_graph_has_roots(self):
        """Both SCD1 and SCD2 must appear as roots in the pipeline graph."""
        ecosys, ecoTree = loadEcosystemFromEcoModule(".", "prod")
        assert ecosys is not None

        graph: EcosystemPipelineGraph = ecosys.getGraph()
        self.assertIsNotNone(graph)

        scd1: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD1")  # type: ignore
        scd2: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD2")  # type: ignore

        scd1_root: Optional[PlatformPipelineGraph] = graph.roots.get(scd1.name)
        self.assertIsNotNone(scd1_root, "SCD1 must appear as a pipeline graph root")

        scd2_root: Optional[PlatformPipelineGraph] = graph.roots.get(scd2.name)
        self.assertIsNotNone(scd2_root, "SCD2 must appear as a pipeline graph root")

    def test_scale_parameters(self):
        """Scale parameters must be positive integers."""
        self.assertGreater(NUM_INGESTION_STREAMS, 0, "NUM_INGESTION_STREAMS must be > 0")
        self.assertGreater(NUM_CONSUMER_WORKSPACES, 0, "NUM_CONSUMER_WORKSPACES must be > 0")
        self.assertGreater(NUM_TABLES_PER_STORE, 0, "NUM_TABLES_PER_STORE must be > 0")
        print(f"Scale: {NUM_INGESTION_STREAMS} streams × {NUM_TABLES_PER_STORE} tables/store, "
              f"{NUM_CONSUMER_WORKSPACES} consumer workspaces")

    def test_all_stores_present(self):
        """Every generated store must be registered in the ecosystem."""
        ecosys, ecoTree = loadEcosystemFromEcoModule(".")
        assert ecosys is not None
        gz = ecosys.getZoneOrThrow("USA")
        team = gz.getTeamOrThrow("team1")
        for i in range(NUM_INGESTION_STREAMS):
            store_name = f"Store_{i:03d}"
            store = team.getStoreOrThrow(store_name)
            self.assertIsNotNone(store, f"{store_name} must be registered")

    def test_all_consumer_workspaces_present(self):
        """Every generated consumer workspace must be registered in the ecosystem."""
        ecosys, ecoTree = loadEcosystemFromEcoModule(".")
        assert ecosys is not None
        gz = ecosys.getZoneOrThrow("USA")
        team = gz.getTeamOrThrow("team1")
        for j in range(NUM_CONSUMER_WORKSPACES):
            ws_name = f"Consumer_{j:03d}"
            ws = team.getWorkspaceOrThrow(ws_name)
            self.assertIsNotNone(ws, f"{ws_name} must be registered")


if __name__ == "__main__":
    unittest.main()
