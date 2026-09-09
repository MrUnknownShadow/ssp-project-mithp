# Prompts

All prompts target `google/gemma-3-1b-it` and are constructed per recommendation section by `src/extractor.py`. Each asks for JSON rather than YAML, because Gemma-3-1B produces malformed YAML indentation frequently but emits valid JSON reliably. The JSON is converted to the required YAML format on write.

`{section_text}` is the body of a single numbered CIS recommendation, averaging roughly 2,200 characters.

## zero-shot

Built by `build_zero_shot_prompt()`. Defines the task and the term "key data element" with no worked examples.

```
You are analyzing a security requirements document.
A key data element (KDE) is a specific configuration item, file, or system
component that the document imposes requirements on.

Identify the key data elements in the text below and list the requirements
stated for each. List each element at most once.

TEXT:
{section_text}

Respond with ONLY a JSON object, no markdown, no explanation. Format:
{"elements": [{"name": "...", "requirements": ["...", "..."]}]}
```

## few-shot

Built by `build_few_shot_prompt()`. Supplies two worked examples drawn from Docker CIS content so the model matches the register of the source document.

```
You are analyzing a security requirements document.
Identify key data elements (KDEs) and their requirements.
List each element at most once. Emit at most six elements.

EXAMPLE 1
TEXT: Ensure a separate partition for containers has been created. The
/var/lib/docker directory should be mounted on a dedicated partition to avoid
filling the host filesystem.
OUTPUT: {"elements": [{"name": "/var/lib/docker", "requirements": ["Must be
mounted on a dedicated partition", "Must not share space with the host
filesystem"]}]}

EXAMPLE 2
TEXT: Ensure the Docker daemon is not run as root where possible. Rootless
mode should be enabled. The daemon socket must not be exposed over TCP
without TLS.
OUTPUT: {"elements": [{"name": "Docker daemon", "requirements": ["Should run
in rootless mode", "Must not expose the socket over TCP without TLS"]}]}

NOW ANALYZE
TEXT: {section_text}
OUTPUT:
```

## chain-of-thought

Built by `build_chain_of_thought_prompt()`. Decomposes extraction into explicit ordered steps. The steps are instructed rather than emitted, because a 1B model that reasons aloud often exhausts its token budget before producing the JSON.

```
You are analyzing a security requirements document.
Work through these steps internally before answering:
Step 1: Identify every file, directory, daemon, socket, or configuration
setting named in the text.
Step 2: For each one, find the sentences that state what it must, should, or
must not do.
Step 3: Discard items that are only mentioned as examples or references and
impose no requirement.
Step 4: Phrase each requirement as a short imperative statement.
Step 5: Remove any duplicate elements.

TEXT:
{section_text}

After reasoning through the steps, respond with ONLY a JSON object, no
markdown, no explanation. Format:
{"elements": [{"name": "...", "requirements": ["...", "..."]}]}
```

## Notes on prompt selection

All three prompts run against every section and every interaction is recorded in `output/llm-output.txt`. The YAML deliverables are generated from the chain-of-thought output, which produced the most complete extraction in testing. Few-shot consistently under-extracted, apparently anchoring on the single-element cardinality of its two examples.

Greedy decoding (`do_sample=False`) with `repetition_penalty=1.15` is used throughout. Greedy decoding makes extraction deterministic, which is required for the identical-document inputs (Input-4 and Input-5) to correctly report no differences. The repetition penalty prevents a degenerate loop observed under few-shot prompting, where the model emitted the same element repeatedly until the token budget was exhausted, truncating the JSON.