---
name: Candle embedding-layer hook for v0.4.13 latent loop
description: Research findings 2026-04-18 — candle exposes forward_input_embed; mistral.rs abstracts it away; use candle directly + target model's own embed layer to sidestep projection training.
type: reference
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
Research done 2026-04-18 before committing to an inference engine for the v0.4.13 latent-loop probe.

## Verified

- **`rustformers/llm` is archived.** Its own README recommends candle / mistral.rs / ratchet as successors. Don't use `llm`.
- **mistral.rs is built on candle.** Its README credits Candle directly: *"This project would not be possible without the excellent work at Candle."* Public API is token-only (request structs, builders — no `input_embeds` / `prompt_embeds` / `virtual_tokens` surface).
- **candle-transformers `llama.rs` exposes `forward_input_embed`:**
  ```rust
  pub fn forward_input_embed(
      &self,
      input_embed: &Tensor,
      index_pos: usize,
      cache: &mut Cache,
  ) -> Result<Tensor>
  ```
  Call `self.embed(tokens)` to get token embeddings, concat/splice with your own vectors, pass to `forward_input_embed`. No re-embedding. This is the exact soft-prompt-prefix hook.

**Decision:** v0.4.13 latent path is **candle direct**, not mistral.rs. mistral.rs is fine for production inference *without* injection, but dropping into `mistralrs-core` internals to patch the hook in is more cost than benefit for a probe.

## Answers to the 8 pre-work checks

1. **Dim match.** Projection (e.g. 768→4096) is a trained matrix (~3M params). Sidestep entirely: use the target LLM's own `tok_embeddings` layer to embed a short text summary per node, pool. Dim is 4096 by construction.
2. **Soft prompt vs replacement.** Both work on candle. You own the `[B, T, D]` tensor — concat prepends, splice replaces.
3. **RoPE.** Qwen 2.5 Coder 7B is Llama-shaped with RoPE. Safe for soft-prompt prefix.
4. **Stability / 30% blend.** Soft prior from the vector-translation paper, not a law. Perplexity-test empirically: inject N vectors, generate 100 tokens, compare vs no-injection baseline. Gate on the delta.
5. **API surface.** candle direct. mistral.rs's public API won't get you there.
6. **Embedding model choice.** Use the target LLM's own embedding layer to produce node embeddings — eliminates projection training + dim alignment in one move. User's own intuition (point 6 of their checklist) was correct.
7. **Context budget.** Qwen 2.5 Coder 7B: 32k native, 128k YaRN. 100–200 virtual tokens negligible.
8. **Quantisation.** GGUF keeps `token_embd.weight` at Q8_0 even for Q4 models (llama.cpp default). Candle dequantises-on-read → inject f16 into the resulting f16 tile is fine. Avoid AWQ/GPTQ for the probe — embeddings may be INT4 there.

## Implication for roadmap

- v0.4.13 probe stack: candle (injection path) + Qwen 2.5 Coder 7B (GGUF Q4_K_M or Q5_K_M, embeddings stay Q8_0) + `forward_input_embed` + target-model-own-embeddings for node vectors.
- No projection-layer training required for the probe.
- mistral.rs kept as an option for later if we need production inference speed without injection.

**Sources (fetched 2026-04-18):**
- github.com/EricLBuehler/mistral.rs
- github.com/huggingface/candle/blob/main/candle-transformers/src/models/llama.rs
- github.com/rustformers/llm (archived)
- docs.rs/mistralrs
