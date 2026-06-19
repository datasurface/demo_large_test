#!/usr/bin/env python3
"""
Prepare a unique Azure Snowflake model-merge Kubernetes job.

The generated PSP model-merge job is a reusable template, but Kubernetes Jobs
are immutable and the checked-in artifact can lag the current RTE image during
fast patch testing. This helper renders a uniquely named job and, by default,
keeps the operation as a local dry run.
"""

from __future__ import annotations

import argparse
import ast
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "generated_output" / "AzureSnowflake_PSP" / "azuresnowflake_psp_model_merge_job.yaml"
RTE_FILE = ROOT / "rte_azure_sf.py"
DATASURFACE_IMAGE_REPO = "registry.gitlab.com/datasurface-inc/datasurface/datasurface"
BASE_JOB_NAME = "azuresnowflake-psp-model-merge-job"
K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def rte_datasurface_version(source: str | None = None) -> str:
    source = RTE_FILE.read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(source, filename=str(RTE_FILE))
    values: list[str] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name) or stmt.target.id != "DATASURFACE_VERSION":
            continue
        if not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str):
            raise ValueError("DATASURFACE_VERSION must be assigned a literal string")
        values.append(stmt.value.value)

    if len(values) != 1:
        raise ValueError(f"Expected one DATASURFACE_VERSION assignment, found {len(values)}")
    return values[0]


def default_image() -> str:
    return f"{DATASURFACE_IMAGE_REPO}:v{rte_datasurface_version()}"


def normalize_suffix(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        raise ValueError("name suffix must contain at least one alphanumeric character")
    return normalized


def default_suffix(rung: int | None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
    if rung is not None:
        return f"{rung}-{timestamp}"
    return f"manual-{timestamp}"


def job_name_for(suffix: str) -> str:
    suffix = normalize_suffix(suffix)
    name = f"{BASE_JOB_NAME}-{suffix}"
    if len(name) > 63:
        raise ValueError(f"Kubernetes job name is too long ({len(name)} > 63): {name}")
    if not K8S_NAME_RE.match(name):
        raise ValueError(f"Invalid Kubernetes job name: {name}")
    return name


def render_job(source: str, *, job_name: str, image: str) -> str:
    lines = source.splitlines(keepends=True)
    rendered: list[str] = []
    in_top_metadata = False
    replaced_name = 0
    replaced_image = 0

    for line in lines:
        if line == "metadata:\n":
            in_top_metadata = True
            rendered.append(line)
            continue

        if in_top_metadata and not line.startswith(" "):
            in_top_metadata = False

        if in_top_metadata and line.startswith("  name: "):
            rendered.append(f"  name: {job_name}\n")
            replaced_name += 1
            continue

        stripped = line.lstrip()
        if (
            replaced_image == 0
            and stripped.startswith("image: ")
            and DATASURFACE_IMAGE_REPO in stripped
        ):
            rendered.append(f"{line[:len(line) - len(stripped)]}image: {image}\n")
            replaced_image += 1
            continue

        rendered.append(line)

    if replaced_name != 1:
        raise ValueError(f"Expected to replace one top-level metadata.name, replaced {replaced_name}")
    if replaced_image != 1:
        raise ValueError(f"Expected to replace one DataSurface image, replaced {replaced_image}")

    return "".join(rendered)


def namespace_for(source: str) -> str:
    lines = source.splitlines()
    in_top_metadata = False
    for line in lines:
        if line == "metadata:":
            in_top_metadata = True
            continue
        if in_top_metadata and line and not line.startswith(" "):
            break
        if in_top_metadata and line.startswith("  namespace: "):
            return line.split(":", 1)[1].strip()
    raise ValueError("Could not find top-level metadata.namespace")


def run(command: list[str], *, execute: bool) -> None:
    print("$ " + shell_join(command))
    if execute:
        subprocess.run(command, cwd=ROOT, text=True, check=True)


def create_command(output: Path) -> list[str]:
    return ["kubectl", "create", "-f", str(output)]


def wait_command(namespace: str, job_name: str, timeout: str) -> list[str]:
    return ["kubectl", "wait", "-n", namespace, "--for=condition=complete", f"job/{job_name}", f"--timeout={timeout}"]


def logs_command(namespace: str, job_name: str) -> list[str]:
    return ["kubectl", "logs", "-n", namespace, f"job/{job_name}"]


def write_manifest(rendered: str, requested_output: Path | None, job_name: str) -> Path:
    if requested_output is not None:
        output = requested_output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        return output

    output = Path(tempfile.gettempdir()) / f"{job_name}.yaml"
    output.write_text(rendered, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rung", type=int, help="Scale rung this model merge prepares, such as 150 or 250")
    parser.add_argument("--name-suffix", help="Suffix appended to the generated Kubernetes job name")
    parser.add_argument("--image", default=default_image(), help="DataSurface image to use in the model-merge job")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT, help="Generated model-merge job template")
    parser.add_argument("--output", type=Path, help="Path for the rendered job YAML. Defaults to /tmp/<job>.yaml")
    parser.add_argument("--execute", action="store_true", help="Create the rendered Kubernetes job")
    parser.add_argument("--wait", action="store_true", help="After --execute, wait for the job to complete")
    parser.add_argument("--timeout", default="30m", help="kubectl wait timeout, used with --wait")
    args = parser.parse_args()

    if args.rung is not None and args.rung < 1:
        raise SystemExit("--rung must be at least 1")
    if args.wait and not args.execute:
        raise SystemExit("--wait requires --execute")

    suffix = args.name_suffix or default_suffix(args.rung)
    job_name = job_name_for(suffix)
    source = args.artifact.read_text(encoding="utf-8")
    rendered = render_job(source, job_name=job_name, image=args.image)
    namespace = namespace_for(rendered)
    output = write_manifest(rendered, args.output, job_name)

    action = "EXECUTE" if args.execute else "DRY RUN"
    print(f"{action}: prepare Azure Snowflake model merge job")
    print(f"Job name: {job_name}")
    print(f"Namespace: {namespace}")
    print(f"Image: {args.image}")
    print(f"Rendered manifest: {output}")
    run(create_command(output), execute=args.execute)
    if args.wait:
        run(wait_command(namespace, job_name, args.timeout), execute=True)
    else:
        print("$ " + shell_join(logs_command(namespace, job_name)))


if __name__ == "__main__":
    main()
