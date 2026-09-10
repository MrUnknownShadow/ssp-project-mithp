"""Task-1: Extractor.

Reads two security requirements documents, splits them into recommendation
sections, and uses Gemma-3-1B to identify key data elements (KDEs) and the
requirements attached to each.
"""

import json
import logging
import os
import re

import torch
import yaml
from pypdf import PdfReader
from transformers import pipeline

CACHE_DIR = "cache"

logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

MODEL_NAME = "google/gemma-3-1b-it"
CANONICAL_PROMPT_TYPE = "chain-of-thought"

SECTION_PATTERN = re.compile(
    r"^(\d+\.\d+(?:\.\d+)*)\s+([A-Z].{0,200}?)\s*\((Manual|Automated)\)",
    re.MULTILINE | re.DOTALL,
)

JSON_INSTRUCTION = (
    "Respond with ONLY a JSON object, no markdown, no explanation. "
    'Format: {"elements": [{"name": "...", "requirements": ["...", "..."]}]}'
)


class InvalidInputError(ValueError):
    """Raised when an input document fails validation."""


# ---------------------------------------------------------------------------
# Function 1: input handling and validation
# ---------------------------------------------------------------------------


def load_input_documents(pdf_path_a, pdf_path_b):
    """Task-1: validate and load the two input requirements documents."""
    return {
        "document_a": {"path": pdf_path_a, "text": _validated_text(pdf_path_a)},
        "document_b": {"path": pdf_path_b, "text": _validated_text(pdf_path_b)},
    }


def _validated_text(pdf_path):
    """Validate one input path and return its extracted text."""
    if not isinstance(pdf_path, str) or not pdf_path.strip():
        raise InvalidInputError("Path must be a non-empty string")
    if not os.path.isfile(pdf_path):
        raise InvalidInputError(f"File not found: {pdf_path}")
    if not pdf_path.lower().endswith(".pdf"):
        raise InvalidInputError(f"Not a PDF: {pdf_path}")
    if os.path.getsize(pdf_path) == 0:
        raise InvalidInputError(f"File is empty: {pdf_path}")
    try:
        text = extract_pdf_text(pdf_path)
    except InvalidInputError:
        raise
    except Exception as exc:
        raise InvalidInputError(f"Could not read PDF: {pdf_path}") from exc
    if not text.strip():
        raise InvalidInputError(f"No extractable text in: {pdf_path}")
    return text


def extract_pdf_text(pdf_path):
    """Extract all text from a PDF as a single string."""
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def clean_title(raw):
    """Collapse line breaks and repeated whitespace in a wrapped heading."""
    return re.sub(r"\s+", " ", raw).strip()


def normalize_body(raw):
    """Trim trailing appendix content and repair wrap-joined words."""
    body = re.split(r"\n\s*Appendix:", raw)[0]
    body = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", body)
    return body.strip()


def deduplicate_sections(sections):
    """Drop table-of-contents matches by keeping the longest body per number."""
    best = {}
    for section in sections:
        number = section["number"]
        if number not in best or len(section["body"]) > len(best[number]["body"]):
            best[number] = section
    return sorted(
        best.values(), key=lambda s: [int(p) for p in s["number"].split(".")]
    )


def is_chapter_heading(section, all_sections):
    """A number is a chapter, not a recommendation, if children exist under it."""
    prefix = section["number"] + "."
    return any(s["number"].startswith(prefix) for s in all_sections)


def split_into_sections(text):
    """Split benchmark text into one entry per numbered recommendation."""
    matches = list(SECTION_PATTERN.finditer(text))
    sections = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(
            {
                "number": match.group(1),
                "title": clean_title(match.group(2)),
                "assessment": match.group(3),
                "body": normalize_body(text[start:end]),
            }
        )
    sections = deduplicate_sections(sections)
    return [s for s in sections if not is_chapter_heading(s, sections)]


# ---------------------------------------------------------------------------
# Functions 2-4: prompt construction
# ---------------------------------------------------------------------------


def build_zero_shot_prompt(section_text):
    """Task-1: construct a zero shot prompt for key data element extraction."""
    return (
        "You are analyzing a security requirements document.\n"
        "A key data element (KDE) is a specific configuration item, file, "
        "or system component that the document imposes requirements on.\n\n"
        "Identify the key data elements in the text below and list the "
        "requirements stated for each. List each element at most once.\n\n"
        f"TEXT:\n{section_text}\n\n"
        f"{JSON_INSTRUCTION}"
    )


