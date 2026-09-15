<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# AI, LLM and vector infrastructure

**Landscape.** Model providers (Anthropic, OpenAI, Google, Mistral, open models
via Together/Fireworks/Bedrock); vector stores (pgvector in existing Postgres,
Pinecone, Qdrant, Weaviate, Chroma, Turbopuffer); orchestration (LangChain,
LlamaIndex, Vercel AI SDK, or plain SDK calls).

**What usually decides it.**
- **If Postgres is already in the stack, evaluate pgvector first.** For corpora up
  to the low millions of vectors it avoids an entire additional system, keeps
  embeddings transactionally consistent with source records, and lets you filter by
  ordinary SQL columns - which is often the actual requirement. Recommending a
  dedicated vector database over pgvector needs a reason.
- Streaming requirement. Token streaming needs a compatible runtime and endpoint
  style; check for edge/serverless timeout limits.
- Cost control. Token costs scale with usage in a way most integrations don't, so
  caching, model routing and per-user limits are architectural, not optional.
- Whether an orchestration framework earns its abstraction. For a single
  provider and straightforward flows, direct SDK calls are often clearer and easier
  to debug.

**Hidden requirements.** Streaming plumbed end to end; timeout handling on long
generations; retry with backoff on rate limits; prompt versioning; evaluation
before and after prompt changes; cost observability per user or feature; PII
handling policy for what gets sent to a provider; embedding regeneration when the
model changes, which is a full reindex.

**Verify.** Everything. This domain moves faster than any other - model names,
context windows, pricing and availability all change on the order of weeks.
