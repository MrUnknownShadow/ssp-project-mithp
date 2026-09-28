"""Command line entry point.

Runs the full pipeline over a pair of security requirements documents:
Task-1 extraction, Task-2 comparison, Task-3 Hadolint execution.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from comparator import run_comparison
from executor import run_execution
from extractor import run_extraction


def build_parser():
    """Define the command line interface."""
    parser = argparse.ArgumentParser(
        prog="ssp-project",
        description=(
            "Detect changes between two security requirements documents and "
            "run Hadolint based on the differences found."
        ),
    )
    parser.add_argument("document_a", help="path to the first PDF")
    parser.add_argument("document_b", help="path to the second PDF")
    parser.add_argument(
        "--dockerfiles",
        default="data/dockerfiles",
        help="directory of Dockerfiles to scan (default: data/dockerfiles)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="directory for generated files (default: output)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="process only the first N sections per document (for testing)",
    )
    return parser


def main(argv=None):
    """Run all three tasks end to end."""
    args = build_parser().parse_args(argv)

    print("=== Task-1: extracting key data elements ===")
    yaml_paths, llm_log = run_extraction(
        args.document_a, args.document_b, limit=args.limit
    )

    print("\n=== Task-2: comparing extracted elements ===")
    name_diff, requirement_diff = run_comparison(
        yaml_paths[0], yaml_paths[1], output_dir=args.output_dir
    )

    print("\n=== Task-3: running Hadolint ===")
    csv_path = run_execution(
        name_diff,
        requirement_diff,
        args.dockerfiles,
        output_dir=args.output_dir,
    )

    print("\n=== Done ===")
    for path in (*yaml_paths, llm_log, name_diff, requirement_diff, csv_path):
        print(f"  {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())