# ADR-007: pgvector in same PostgreSQL, no separate vector DB

- **Status:** Accepted
- **Date:** 2026-04-18
- **Amended:** 2026-04-19 — PostgreSQL 15 → 17 (tracks ADR-001 amendment).

## Context

TechScreen will store embeddings of annotated turns to power RAG features (Roadmap H2). The options:

1. **Separate vector database** — Pinecone, Weaviate, Qdrant as a managed or self-hosted service.
2. **pgvector in the application Postgres** — vectors live in the same database as relational data.

At MVP scale we expect < 10k embeddings in the first six months. A dedicated vector DB adds: a second operational surface, a second billing line, a second backup regime, and cross-store consistency concerns (what if a turn is deleted in Postgres but its vector remains?).

## Decision

All embeddings live in the **same Cloud SQL PostgreSQL 17** instance via the `pgvector` extension. The table `annotated_turn_embedding` stores `vector(768)` column and foreign keys into `turn` / `turn_annotation`.

Index type: `IVFFlat` initially; upgrade to `HNSW` if recall or latency requires it.

## Consequences

**Positive.**

- One DB to manage, back up, monitor, migrate.
- Joins between relational metadata and vector neighbours are a simple SQL query — no two-store coordination.
- Cost at MVP scale is near zero — an extra column on an existing row.
- Aligns with the "minimise moving parts" bias of a pre-PMF MVP.

**Negative.**

- pgvector is not a specialist vector engine. At ~100k+ vectors with high QPS we will hit recall/latency limits.
- Some advanced reranking / hybrid search features require additional Postgres extensions or application-side logic.

**Mitigation.**

- The vector access code is isolated behind a `VectorStore` interface. Migrating to Pinecone or Qdrant later is a 2-day job of moving embeddings and swapping the interface implementation — not a rewrite.
- Monitor recall@k and p95 latency on the RAG query; trigger migration when we cross preset thresholds.

## Amendment — 2026-04-19: PostgreSQL 15 → 17

Tracks ADR-001 amendment of the same date. pgvector behaviour, IVFFlat-then-HNSW upgrade path, and the single-DB rationale all carry over unchanged — pgvector supports PG15/16/17 identically for our `vector(768)` workload. Only the version pin moves from 15 to 17 to extend the EOL runway. Verify pgvector availability on Cloud SQL PG17 in `europe-west1` at provisioning time (T01a); fall back to PG16 only if PG17 + pgvector is blocked there.
