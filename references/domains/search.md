<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Search

**Landscape.** Database-native first (Postgres full-text search with `tsvector`,
`pg_trgm`, or pgvector for semantic); hosted search (Algolia, Typesense Cloud,
Meilisearch Cloud, Elastic Cloud); self-hosted (Meilisearch, Typesense,
OpenSearch, Elasticsearch).

**What usually decides it.**
- **Corpus size and query pattern.** Under roughly a hundred thousand documents
  with simple relevance needs, Postgres full-text is frequently the right answer
  and removes an entire piece of infrastructure. Recommend it when it fits; it is
  the most commonly overlooked good option in this domain.
- Typo tolerance, faceting, instant-search latency and relevance tuning are where
  dedicated engines earn their cost.
- Who tunes relevance? If nobody will own it, a managed service with good defaults
  beats a tunable one.
- Search-as-you-type from the browser needs a search-only API key and a
  latency-appropriate host.

**Hidden requirements.** Index synchronisation on every write path - the part
teams underestimate; a backfill/reindex job for schema changes; handling index and
database divergence; permission filtering so users only see their own results,
which constrains index design; analytics on empty results.

**Cost shape.** Hosted search often prices on records plus operations, so a
write-heavy corpus can cost more than a read-heavy one of the same size. Check the
repo's write patterns before scoring `cost_efficiency`.
