# ADR 0004: Market-data storage, identity and snapshots

- Status: Accepted
- Date: 2026-11-14

## Context

Phase 1 (spec sections 2.1, 5 and 13) needs an instrument master, a provider boundary,
raw/normalized/curated layers, validation with quarantine, reproducible snapshots and a
historical query API. No licensed data provider has been selected.

## Decision

**Two stores.** PostgreSQL is the catalog: instrument master, raw-object records, snapshot
manifests, ingestion runs and audit events. Bars live as Parquet files in a file-based lake
under `DATA_DIR`, with layers `raw/`, `normalized/` and `curated/`. Polars reads and writes
Parquet.

**A snapshot is published by its catalog row.** Snapshot files are staged, moved into place
and the row inserted inside one database transaction, under a per-dataset advisory lock.
Readers resolve snapshots only through the catalog, so files without a row (from a failed or
crashed publish) are invisible and are replaced by the next publish of that version.

**Identity.** An instrument gets a random UUID the first time a provider mentions it.
`provider_instrument_ids` maps `(source_id, provider id)` to that UUID. Symbols, names and
ISINs are effective-dated rows in `instrument_symbols`; none of them is the identity, because
all of them change (ISINs change on some corporate actions in India).

**Providers return bytes; parsers are separate.** `fetch_*` returns the source payload
unchanged and ingestion stores it before parsing. Parsers are registered by format ID and
always run against the stored bytes. That is what lets `reproduce` rebuild a snapshot
without the provider.

**Idempotency by fingerprint.** The fingerprint hashes the source ID, the declared dataset
attributes, the schema and normalizer versions and the raw checksums. An ingestion whose
fingerprint is already published returns the existing snapshot and writes nothing. Any
change to input or rules yields a new version of the dataset; nothing is overwritten.

**One dataset per source.** `dataset_id` is `<source_id>.daily_bars`. Sources are never
merged, and the bars API has no default dataset, so synthetic data cannot be served by
accident in place of real data.

**Prices are decimals.** `Decimal(20, 6)` for prices, `Decimal(24, 4)` for turnover, 64-bit
integer volume. The API returns prices as decimal strings.

**Routes beyond spec section 11.** `/api/v1/datasets/...` and `/api/v1/health/ready` are
added so provenance, quarantine reports, failed runs and database readiness are inspectable.

## Deliberate simplifications

- The provider interface has no date-range or per-instrument arguments (the spec's
  illustrative contract has both). Neither existing provider needs them; they get added with
  the first API-backed provider.
- Curated content currently equals the validated normalized content. The layers are kept
  separate because curation rules (adjustments, point-in-time joins) arrive later.
- Symbol-period overlap is enforced in code within one source, not by a database exclusion
  constraint. Mappings from different sources for one instrument are not reconciled, because
  there is no cross-source instrument matching yet: a second source creates its own
  instruments.
- Internal instrument IDs are random, so a snapshot's content checksum is reproducible
  within one deployment's catalog, not across separately initialised databases.

## Consequences

- Ingestion and all market-data routes require PostgreSQL; their tests need a disposable
  database.
- The lake is a local directory. Backups must cover the database and the lake together.
- Quarantine reports are read whole into memory by the API. Fine for daily data at the
  current scale; revisit for large deliveries.
