#!/usr/bin/env python3
"""
Set the Azure Snowflake scale-test stream count in db_constants.py.

This deliberately edits only NUM_STORES_PER_TEAM. The scale-test model keeps
NUM_TEAMS at 1, so the store count is also the stream count.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_CONSTANTS = ROOT / "db_constants.py"
ASSIGNMENT_RE = re.compile(r"^(NUM_STORES_PER_TEAM:\s*int\s*=\s*)(\d+)(\s*)$", re.MULTILINE)


def _current_count(source: str) -> int:
    tree = ast.parse(source, filename=str(DB_CONSTANTS))
    values: list[int] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        if stmt.target.id != "NUM_STORES_PER_TEAM":
            continue
        if not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, int):
            raise ValueError("NUM_STORES_PER_TEAM must be assigned a literal integer")
        values.append(stmt.value.value)

    if len(values) != 1:
        raise ValueError(f"Expected one NUM_STORES_PER_TEAM assignment, found {len(values)}")
    return values[0]


def set_stream_count(count: int, *, check: bool = False) -> int:
    if count < 1:
        raise ValueError("Stream count must be at least 1")

    source = DB_CONSTANTS.read_text(encoding="utf-8")
    before = _current_count(source)
    updated, replacements = ASSIGNMENT_RE.subn(rf"\g<1>{count}\3", source)
    if replacements != 1:
        raise ValueError(f"Expected one editable NUM_STORES_PER_TEAM assignment, found {replacements}")

    if not check and updated != source:
        DB_CONSTANTS.write_text(updated, encoding="utf-8")

    return before


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("count", type=int, help="Number of Azure Snowflake streams to configure")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the requested edit without writing db_constants.py",
    )
    args = parser.parse_args()

    before = set_stream_count(args.count, check=args.check)
    action = "would set" if args.check else "set"
    print(f"{action} NUM_STORES_PER_TEAM from {before} to {args.count}")


if __name__ == "__main__":
    main()
