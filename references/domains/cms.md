<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Content management

**Landscape.** Headless CMS (Contentful, Sanity, Strapi, Payload, Prismic,
Storyblok, Directus); git-based content (MDX files, Keystatic, TinaCMS);
traditional (WordPress headless, Ghost).

**What usually decides it.**
- **Who edits, and how often.** If developers are the only editors and content
  ships with releases, MDX in the repo beats any CMS - it versions, reviews and
  deploys with the code. A CMS earns its cost when non-technical people publish
  independently.
- Content model complexity. Flat pages and posts suit almost anything; deeply
  relational content with references and localisation narrows the field fast.
- Self-hosting requirement. Strapi, Payload and Directus self-host; most others
  don't.
- Rendering strategy. Static generation needs webhook-triggered rebuilds;
  server-rendering needs low-latency reads and a cache.

**Hidden requirements.** Preview and draft handling, which is where most CMS
integrations get complicated. Cache invalidation on publish - without it, editors
publish and see nothing change, and they will lose faith quickly. Image handling
and transforms. Migration of existing content, which is usually a scripted one-off.
Roles and permissions if more than a couple of editors.

**Portability.** Content exports as JSON from most platforms, but the content model
and rich-text format are provider-shaped; rich text in a proprietary AST is the part
that hurts. Prefer portable formats (Markdown, or a documented rich-text spec).
