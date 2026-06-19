import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


def _load_tool(name: str):
    script = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_release = _load_tool("prepare_azure_sf_rung_release")
prepare_model_merge = _load_tool("prepare_azure_sf_model_merge_job")


SAMPLE_MODEL_MERGE_JOB = """# model-merge-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: azuresnowflake-psp-model-merge-job
  namespace: ds-scale-azure-sf
spec:
  template:
    spec:
      containers:
      - name: model-merge-handler
        image: registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.4.65-azsf-fix5
        command: ["/bin/bash"]
"""


class TestAzureSfTools(unittest.TestCase):
    def test_default_next_tag_follows_demo_tags(self) -> None:
        with patch.object(prepare_release, "existing_demo_tags", return_value=["v1.0.13-demo", "v1.0.14-demo"]):
            self.assertEqual(prepare_release.next_demo_tag(), "v1.0.15-demo")

    def test_validation_env_prefers_local_datasurface_source(self) -> None:
        env = prepare_release.validation_env()

        self.assertEqual(env["DATASURFACE_ESO_RECONCILE"], "false")
        self.assertTrue(env["PYTHONPATH"].startswith("/Users/billy/code/datasurface/src"))

    def test_github_release_command_documents_stable_release(self) -> None:
        command = prepare_release.github_release_command("v1.0.15-demo", 150)

        self.assertEqual(command[:3], ["gh", "release", "create"])
        self.assertIn("v1.0.15-demo", command)
        self.assertIn("Azure Snowflake 150-stream scale rung model release.", command)

    def test_execute_restores_count_when_validation_fails_before_commit(self) -> None:
        args = Namespace(count=150, push=False, restore_on_failure=True, github_release=True)

        with tempfile.TemporaryDirectory() as tmp:
            db_constants = Path(tmp) / "db_constants.py"
            db_constants.write_text("NUM_TEAMS: int = 1\nNUM_STORES_PER_TEAM: int = 400\n", encoding="utf-8")
            original_db_constants = prepare_release.stream_count_tool.DB_CONSTANTS
            prepare_release.stream_count_tool.DB_CONSTANTS = db_constants
            try:
                with (
                    patch.object(prepare_release, "ensure_clean_worktree"),
                    patch.object(prepare_release, "validation_command", return_value=["validate"]),
                    patch.object(prepare_release, "validation_env", return_value={}),
                    patch.object(prepare_release, "run", side_effect=RuntimeError("validation failed")),
                ):
                    with self.assertRaises(RuntimeError):
                        prepare_release.execute_release(args, before=400, tag="v1.0.99-demo")
            finally:
                prepare_release.stream_count_tool.DB_CONSTANTS = original_db_constants

            self.assertIn("NUM_STORES_PER_TEAM: int = 400", db_constants.read_text(encoding="utf-8"))

    def test_restore_count_can_be_disabled(self) -> None:
        args = Namespace(count=150, push=False, restore_on_failure=False, github_release=True)

        with tempfile.TemporaryDirectory() as tmp:
            db_constants = Path(tmp) / "db_constants.py"
            db_constants.write_text("NUM_TEAMS: int = 1\nNUM_STORES_PER_TEAM: int = 400\n", encoding="utf-8")
            original_db_constants = prepare_release.stream_count_tool.DB_CONSTANTS
            prepare_release.stream_count_tool.DB_CONSTANTS = db_constants
            try:
                with (
                    patch.object(prepare_release, "ensure_clean_worktree"),
                    patch.object(prepare_release, "validation_command", return_value=["validate"]),
                    patch.object(prepare_release, "validation_env", return_value={}),
                    patch.object(prepare_release, "run", side_effect=RuntimeError("validation failed")),
                ):
                    with self.assertRaises(RuntimeError):
                        prepare_release.execute_release(args, before=400, tag="v1.0.99-demo")
            finally:
                prepare_release.stream_count_tool.DB_CONSTANTS = original_db_constants

            self.assertIn("NUM_STORES_PER_TEAM: int = 150", db_constants.read_text(encoding="utf-8"))

    def test_execute_push_creates_github_release_after_pushing_tag(self) -> None:
        args = Namespace(count=150, push=True, restore_on_failure=True, github_release=True)

        with tempfile.TemporaryDirectory() as tmp:
            db_constants = Path(tmp) / "db_constants.py"
            db_constants.write_text("NUM_TEAMS: int = 1\nNUM_STORES_PER_TEAM: int = 400\n", encoding="utf-8")
            original_db_constants = prepare_release.stream_count_tool.DB_CONSTANTS
            prepare_release.stream_count_tool.DB_CONSTANTS = db_constants
            try:
                with (
                    patch.object(prepare_release, "ensure_clean_worktree"),
                    patch.object(prepare_release, "validation_command", return_value=["validate"]),
                    patch.object(prepare_release, "validation_env", return_value={}),
                    patch.object(prepare_release, "run") as run,
                ):
                    prepare_release.execute_release(args, before=400, tag="v1.0.99-demo")
            finally:
                prepare_release.stream_count_tool.DB_CONSTANTS = original_db_constants

            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn(["git", "push", "origin", "main"], commands)
            self.assertIn(["git", "push", "origin", "v1.0.99-demo"], commands)
            self.assertIn(prepare_release.github_release_command("v1.0.99-demo", 150), commands)

    def test_model_merge_default_image_tracks_rte_version(self) -> None:
        version = prepare_model_merge.rte_datasurface_version('DATASURFACE_VERSION: str = "1.4.65-azsf-fix6"\n')

        self.assertEqual(version, "1.4.65-azsf-fix6")

    def test_model_merge_job_name_is_normalized_and_bounded(self) -> None:
        self.assertEqual(
            prepare_model_merge.job_name_for("Rung_150_Cold"),
            "azuresnowflake-psp-model-merge-job-rung-150-cold",
        )

        with self.assertRaises(ValueError):
            prepare_model_merge.job_name_for("x" * 40)

    def test_model_merge_render_changes_unique_name_and_image(self) -> None:
        rendered = prepare_model_merge.render_job(
            SAMPLE_MODEL_MERGE_JOB,
            job_name="azuresnowflake-psp-model-merge-job-150-010203",
            image="registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.4.65-azsf-fix6",
        )

        self.assertIn("name: azuresnowflake-psp-model-merge-job-150-010203", rendered)
        self.assertIn("namespace: ds-scale-azure-sf", rendered)
        self.assertIn("image: registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.4.65-azsf-fix6", rendered)
        self.assertNotIn("v1.4.65-azsf-fix5", rendered)

    def test_model_merge_namespace_and_commands(self) -> None:
        rendered = prepare_model_merge.render_job(
            SAMPLE_MODEL_MERGE_JOB,
            job_name="azuresnowflake-psp-model-merge-job-250-010203",
            image="registry.gitlab.com/datasurface-inc/datasurface/datasurface:v1.4.65-azsf-fix6",
        )

        self.assertEqual(prepare_model_merge.namespace_for(rendered), "ds-scale-azure-sf")
        self.assertEqual(
            prepare_model_merge.create_command(Path("/tmp/job.yaml")),
            ["kubectl", "create", "-f", "/tmp/job.yaml"],
        )
        self.assertEqual(
            prepare_model_merge.wait_command("ds-scale-azure-sf", "job-name", "30m"),
            ["kubectl", "wait", "-n", "ds-scale-azure-sf", "--for=condition=complete", "job/job-name", "--timeout=30m"],
        )
        self.assertEqual(
            prepare_model_merge.logs_command("ds-scale-azure-sf", "job-name"),
            ["kubectl", "logs", "-n", "ds-scale-azure-sf", "job/job-name"],
        )


if __name__ == "__main__":
    unittest.main()
