// FinText-LLM Neo4j schema bootstrap.
//
// Run with: cypher-shell -u neo4j -p password < src/graph/schema.cypher
//
// Each entity label is anchored by a unique string id property named
// `<label_snake>_id` (e.g. `company_id`, `evidence_id`, `claim_id`).
// This keeps lookups and MERGE keys stable across ingestion passes.

// -----------------------------------------------------------------------------
// Unique constraints (one per entity label).
// -----------------------------------------------------------------------------
CREATE CONSTRAINT company_id IF NOT EXISTS
FOR (n:Company) REQUIRE n.company_id IS UNIQUE;

CREATE CONSTRAINT product_id IF NOT EXISTS
FOR (n:Product) REQUIRE n.product_id IS UNIQUE;

CREATE CONSTRAINT segment_id IF NOT EXISTS
FOR (n:Segment) REQUIRE n.segment_id IS UNIQUE;

CREATE CONSTRAINT customer_id IF NOT EXISTS
FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE;

CREATE CONSTRAINT supplier_id IF NOT EXISTS
FOR (n:Supplier) REQUIRE n.supplier_id IS UNIQUE;

CREATE CONSTRAINT competitor_id IF NOT EXISTS
FOR (n:Competitor) REQUIRE n.competitor_id IS UNIQUE;

CREATE CONSTRAINT region_id IF NOT EXISTS
FOR (n:Region) REQUIRE n.region_id IS UNIQUE;

CREATE CONSTRAINT country_id IF NOT EXISTS
FOR (n:Country) REQUIRE n.country_id IS UNIQUE;

CREATE CONSTRAINT commodity_id IF NOT EXISTS
FOR (n:Commodity) REQUIRE n.commodity_id IS UNIQUE;

CREATE CONSTRAINT policy_id IF NOT EXISTS
FOR (n:Policy) REQUIRE n.policy_id IS UNIQUE;

CREATE CONSTRAINT risk_id IF NOT EXISTS
FOR (n:Risk) REQUIRE n.risk_id IS UNIQUE;

CREATE CONSTRAINT opportunity_id IF NOT EXISTS
FOR (n:Opportunity) REQUIRE n.opportunity_id IS UNIQUE;

CREATE CONSTRAINT filing_id IF NOT EXISTS
FOR (n:Filing) REQUIRE n.filing_id IS UNIQUE;

CREATE CONSTRAINT transcript_id IF NOT EXISTS
FOR (n:Transcript) REQUIRE n.transcript_id IS UNIQUE;

CREATE CONSTRAINT article_id IF NOT EXISTS
FOR (n:Article) REQUIRE n.article_id IS UNIQUE;

CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (n:Event) REQUIRE n.event_id IS UNIQUE;

CREATE CONSTRAINT executive_id IF NOT EXISTS
FOR (n:Executive) REQUIRE n.executive_id IS UNIQUE;

CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (n:Claim) REQUIRE n.claim_id IS UNIQUE;

CREATE CONSTRAINT evidence_id IF NOT EXISTS
FOR (n:Evidence) REQUIRE n.evidence_id IS UNIQUE;

// -----------------------------------------------------------------------------
// Lookup indexes (non-unique) for common join fields.
// -----------------------------------------------------------------------------
CREATE INDEX company_cik IF NOT EXISTS
FOR (n:Company) ON (n.cik);

CREATE INDEX company_ticker IF NOT EXISTS
FOR (n:Company) ON (n.ticker);

CREATE INDEX evidence_source IF NOT EXISTS
FOR (n:Evidence) ON (n.source_id);

CREATE INDEX claim_type IF NOT EXISTS
FOR (n:Claim) ON (n.claim_type);

CREATE INDEX claim_confidence IF NOT EXISTS
FOR (n:Claim) ON (n.confidence);
