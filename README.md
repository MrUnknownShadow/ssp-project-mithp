# SSP Project: Security Requirements Change Detection

Detects changes between two security requirements documents (Docker CIS
Benchmarks) and runs Hadolint static analysis scoped to the changes found.

COMP 5700/6700, Secure Software Process, Fall 2026, Auburn University.

## Team


| Name       | Banner ID | Email                                           |
| ---------- | --------- | ----------------------------------------------- |
| Mith Patel | 904294756 | [mdp0068@auburn.edu](mailto:mdp0068@auburn.edu) |


## LLM Used

Task-1 uses **Gemma-3-1B** (`google/gemma-3-1b-it`, instruction tuned) through
the Hugging Face `transformers` library.

## What it does


| Task | Module              | Output                                                                                                                                                             |
| ---- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | `src/extractor.py`  | Splits each PDF into numbered CIS recommendations, runs three prompt types through Gemma, writes key data elements to YAML and every LLM interaction to a TEXT log |
| 2    | `src/comparator.py` | Diffs the two YAML files, writes element-name differences and element-requirement differences to TEXT files                                                        |
| 3    | `src/executor.py`   | Maps the reported differences to Hadolint rule IDs, scans a directory of Dockerfiles, writes findings to CSV                                                       |




## Setup

```
python3 -m venv comp5700-venv
source comp5700-venv/bin/activate
pip install -r requirements.txt
```



### Hugging Face access

Gemma-3-1B is a gated model. Accept the license at
[https://huggingface.co/google/gemma-3-1b-it](https://huggingface.co/google/gemma-3-1b-it) while signed in, then
authenticate:

```
hf auth login
```

Without this, Task-1 fails with a 403 on the first model download.

### Hadolint

Hadolint is a standalone binary, not a Python package:

```
brew install hadolint          # macOS
```

On Linux, download the release binary from
[https://github.com/hadolint/hadolint/releases](https://github.com/hadolint/hadolint/releases) and make it executable.

## Usage

Run the full pipeline over a pair of documents:

```
python3 src/main.py data/docker-cis-v0.pdf data/docker-cis-v1.pdf
```

Options:

```
--dockerfiles DIR    directory of Dockerfiles to scan (default: data/dockerfiles)
--output-dir DIR     where to write generated files (default: output)
--limit N            process only the first N sections per document
```

Individual tasks can also be run on their own:

```
python3 src/extractor.py  data/docker-cis-v0.pdf data/docker-cis-v1.pdf
python3 src/comparator.py output/docker-cis-v0-kdes.yaml output/docker-cis-v1-kdes.yaml
python3 src/executor.py   output/name-diff.txt output/requirement-diff.txt data/dockerfiles
```



## Generated files


| File                           | Task | Contents                                                                                             |
| ------------------------------ | ---- | ---------------------------------------------------------------------------------------------------- |
| `output/<document>-kdes.yaml`  | 1    | Key data elements and their requirements, one file per input document                                |
| `output/llm-output.txt`        | 1    | Every LLM interaction, formatted with `*LLM Name*`, `*Prompt Used*`, `*Prompt Type*`, `*LLM Output*` |
| `output/name-diff.txt`         | 2    | Element names present in only one document, or `NO DIFFERENCES IN REGARDS TO ELEMENT NAMES`          |
| `output/requirement-diff.txt`  | 2    | `NAME,REQU` tuples for changed requirements, or `NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS`  |
| `output/rule-mapping.txt`      | 3    | Hadolint rule IDs selected from the reported differences, or `NO DIFFERENCES FOUND`                  |
| `output/hadolint-findings.csv` | 3    | `FilePath`, `DefaultSeverity`, `RULEID`, `COUNT`                                                     |




## Caching

Extraction results are cached in `cache/`, keyed by document and prompt type.
Because the five graded input pairs reference only three distinct documents,
caching avoids re-running the model on a document already processed. Delete
`cache/` to force a fresh extraction.

## Design notes

**Section-based chunking.** The benchmarks run roughly 300 pages, about 85,000
tokens each, well beyond Gemma-3-1B's context window. The extractor splits each
document on its numbered recommendation headings (`1.1.1`, `2.3`, and so on),
giving around 116 sections averaging 2,200 characters, each of which fits
comfortably in a single prompt.

**JSON, not YAML, from the model.** All three prompts request JSON. Gemma-3-1B
produces malformed YAML indentation frequently but emits valid JSON reliably.
The JSON is converted to the required YAML format on write.

**Deterministic generation.** Greedy decoding (`do_sample=False`) makes
extraction reproducible, which is required for the identical-document inputs
(v1 vs v1, v2 vs v2) to correctly report no differences. A repetition penalty
of 1.15 prevents a degenerate loop in which the model emitted the same element
repeatedly until the token budget ran out.

**Canonical prompt type.** All three prompt types run over every section and
all interactions are logged, but the YAML deliverables are generated from
chain-of-thought output, which extracted substantially more elements than
zero-shot or few-shot in testing.

**Diff interpretation.** Differences reported by Task-2 reflect both genuine
changes between benchmark versions and variation in how the model phrases the
same concept across documents. The latter is inherent to LLM-based extraction
from unstructured text.

## Tests

Thirteen test cases, one per required function:

```
pytest tests/ -v
```

The Task-1 LLM test mocks the `transformers` pipeline, and `torch` and
`transformers` are imported lazily, so the suite runs without downloading model
weights or authenticating to Hugging Face. Tests run automatically on every
push and pull request via GitHub Actions (`.github/workflows/tests.yml`).

## Repository layout

```
src/extractor.py       Task-1: PDF parsing, prompting, KDE extraction
src/comparator.py      Task-2: YAML loading and difference reporting
src/executor.py        Task-3: rule mapping, Hadolint, CSV output
src/main.py            CLI entry point for the full pipeline
tests/                 13 test cases
data/                  Input PDFs and Dockerfiles
output/                Generated deliverables
cache/                 Cached extraction results
PROMPT.md              The three prompt templates
```

