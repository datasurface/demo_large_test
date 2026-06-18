# Copyright (c) 2026 DataSurface Inc. All Rights Reserved.
# Proprietary Software - See LICENSE.txt for terms.

import unittest
from datasurface.dsl import Ecosystem, DataPlatform, EcosystemPipelineGraph, PlatformPipelineGraph
from datasurface.validation import ValidationTree
from datasurface.model import loadEcosystemFromEcoModule
from typing import Any, Optional


class TestEcosystem(unittest.TestCase):
    def _assert_loads_without_errors(self, rte_name: str) -> Ecosystem:
        ecosys: Optional[Ecosystem]
        ecoTree: Optional[ValidationTree]
        ecosys, ecoTree = loadEcosystemFromEcoModule(".", rte_name)
        self.assertIsNotNone(ecosys)
        self.assertIsNotNone(ecoTree)
        assert ecoTree is not None
        assert ecosys is not None
        if ecoTree.hasErrors():
            print(f"Ecosystem validation failed with errors for RTE {rte_name}:")
            ecoTree.printTree()
            raise Exception("Ecosystem validation failed")
        return ecosys

    def test_createEcosystem(self):
        ecosys: Optional[Ecosystem]
        ecoTree: Optional[ValidationTree]
        ecosys, ecoTree = loadEcosystemFromEcoModule(".")  # Check like a PR would first.
        self.assertIsNotNone(ecosys)
        self.assertIsNotNone(ecoTree)
        assert ecoTree is not None
        assert ecosys is not None
        if ecoTree.hasErrors():
            print("Ecosystem validation failed with errors:")
            ecoTree.printTree()
            raise Exception("Ecosystem validation failed")
        else:
            print("Ecosystem validated OK")
            if ecoTree.hasWarnings():
                print("Note: There are some warnings:")
                ecoTree.printTree()

        ecosys = self._assert_loads_without_errors("demo")
        vTree: ValidationTree = ecosys.lintAndHydrateCaches()
        if (vTree.hasErrors()):
            print("Ecosystem validation failed with errors:")
            vTree.printTree()
            raise Exception("Ecosystem validation failed")
        else:
            print("Ecosystem validated OK")
            if vTree.hasWarnings():
                print("Note: There are some warnings:")
                vTree.printTree()
        scd2_dp: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD2")  # type: ignore
        self.assertIsNotNone(scd2_dp)
        graph: EcosystemPipelineGraph = ecosys.getGraph()
        self.assertIsNotNone(graph)
        scd2_root: Optional[PlatformPipelineGraph] = graph.roots.get(scd2_dp.name)
        self.assertIsNotNone(scd2_root)

    def test_azure_sf_createEcosystem(self):
        ecosys = self._assert_loads_without_errors("azure_sf")
        scd2_azure_sf_dp: DataPlatform[Any] = ecosys.getDataPlatformOrThrow("SCD2_AZURE_SF")  # type: ignore
        self.assertIsNotNone(scd2_azure_sf_dp)
        graph: EcosystemPipelineGraph = ecosys.getGraph()
        self.assertIsNotNone(graph)
        scd2_azure_sf_root: Optional[PlatformPipelineGraph] = graph.roots.get(scd2_azure_sf_dp.name)
        self.assertIsNotNone(scd2_azure_sf_root)


if __name__ == "__main__":
    unittest.main()
