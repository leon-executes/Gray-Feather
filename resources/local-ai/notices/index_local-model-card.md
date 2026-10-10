---
base_model: IndexTeam/Index-Translate-2B
library_name: llama.cpp
tags:
- gguf
- translation
- index
license: apache-2.0
---

# Index-Translate-2B-GGUF

Official GGUF conversion of [IndexTeam/Index-Translate-2B](https://huggingface.co/IndexTeam/Index-Translate-2B), part of the **Index-Translate** multilingual translation model family (150 languages, terminology/format-constrained translation, controlled dubbing translation, long-document translation).

- Technical report: [Index-Translate: A Multilingual Translation Model Family](https://arxiv.org/abs/2609.40181)
- Code: [github.com/bilibili/Index-Translate](https://github.com/bilibili/Index-Translate)
- Converted with [llama.cpp](https://github.com/ggml-org/llama.cpp) (master, 2026-10); static post-training quantization, all bit-widths in this single repository.

## Provided files

(sorted by size)

| File | Size | Notes |
|:-----|-----:|:------|
| [mmproj-Q8_0](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.mmproj-Q8_0.gguf) | 0.36 GB | multi-modal projector supplement |
| [mmproj-f16](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.mmproj-f16.gguf) | 0.67 GB | multi-modal projector supplement |
| [Q2_K](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q2_K.gguf) | 0.99 GB | 2-bit, significant quality loss |
| [Q3_K_S](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q3_K_S.gguf) | 1.05 GB | 3-bit, noticeable quality loss |
| [Q3_K_M](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q3_K_M.gguf) | 1.13 GB | 3-bit, noticeable quality loss |
| [Q3_K_L](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q3_K_L.gguf) | 1.20 GB | 3-bit, noticeable quality loss |
| [IQ4_XS](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.IQ4_XS.gguf) | 1.23 GB | 4-bit I-quant, small |
| [Q4_K_S](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q4_K_S.gguf) | 1.25 GB | 4-bit, slightly smaller/faster |
| [Q4_K_M](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q4_K_M.gguf) | 1.31 GB | 4-bit, good balance, recommended |
| [Q5_K_S](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q5_K_S.gguf) | 1.42 GB | 5-bit, low quality loss |
| [Q5_K_M](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q5_K_M.gguf) | 1.45 GB | 5-bit, low quality loss |
| [Q6_K](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q6_K.gguf) | 1.61 GB | 6-bit, very low quality loss |
| [Q8_0](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.Q8_0.gguf) | 2.08 GB | 8-bit, near-lossless |
| [f16](https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/resolve/main/Index-Translate-2B.f16.gguf) | 3.90 GB | 16-bit, lossless conversion baseline |

The `mmproj` files are the multi-modal projector for the vision tower; they are only needed for image-input use with `llama-mtmd-cli`. For text-only translation, the plain GGUF files suffice.

## Usage

```bash
# Run the recommended Q4_K_M directly:
llama serve -hf IndexTeam/Index-Translate-2B-GGUF:Q4_K_M
llama cli -hf IndexTeam/Index-Translate-2B-GGUF:Q4_K_M
```

Translation prompt format (greedy decoding, temperature=0 recommended; use the chat template with `enable_thinking: false`):

```text
请将以下文本翻译为{target-language}，直接输出翻译结果，不要进行任何解释。

{source-text}
```

```bash
# llama.cpp: run the recommended Q4_K_M with the chat template and thinking disabled
llama-cli -hf IndexTeam/Index-Translate-2B-GGUF:Q4_K_M --jinja --chat-template-kwargs '{"enable_thinking":false}' --temp 0
```

## Prompting & constrained translation (instTrans)

Beyond plain translation, the models follow the **instTrans** constrained-translation format. The official client wraps requests into the canonical structure `【源文】<text>` + numbered `1. 【硬性要求】<hard constraints>` + `2. 【注意】<soft constraints>` + suffix instructions:

- **Hard constraints** (binary, must hold): strict terminology glossary enforcement (e.g. `碳纤维:carbon fiber, 抗裂缝:crack resistance`), and format/structure preservation for JSON/CSV/code/placeholders.
- **Soft constraints** (graded): tone & style adaptation (e.g. formal business-email register), domain/word-sense disambiguation (e.g. *plant* → 工厂 in an industrial context), cross-sentence consistency, LaTeX preservation.
- **Syllable-controlled translation** (dubbing): use the Index-Homura checkpoints ([IndexTeam/Index-Homura-2B/9B](https://huggingface.co/IndexTeam/Index-Homura-2B)), which strictly respect a target syllable budget and can be combined with glossaries.

Full prompt reference: [github.com/bilibili/Index-Translate](https://github.com/bilibili/Index-Translate) (Instruction Following section, `docs/prompts.md`, `inference/llm/cases/`).

See the [base model card](https://huggingface.co/IndexTeam/Index-Translate-2B) for the full instTrans constrained-translation format and serving presets.

## Consistency validation

Before release, each quantization tier was validated on GPU (NVIDIA A100) against the F16 conversion: per-token KL divergence / RMS Δp via `llama-perplexity`, plus greedy-generation spot checks against the original BF16 weights (transformers reference). Generation outputs of Q4_K_M matched the reference almost verbatim.

*Converted and published by the Index team, 2026-10-03.*
