"""Task-3 test cases: one per required executor function."""

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import executor


NAME_LINES = [
    "ONLY IN FIRST DOCUMENT,Docker daemon user",
    "ONLY IN SECOND DOCUMENT,Base image version tag",
]

REQUIREMENT_LINES = [
    "Access Control Lists (ACL), must pin package versions",
]


def _write(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
    return str(path)


# Function 1: read the Task-2 difference reports
def test_load_difference_reports_validates_and_reads(tmp_path):
    name_path = _write(tmp_path, "name-diff.txt", NAME_LINES)
    req_path = _write(tmp_path, "requirement-diff.txt", REQUIREMENT_LINES)

    reports = executor.load_difference_reports(name_path, req_path)
    assert len(reports["names"]) == 2
    assert len(reports["requirements"]) == 1

    with pytest.raises(executor.ExecutorInputError):
        executor.load_difference_reports("missing.txt", req_path)

    empty = _write(tmp_path, "empty.txt", [])
    with pytest.raises(executor.ExecutorInputError):
        executor.load_difference_reports(empty, req_path)


# Function 2: map differences to Hadolint rule IDs
def test_map_differences_to_rules_selects_and_writes(tmp_path):
    reports = {"names": NAME_LINES, "requirements": REQUIREMENT_LINES}
    output = str(tmp_path / "rule-mapping.txt")

    rules = executor.map_differences_to_rules(reports, output)
    assert "DL3002" in rules
    assert "DL3007" in rules
    assert rules == sorted(set(rules))
    assert "DL3002" in open(output).read()

    # Element names containing commas must not be split apart.
    assert any("ACL" not in rule for rule in rules)

    no_diff = {
        "names": ["NO DIFFERENCES IN REGARDS TO ELEMENT NAMES"],
        "requirements": ["NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS"],
    }
    empty_output = str(tmp_path / "none.txt")
    assert executor.map_differences_to_rules(no_diff, empty_output) == []
    assert executor.NO_DIFFERENCES_FOUND in open(empty_output).read()


# Function 3: run Hadolint
def test_run_hadolint_returns_filtered_dataframe(tmp_path):
    dockerfile_dir = tmp_path / "dockerfiles"
    dockerfile_dir.mkdir()
    (dockerfile_dir / "Dockerfile").write_text("FROM ubuntu:latest\nUSER root\n")

    fake_output = (
        '[{"code":"DL3007","file":"Dockerfile","level":"warning",'
        '"line":1,"message":"x"},'
        '{"code":"DL3002","file":"Dockerfile","level":"warning",'
        '"line":2,"message":"y"}]'
    )

    class FakeCompleted:
        stdout = fake_output
        stderr = ""
        returncode = 1

    with patch.object(executor.subprocess, "run", return_value=FakeCompleted()):
        frame = executor.run_hadolint(str(dockerfile_dir))
        assert len(frame) == 2

        filtered = executor.run_hadolint(str(dockerfile_dir), rule_ids=["DL3002"])
        assert len(filtered) == 1
        assert filtered.iloc[0]["code"] == "DL3002"

    with pytest.raises(executor.ExecutorInputError):
        executor.run_hadolint(str(tmp_path / "does-not-exist"))


# Function 4: write the CSV
def test_write_findings_csv_aggregates_counts(tmp_path):
    frame = pd.DataFrame(
        [
            {"file": "a/Dockerfile", "code": "DL3007", "level": "warning", "line": 1},
            {"file": "a/Dockerfile", "code": "DL3007", "level": "warning", "line": 9},
            {"file": "b/Dockerfile", "code": "DL3002", "level": "warning", "line": 3},
        ]
    )

    output = str(tmp_path / "findings.csv")
    executor.write_findings_csv(frame, output)

    result = pd.read_csv(output)
    assert list(result.columns) == [
        "FilePath",
        "DefaultSeverity",
        "RULEID",
        "COUNT",
    ]
    repeated = result[result["RULEID"] == "DL3007"]
    assert repeated.iloc[0]["COUNT"] == 2

    empty_output = str(tmp_path / "empty.csv")
    executor.write_findings_csv(pd.DataFrame(), empty_output)
    assert list(pd.read_csv(empty_output).columns) == [
        "FilePath",
        "DefaultSeverity",
        "RULEID",
        "COUNT",
    ]