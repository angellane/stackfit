<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Realtime and collaboration

**Landscape.** Managed pub/sub (Pusher, Ably, Supabase Realtime); collaboration
infrastructure with conflict resolution (Liveblocks, PartyKit, Yjs-based stacks);
self-managed websockets (Socket.IO, Django Channels, Phoenix Channels,
ActionCable).

**What usually decides it.**
- **Runtime model, more than anywhere else.** Serverless platforms cannot hold
  persistent connections. On a serverless-detected repo, self-hosted websockets are
  a disqualifier, not a low score - this is the single most common architectural
  mismatch in this domain.
- Broadcast versus collaborative editing. Presence and notifications are a
  different problem from concurrent document editing with conflict resolution; CRDT
  infrastructure is not worth it for the former.
- Connection scale and fan-out pattern.

**Hidden requirements.** Authentication on connect, usually via a token endpoint;
reconnection and state resync after a drop; presence cleanup for ghost users;
message ordering guarantees; scaling connections across instances if self-hosted;
mobile background-connection behaviour.
