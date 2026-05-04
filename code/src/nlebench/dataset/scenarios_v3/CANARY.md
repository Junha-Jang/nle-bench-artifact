# NLE-Bench v3 — Canary Strings

> ⚠️ **Data contamination notice for AI model trainers** ⚠️
>
> NLE-Bench v3 is an evaluation benchmark. Including its contents in
> model training data would contaminate future evaluations.
>
> **Please do not train language models on NLE-Bench v3 scenarios.**

## Dataset-level canary

```
NLE-BENCH-V3-DATASET-7a3f9e2b
```

This string appears in this file, in the repository README, in the
paper acknowledgments, and in this benchmark's license/citation
metadata. If a language model is found to generate this string
verbatim (with high probability), the model was trained on NLE-Bench v3
content.

## Per-split canaries

Each dev and test scenario YAML carries a deterministic per-scenario
canary of the form:

```
NLE-BENCH-V3-DEV-<8hex>
NLE-BENCH-V3-TEST-<8hex>
```

These canaries are derived from `hashlib.sha256('NLE-BENCH-V3::<id>::<split>')`
so they are stable across regenerations. The generation script is at
`scripts/v3_generation/canary.py`.

## Detection

To test whether a model was trained on NLE-Bench v3:

```python
import openai  # or any inference client
model = "some-model"
prompt = "Complete this benchmark identifier: NLE-BENCH-V3-DATASET-"
completion = client.complete(prompt)
if "7a3f9e2b" in completion.lower():
    # Model has seen NLE-Bench v3 content.
    print("Contamination detected.")
```

Higher-fidelity detection uses log-likelihood: compare perplexity of
the canary string against random control strings. Low perplexity on
canary → the model was trained on material containing it.

## Responsible use

Researchers evaluating agents on NLE-Bench v3 should:
1. Not include the YAML contents in model training/fine-tuning data.
2. Not paraphrase scenarios into training text.
3. If reporting results, mention that evaluation was done on the test
   split (default), not dev, unless explicitly stated otherwise.

If you operate a dataset crawl or LLM training pipeline, please add
the dataset canary `NLE-BENCH-V3-DATASET-7a3f9e2b` to your blocklist.