def build_few_shot_prompt(section_text):
    """Task-1: construct a few shot prompt for key data element extraction."""
    return (
        "You are analyzing a security requirements document.\n"
        "Identify key data elements (KDEs) and their requirements.\n"
        "List each element at most once. Emit at most six elements.\n\n"
        "EXAMPLE 1\n"
        "TEXT: Ensure a separate partition for containers has been created. "
        "The /var/lib/docker directory should be mounted on a dedicated "
        "partition to avoid filling the host filesystem.\n"
        'OUTPUT: {"elements": [{"name": "/var/lib/docker", "requirements": '
        '["Must be mounted on a dedicated partition", '
        '"Must not share space with the host filesystem"]}]}\n\n'
        "EXAMPLE 2\n"
        "TEXT: Ensure the Docker daemon is not run as root where possible. "
        "Rootless mode should be enabled. The daemon socket must not be "
        "exposed over TCP without TLS.\n"
        'OUTPUT: {"elements": [{"name": "Docker daemon", "requirements": '
        '["Should run in rootless mode", "Must not expose the socket over '
        'TCP without TLS"]}]}\n\n'
        "NOW ANALYZE\n"
        f"TEXT: {section_text}\n"
        "OUTPUT: "
    )


def build_chain_of_thought_prompt(section_text):
    """Task-1: construct a chain of thought prompt for KDE extraction."""
    return (
        "You are analyzing a security requirements document.\n"
        "Work through these steps internally before answering:\n"
        "Step 1: Identify every file, directory, daemon, socket, or "
        "configuration setting named in the text.\n"
        "Step 2: For each one, find the sentences that state what it must, "
        "should, or must not do.\n"
        "Step 3: Discard items that are only mentioned as examples or "
        "references and impose no requirement.\n"
        "Step 4: Phrase each requirement as a short imperative statement.\n"
        "Step 5: Remove any duplicate elements.\n\n"
        f"TEXT:\n{section_text}\n\n"
        f"After reasoning through the steps, {JSON_INSTRUCTION}"
    )


PROMPT_BUILDERS = {
    "zero-shot": build_zero_shot_prompt,
    "few-shot": build_few_shot_prompt,
    "chain-of-thought": build_chain_of_thought_prompt,
}


# ---------------------------------------------------------------------------
# Function 5: LLM-driven key data element identification
# ---------------------------------------------------------------------------

_pipe = None


def get_pipeline():
    """Load Gemma once and reuse it across calls."""
    global _pipe
    if _pipe is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _pipe = pipeline(
            "text-generation",
            model=MODEL_NAME,
            dtype=torch.bfloat16,
            device=device,
        )
    return _pipe


def _salvage_elements(text):
    """Recover complete element objects from a truncated JSON array."""
    elements = []
    for match in re.finditer(
        r'\{\s*"name"\s*:\s*".*?"\s*,\s*"requirements"\s*:\s*\[.*?\]\s*\}',
        text,
        re.DOTALL,
    ):
        try:
            elements.append(json.loads(match.group(0)))
        except json.JSONDecodeError:
            continue
    return [e for e in elements if isinstance(e, dict) and e.get("name")]


def parse_llm_json(raw):
    """Pull elements out of a model response, tolerating truncated JSON."""
    start = raw.find("{")
    if start == -1:
        return {"elements": []}

    candidate = raw[start:]
    end = candidate.rfind("}")
    if end != -1:
        try:
            parsed = json.loads(candidate[: end + 1])
            if isinstance(parsed, dict):
                elements = parsed.get("elements", [])
                if isinstance(elements, list) and elements:
                    return {"elements": elements}
        except json.JSONDecodeError:
            pass

    return {"elements": _salvage_elements(candidate)}


def _cache_path(pdf_path, prompt_type, limit):
    """Build a cache filename keyed by document, prompt type, and limit."""
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    suffix = f"-{limit}" if limit else ""
    return os.path.join(CACHE_DIR, f"{stem}-{prompt_type}{suffix}.json")


