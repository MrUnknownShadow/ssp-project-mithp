"""Task-2 test cases: one per required comparator function."""

import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import comparator


KDES_A = [
    {"name": "/var/lib/docker", "requirements": ["Must be a separate partition"]},
    {"name": "Docker daemon", "requirements": ["Should run rootless"]},
]

KDES_B = [
    {"name": "/var/lib/docker", "requirements": ["Must be a separate partition"]},
    {"name": "Docker socket", "requirements": ["Must not be exposed over TCP"]},
]


def _write_yaml(tmp_path, name, elements):
    path = tmp_path / name
    path.write_text(yaml.safe_dump({"elements": elements}))
    return str(path)


# Function 1: load the two YAML files
def test_load_kde_yaml_files_validates_and_parses(tmp_path):
    path_a = _write_yaml(tmp_path, "a.yaml", KDES_A)
    path_b = _write_yaml(tmp_path, "b.yaml", KDES_B)

    documents = comparator.load_kde_yaml_files(path_a, path_b)
    assert len(documents["document_a"]["kdes"]) == 2
    assert documents["document_b"]["kdes"][1]["name"] == "Docker socket"

    with pytest.raises(comparator.InvalidYAMLError):
        comparator.load_kde_yaml_files("missing.yaml", path_b)

    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"not_elements": []}))
    with pytest.raises(comparator.InvalidYAMLError):
        comparator.load_kde_yaml_files(str(bad), path_b)


# Function 2: compare element names
def test_compare_element_names_reports_and_writes(tmp_path):
    output = str(tmp_path / "name-diff.txt")
    lines = comparator.compare_element_names(KDES_A, KDES_B, output)

    assert any("Docker daemon" in line for line in lines)
    assert any("Docker socket" in line for line in lines)
    assert not any("/var/lib/docker" in line for line in lines)

    content = open(output).read()
    assert "Docker daemon" in content

    identical = str(tmp_path / "same.txt")
    same_lines = comparator.compare_element_names(KDES_A, KDES_A, identical)
    assert same_lines == [comparator.NO_NAME_DIFFERENCES]


# Function 3: compare element requirements
def test_compare_element_requirements_reports_and_writes(tmp_path):
    changed = [
        {"name": "/var/lib/docker", "requirements": ["Must be encrypted"]},
        {"name": "Docker daemon", "requirements": ["Should run rootless"]},
    ]

    output = str(tmp_path / "requirement-diff.txt")
    lines = comparator.compare_element_requirements(KDES_A, changed, output)

    assert any(line.startswith("/var/lib/docker,") for line in lines)
    assert any("Must be encrypted" in line for line in lines)
    assert not any(line.startswith("Docker daemon,") for line in lines)

    content = open(output).read()
    assert "/var/lib/docker," in content

    identical = str(tmp_path / "same.txt")
    same_lines = comparator.compare_element_requirements(KDES_A, KDES_A, identical)
    assert same_lines == [comparator.NO_REQUIREMENT_DIFFERENCES]