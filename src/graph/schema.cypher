// FinText-LLM Neo4j schema bootstrap.
//
// Run with: cypher-shell -u neo4j -p password < src/graph/schema.cypher
//
// Every entity label is anchored by a single unified ``entity_id``
// string property. This keeps lookups, MERGE keys, and relationship
// MATCH patterns consistent across ingestion passes, regardless of
// whether a node is a Company, Product, Claim, Evidence, etc.

// -----------------------------------------------------------------------------
// Unique constraints: every label shares the ``entity_id`` key.
// -----------------------------------------------------------------------------
CREATE CONSTRAINT company_entity_id IF NOT EXISTS
FOR (n:Company) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT product_entity_id IF NOT EXISTS
FOR (n:Product) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT component_entity_id IF NOT EXISTS
FOR (n:Component) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT service_entity_id IF NOT EXISTS
FOR (n:Service) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT infrastructure_entity_id IF NOT EXISTS
FOR (n:Infrastructure) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT energy_source_entity_id IF NOT EXISTS
FOR (n:EnergySource) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT datacenter_entity_id IF NOT EXISTS
FOR (n:DataCenter) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT segment_entity_id IF NOT EXISTS
FOR (n:Segment) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT customer_entity_id IF NOT EXISTS
FOR (n:Customer) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT supplier_entity_id IF NOT EXISTS
FOR (n:Supplier) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT competitor_entity_id IF NOT EXISTS
FOR (n:Competitor) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT region_entity_id IF NOT EXISTS
FOR (n:Region) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT country_entity_id IF NOT EXISTS
FOR (n:Country) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT commodity_entity_id IF NOT EXISTS
FOR (n:Commodity) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT policy_entity_id IF NOT EXISTS
FOR (n:Policy) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT risk_entity_id IF NOT EXISTS
FOR (n:Risk) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT opportunity_entity_id IF NOT EXISTS
FOR (n:Opportunity) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT filing_entity_id IF NOT EXISTS
FOR (n:Filing) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT transcript_entity_id IF NOT EXISTS
FOR (n:Transcript) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT article_entity_id IF NOT EXISTS
FOR (n:Article) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT event_entity_id IF NOT EXISTS
FOR (n:Event) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT executive_entity_id IF NOT EXISTS
FOR (n:Executive) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT claim_entity_id IF NOT EXISTS
FOR (n:Claim) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT evidence_entity_id IF NOT EXISTS
FOR (n:Evidence) REQUIRE n.entity_id IS UNIQUE;

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
