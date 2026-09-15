<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Authentication and identity

**Landscape.** Framework-native libraries (Auth.js/NextAuth, Devise, Django auth,
Spring Security, Passport); developer-focused hosted providers (Clerk, Auth0,
Stytch, Supabase Auth, Firebase Auth, Better Auth, Lucia); enterprise-oriented
(WorkOS, Okta, Keycloak self-hosted).

**What usually decides it.**
- Does the app need enterprise SSO (SAML/SCIM)? That single requirement eliminates
  most of the list and is frequently the whole decision.
- Where do user records live? Providers that own the user table create a
  synchronisation problem with an existing `users` table; providers that federate
  into your database don't. Check the schema before ranking.
- Is there already an auth system? Replacing working auth is a migration with
  session invalidation and password-hash portability concerns, not an integration.
- Serverless runtime pushes toward stateless JWT/session strategies.

**Hidden requirements.** Session strategy and refresh handling; account linking
when a user signs up twice by different methods; email deliverability for
verification and reset (an email provider decision hiding inside an auth
decision); an admin path for support to unlock accounts; migration of existing
password hashes if any exist.

**Portability note.** Password hashes are usually exportable; social-login identity
mappings often are not, which is the part that actually traps you. Ask what an
export contains before scoring `portability` above 3.

**Verify.** MAU tiers and what counts as an active user, whether SSO/SAML sits
behind an enterprise plan, hash export policy.