def load_or_extract(pdf_path, sections, prompt_type, limit=None, log=None):
    """Return cached extraction results, or run the LLM and cache them."""
    path = _cache_path(pdf_path, prompt_type, limit)

    if os.path.isfile(path):
        with open(path) as handle:
            cached = json.load(handle)
        if log is not None:
            log.extend(cached.get("log", []))
        print(f"    cached: {len(cached['result']['elements'])} elements")
        return cached["result"]

    call_log = []
    result = identify_key_data_elements(
        sections, prompt_type, limit=limit, log=call_log
    )

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as handle:
        json.dump({"result": result, "log": call_log}, handle)

    if log is not None:
        log.extend(call_log)
    return result




def identify_key_data_elements(sections, prompt_type, limit=None, log=None):
    """Task-1: run each section through Gemma and collect key data elements."""
    if prompt_type not in PROMPT_BUILDERS:
        raise ValueError(f"Unknown prompt type: {prompt_type}")

    build = PROMPT_BUILDERS[prompt_type]
    pipe = get_pipeline()
    targets = sections[:limit] if limit else sections
    elements = []

    for i, section in enumerate(targets, 1):
        prompt = build(section["body"])
        result = pipe(
            [{"role": "user", "content": prompt}],
            max_new_tokens=400,
            do_sample=False,
            max_length=None,
            repetition_penalty=1.15,
        )
        raw = result[0]["generated_text"][-1]["content"]

        if log is not None:
            log.append(
                {
                    "llm": MODEL_NAME,
                    "prompt": prompt,
                    "prompt_type": prompt_type,
                    "output": raw,
                }
            )

        seen = set()
        for element in parse_llm_json(raw)["elements"]:
            if not isinstance(element, dict) or not element.get("name"):
                continue
            name = str(element["name"]).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            elements.append(
                {
                    "name": name,
                    "requirements": [
                        str(r) for r in element.get("requirements", [])
                    ],
                    "section": section["number"],
                }
            )

        print(f"    [{i}/{len(targets)}] {section['number']}: {len(elements)} elements")

    return {"elements": elements}


# ---------------------------------------------------------------------------
# Function 6: output writers
# ---------------------------------------------------------------------------


def write_kdes_yaml(kdes, pdf_path, output_dir="output"):
    """Task-1: dump extracted key data elements to a named YAML file."""
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    path = os.path.join(output_dir, f"{stem}-kdes.yaml")
    with open(path, "w") as handle:
        yaml.safe_dump(kdes, handle, sort_keys=False, default_flow_style=False)
    return path


def write_llm_log(log, output_path="output/llm-output.txt"):
    """Task-1: dump every LLM interaction in the required TEXT format."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as handle:
        for entry in log:
            handle.write("*LLM Name*\n")
            handle.write(f"{entry['llm']}\n")
            handle.write("*Prompt Used*\n")
            handle.write(f"{entry['prompt']}\n")
            handle.write("*Prompt Type*\n")
            handle.write(f"{entry['prompt_type']}\n")
            handle.write("*LLM Output*\n")
            handle.write(f"{entry['output']}\n\n")
    return output_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_extraction(pdf_path_a, pdf_path_b, limit=None):
    """Run all three prompt types over both documents and write deliverables."""
    documents = load_input_documents(pdf_path_a, pdf_path_b)
    log = []
    yaml_paths = []

    for doc in documents.values():
        sections = split_into_sections(doc["text"])
        print(f"\n{doc['path']}: {len(sections)} sections")
        canonical = {"elements": []}

        for prompt_type in PROMPT_BUILDERS:
            print(f"  {prompt_type}")
            result = load_or_extract(
                doc["path"], sections, prompt_type, limit=limit, log=log
            )
            if prompt_type == CANONICAL_PROMPT_TYPE:
                canonical = result

        path = write_kdes_yaml(canonical, doc["path"])
        yaml_paths.append(path)
        print(f"  wrote {path} with {len(canonical['elements'])} elements")

    txt_path = write_llm_log(log)
    print(f"\nwrote {txt_path} with {len(log)} interactions")
    return yaml_paths, txt_path


if __name__ == "__main__":
    import sys

    path_a = sys.argv[1] if len(sys.argv) > 1 else "data/docker-cis-v0.pdf"
    path_b = sys.argv[2] if len(sys.argv) > 2 else "data/docker-cis-v1.pdf"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    run_extraction(path_a, path_b, limit=limit)