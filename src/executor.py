"""Task-3: Executor.

Reads the difference reports from Task-2, maps the differences to Hadolint
rule IDs, runs Hadolint over a directory of Dockerfiles, and writes the
findings to CSV.
"""

import json
import os
import subprocess

import pandas as pd

NO_DIFFERENCES_FOUND = "NO DIFFERENCES FOUND"

NAME_DIFF_PREFIXES = ("ONLY IN FIRST DOCUMENT,", "ONLY IN SECOND DOCUMENT,")

NO_DIFFERENCE_MARKERS = (
    "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES",
    "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS",
)

# Maps a keyword found in a changed key data element to the Hadolint rules
# that check the corresponding Dockerfile concern.
KEYWORD_RULE_MAP = {
    "user": ["DL3002", "DL3066"],
    "root": ["DL3002"],
    "privilege": ["DL3002"],
    "version": ["DL3006", "DL3007", "DL3008", "DL3048"],
    "tag": ["DL3006", "DL3007"],
    "latest": ["DL3007"],
    "image": ["DL3006", "DL3007", "DL3026"],
    "package": ["DL3008", "DL3009", "DL3015"],
    "apt": ["DL3008", "DL3009", "DL3015"],
    "update": ["DL3008", "DL3009"],
    "install": ["DL3008", "DL3015"],
    "copy": ["DL3020", "DL3021"],
    "add": ["DL3020"],
    "download": ["DL3020"],
    "port": ["DL3011"],
    "expose": ["DL3011"],
    "health": ["DL3057"],
    "secret": ["DL3003"],
    "workdir": ["DL3000", "DL3003"],
    "shell": ["DL4005", "DL4006"],
    "pipe": ["DL4006"],
    "label": ["DL3048"],
    "registry": ["DL3026"],
    "signature": ["DL3026"],
    "trust": ["DL3026"],
}


class ExecutorInputError(ValueError):
    """Raised when a Task-2 difference report is missing or unreadable."""


# ---------------------------------------------------------------------------
# Function 1: read the Task-2 difference reports
# ---------------------------------------------------------------------------


def load_difference_reports(name_diff_path, requirement_diff_path):
    """Task-3: load the two TEXT difference reports produced by Task-2."""
    return {
        "names": _validated_lines(name_diff_path),
        "requirements": _validated_lines(requirement_diff_path),
    }


def _validated_lines(path):
    """Validate one report path and return its non-empty lines."""
    if not isinstance(path, str) or not path.strip():
        raise ExecutorInputError("Path must be a non-empty string")
    if not os.path.isfile(path):
        raise ExecutorInputError(f"File not found: {path}")

    with open(path) as handle:
        lines = [line.strip() for line in handle if line.strip()]

    if not lines:
        raise ExecutorInputError(f"Report is empty: {path}")
    return lines


# ---------------------------------------------------------------------------
# Function 2: map differences to Hadolint rule IDs
# ---------------------------------------------------------------------------


def map_differences_to_rules(reports, output_path="output/rule-mapping.txt"):
    """Task-3: determine which Hadolint rules the reported changes concern."""
    changed_terms = _extract_changed_terms(reports)

    if not changed_terms:
        _write_lines(output_path, [NO_DIFFERENCES_FOUND])
        return []

    rules = set()
    for term in changed_terms:
        lowered = term.lower()
        for keyword, rule_ids in KEYWORD_RULE_MAP.items():
            if keyword in lowered:
                rules.update(rule_ids)

    selected = sorted(rules)
    _write_lines(output_path, selected if selected else [NO_DIFFERENCES_FOUND])
    return selected


def _extract_changed_terms(reports):
    """Pull the element names out of both difference reports."""
    terms = []

    for line in reports.get("names", []):
        if line in NO_DIFFERENCE_MARKERS:
            continue
        for prefix in NAME_DIFF_PREFIXES:
            if line.startswith(prefix):
                terms.append(line[len(prefix):].strip())
                break

    for line in reports.get("requirements", []):
        if line in NO_DIFFERENCE_MARKERS:
            continue
        # Element names can contain commas, so split on the first one only.
        name, _, requirement = line.partition(",")
        terms.append(name.strip())
        terms.append(requirement.strip())

    return [term for term in terms if term]


# ---------------------------------------------------------------------------
# Function 3: run Hadolint
# ---------------------------------------------------------------------------


def run_hadolint(dockerfile_dir, rule_ids=None):
    """Task-3: run Hadolint over a directory and return findings as a DataFrame."""
    if not os.path.isdir(dockerfile_dir):
        raise ExecutorInputError(f"Directory not found: {dockerfile_dir}")

    paths = sorted(
        os.path.join(dockerfile_dir, name)
        for name in os.listdir(dockerfile_dir)
        if os.path.isfile(os.path.join(dockerfile_dir, name))
    )
    if not paths:
        raise ExecutorInputError(f"No Dockerfiles in: {dockerfile_dir}")

    command = ["hadolint", "--format", "json"] + paths
    completed = subprocess.run(command, capture_output=True, text=True)

    try:
        findings = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ExecutorInputError("Hadolint did not return valid JSON") from exc

    frame = pd.DataFrame(findings)
    if frame.empty:
        return pd.DataFrame(columns=["file", "code", "level", "line", "message"])

    if rule_ids:
        frame = frame[frame["code"].isin(rule_ids)]

    return frame.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Function 4: write the CSV
# ---------------------------------------------------------------------------


def write_findings_csv(frame, output_path="output/hadolint-findings.csv"):
    """Task-3: aggregate findings and write the required CSV."""
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    columns = ["FilePath", "DefaultSeverity", "RULEID", "COUNT"]

    if frame.empty:
        pd.DataFrame(columns=columns).to_csv(output_path, index=False)
        return output_path

    counted = (
        frame.groupby(["file", "level", "code"])
        .size()
        .reset_index(name="COUNT")
        .rename(
            columns={
                "file": "FilePath",
                "level": "DefaultSeverity",
                "code": "RULEID",
            }
        )
        .sort_values(["FilePath", "RULEID"])
    )

    counted[columns].to_csv(output_path, index=False)
    return output_path


def _write_lines(output_path, lines):
    """Write one entry per line to a TEXT file."""
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    return output_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_execution(
    name_diff_path,
    requirement_diff_path,
    dockerfile_dir,
    output_dir="output",
):
    """Map Task-2 differences to rules, scan Dockerfiles, write the CSV."""
    reports = load_difference_reports(name_diff_path, requirement_diff_path)
    rules = map_differences_to_rules(
        reports, os.path.join(output_dir, "rule-mapping.txt")
    )

    if rules:
        print(f"{len(rules)} rules selected from reported differences")
    else:
        print(f"{NO_DIFFERENCES_FOUND}, running all rules")

    frame = run_hadolint(dockerfile_dir, rule_ids=rules or None)
    csv_path = write_findings_csv(
        frame, os.path.join(output_dir, "hadolint-findings.csv")
    )

    print(f"{len(frame)} findings, wrote {csv_path}")
    return csv_path


if __name__ == "__main__":
    import sys

    name_path = sys.argv[1] if len(sys.argv) > 1 else "output/name-diff.txt"
    req_path = sys.argv[2] if len(sys.argv) > 2 else "output/requirement-diff.txt"
    docker_dir = sys.argv[3] if len(sys.argv) > 3 else "data/dockerfiles"

    run_execution(name_path, req_path, docker_dir)