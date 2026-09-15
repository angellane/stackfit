<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Backend platforms and databases

**Landscape.** Integrated platforms (Supabase, Firebase, Appwrite, Convex,
Nhost); managed Postgres (Neon, PlanetScale for MySQL, Railway, RDS, Cloud SQL);
edge-oriented (Turso, Cloudflare D1).

**What usually decides it.**
- Adopting a platform for one feature buys the whole platform's model. That's fine
  when several features are coming, and a poor trade for one.
- Connection model. Serverless functions exhaust traditional connection pools;
  pooling support or an HTTP-based driver is a hard requirement, not a nice-to-have.
- Relational versus document, decided by the data, not by preference.
- Postgres-compatible options keep portability high because the query language and
  tooling transfer.

**Hidden requirements.** Connection pooling; migration workflow; backup and
point-in-time recovery expectations; read replicas if read-heavy; local development
parity; row-level security semantics if using a platform that exposes the database
to clients directly.

For replacing an existing database or platform, use
`references/migration-analysis.md` - that is a migration, not an integration, and
the effort profile is entirely different.
