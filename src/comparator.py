"""Task-2: Comparator.

Loads the two YAML files produced by Task-1 and reports differences in key
data element names and in the requirements attached to each element.
"""

import os

import yaml

NO_NAME_DIFFERENCES = "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES"
NO_REQUIREMENT_DIFFERENCES = (
    "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS"
)


class InvalidYAMLError(ValueError):
    """Raised when an input YAML file is missing or malformed."""


# ---------------------------------------------------------------------------
# Function 1: load the two YAML files
# ---------------------------------------------------------------------------


def load_kde_yaml_files(yaml_path_a, yaml_path_b):
    """Task-2: load and validate the two key data element YAML files."""
    return {
        "document_a": {"path": yaml_path_a, "kdes": _validated_yaml(yaml_path_a)},
        "document_b": {"path": yaml_path_b, "kdes": _validated_yaml(yaml_path_b)},
    }


def _validated_yaml(path):
    """Validate one YAML path and return its parsed element list."""
    if not isinstance(path, str) or not path.strip():
        raise InvalidYAMLError("Path must be a non-empty string")
    if not os.path.isfile(path):
        raise InvalidYAMLError(f"File not found: {path}")

    try:
        with open(path) as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise InvalidYAMLError(f"Malformed YAML: {path}") from exc

    if not isinstance(data, dict) or "elements" not in data:
        raise InvalidYAMLError(f"Missing 'elements' key: {path}")
    if not isinstance(data["elements"], list):
        raise InvalidYAMLError(f"'elements' is not a list: {path}")

    return data["elements"]


def _elements_by_name(elements):
    """Index elements by name, merging requirements for repeated names."""
    indexed = {}
    for element in elements:
        if not isinstance(element, dict) or not element.get("name"):
            continue
        name = str(element["name"]).strip()
        requirements = [str(r).strip() for r in element.get("requirements", [])]
        indexed.setdefault(name, set()).update(requirements)
    return indexed


# ---------------------------------------------------------------------------
# Function 2: compare element names
# ---------------------------------------------------------------------------


def compare_element_names(kdes_a, kdes_b, output_path="output/name-diff.txt"):
    """Task-2: report key data element names that differ between documents."""
    names_a = set(_elements_by_name(kdes_a))
    names_b = set(_elements_by_name(kdes_b))

    only_a = sorted(names_a - names_b)
    only_b = sorted(names_b - names_a)

    lines = []
    for name in only_a:
        lines.append(f"ONLY IN FIRST DOCUMENT,{name}")
    for name in only_b:
        lines.append(f"ONLY IN SECOND DOCUMENT,{name}")

    if not lines:
        lines = [NO_NAME_DIFFERENCES]

    _write_lines(output_path, lines)
    return lines


# ---------------------------------------------------------------------------
# Function 3: compare element requirements
# ---------------------------------------------------------------------------


def compare_element_requirements(
    kdes_a, kdes_b, output_path="output/requirement-diff.txt"
):
    """Task-2: report requirement differences for shared element names."""
    indexed_a = _elements_by_name(kdes_a)
    indexed_b = _elements_by_name(kdes_b)

    lines = []
    for name in sorted(set(indexed_a) & set(indexed_b)):
        requirements_a = indexed_a[name]
        requirements_b = indexed_b[name]
        for requirement in sorted(requirements_a - requirements_b):
            lines.append(f"{name},{requirement}")
        for requirement in sorted(requirements_b - requirements_a):
            lines.append(f"{name},{requirement}")

    if not lines:
        lines = [NO_REQUIREMENT_DIFFERENCES]

    _write_lines(output_path, lines)
    return lines


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


def run_comparison(yaml_path_a, yaml_path_b, output_dir="output"):
    """Load both YAMLs and write both difference reports."""
    documents = load_kde_yaml_files(yaml_path_a, yaml_path_b)
    kdes_a = documents["document_a"]["kdes"]
    kdes_b = documents["document_b"]["kdes"]

    name_path = os.path.join(output_dir, "name-diff.txt")
    requirement_path = os.path.join(output_dir, "requirement-diff.txt")

    name_lines = compare_element_names(kdes_a, kdes_b, name_path)
    requirement_lines = compare_element_requirements(
        kdes_a, kdes_b, requirement_path
    )

    print(f"wrote {name_path} with {len(name_lines)} lines")
    print(f"wrote {requirement_path} with {len(requirement_lines)} lines")
    return name_path, requirement_path


if __name__ == "__main__":
    import sys

    path_a = sys.argv[1] if len(sys.argv) > 1 else "output/docker-cis-v0-kdes.yaml"
    path_b = sys.argv[2] if len(sys.argv) > 2 else "output/docker-cis-v1-kdes.yaml"
    run_comparison(path_a, path_b)