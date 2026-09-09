"""Task-1 test cases: one per required extractor function."""

import os
import sys
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import extractor


SAMPLE_SECTION = """1.1.1 Ensure a separate partition for containers has been created (Automated)
Profile Applicability:
Level 1 - Docker - Linux
Description:
All Docker containers are stored under /var/lib/docker.
Remediation:
Create a separate partition for /var/lib/docker.

1.1.2 Ensure only trusted users control Docker daemon (Automated)
Description:
The Docker daemon requires access to the Docker socket.
"""


# Function 1: input handling and validation
def test_load_input_documents_rejects_invalid_input():
    with pytest.raises(extractor.InvalidInputError):
        extractor.load_input_documents("does-not-exist.pdf", "also-missing.pdf")

    with pytest.raises(extractor.InvalidInputError):
        extractor.load_input_documents("", "")

    with pytest.raises(extractor.InvalidInputError):
        extractor.load_input_documents("README.md", "README.md")


# Function 2: zero shot prompt construction
def test_build_zero_shot_prompt_returns_string_with_text():
    prompt = extractor.build_zero_shot_prompt("Sample requirement text.")
    assert isinstance(prompt, str)
    assert "Sample requirement text." in prompt
    assert "JSON" in prompt
    assert "EXAMPLE" not in prompt


# Function 3: few shot prompt construction
def test_build_few_shot_prompt_includes_examples():
    prompt = extractor.build_few_shot_prompt("Sample requirement text.")
    assert isinstance(prompt, str)
    assert "Sample requirement text." in prompt
    assert prompt.count("EXAMPLE") >= 2
    assert "/var/lib/docker" in prompt


# Function 4: chain of thought prompt construction
def test_build_chain_of_thought_prompt_includes_steps():
    prompt = extractor.build_chain_of_thought_prompt("Sample requirement text.")
    assert isinstance(prompt, str)
    assert "Sample requirement text." in prompt
    assert "Step 1" in prompt
    assert "Step 4" in prompt


# Function 5: LLM-driven key data element identification
def test_identify_key_data_elements_builds_nested_structure():
    sections = extractor.split_into_sections(SAMPLE_SECTION)
    assert len(sections) == 2

    fake_response = [
        {
            "generated_text": [
                {"role": "user", "content": "..."},
                {
                    "role": "assistant",
                    "content": '{"elements": [{"name": "/var/lib/docker", '
                    '"requirements": ["Must be on a separate partition"]}]}',
                },
            ]
        }
    ]

    log = []
    with patch.object(extractor, "get_pipeline", return_value=lambda *a, **k: fake_response):
        result = extractor.identify_key_data_elements(
            sections, "zero-shot", log=log
        )

    assert "elements" in result
    assert len(result["elements"]) == 2
    first = result["elements"][0]
    assert first["name"] == "/var/lib/docker"
    assert first["requirements"] == ["Must be on a separate partition"]
    assert first["section"] == "1.1.1"
    assert len(log) == 2

    with pytest.raises(ValueError):
        extractor.identify_key_data_elements(sections, "not-a-prompt-type")


# Function 6: output writers
def test_write_outputs_produce_expected_files(tmp_path):
    kdes = {
        "elements": [
            {
                "name": "Docker daemon",
                "requirements": ["Should run rootless"],
                "section": "2.1",
            }
        ]
    }

    yaml_path = extractor.write_kdes_yaml(
        kdes, "data/docker-cis-v0.pdf", output_dir=str(tmp_path)
    )
    assert os.path.basename(yaml_path) == "docker-cis-v0-kdes.yaml"
    with open(yaml_path) as handle:
        loaded = yaml.safe_load(handle)
    assert loaded["elements"][0]["name"] == "Docker daemon"

    log = [
        {
            "llm": extractor.MODEL_NAME,
            "prompt": "some prompt",
            "prompt_type": "zero-shot",
            "output": "some output",
        }
    ]
    txt_path = extractor.write_llm_log(log, str(tmp_path / "llm-output.txt"))
    content = open(txt_path).read()
    for header in ("*LLM Name*", "*Prompt Used*", "*Prompt Type*", "*LLM Output*"):
        assert header in content