-- BoardBreeze Concierge — Governance Tools schema
-- Run this in your Supabase SQL editor.
--
-- Creates:
--   1. governance_kb       — RAG corpus with 512-dim Voyage embeddings
--   2. conversation_state  — per-session state the Concierge reads
--   3. handoffs            — log of agent-to-agent handoffs (for dashboard)
--   4. match_governance_kb RPC — pgvector similarity search with filters

-- ==========================================================================
-- Extensions
-- ==========================================================================
create extension if not exists vector;
create extension if not exists "uuid-ossp";

-- ==========================================================================
-- 1. governance_kb
-- ==========================================================================
create table if not exists governance_kb (
    id             uuid primary key default uuid_generate_v4(),
    content        text not null,
    source         text not null,         -- e.g. "Gov. Code § 54954.2"
    document       text not null,         -- e.g. "California Brown Act"
    section_title  text,                  -- e.g. "Agenda posting requirements"
    jurisdiction   text not null,         -- "CA" | "CA_STATE" | "federal" | ...
    agency_types   text[] default '{}',   -- ['school_district', 'ccd'] or []=all
    metadata       jsonb default '{}'::jsonb,
    embedding      vector(512),           -- voyage-3-lite → 512 dims
    created_at     timestamptz not null default now()
);

-- IVFFlat index: fast approximate KNN. Tune `lists` to ~sqrt(rows).
-- For < 10k rows, lists = 100 is fine.
create index if not exists governance_kb_embedding_ivfflat_idx
  on governance_kb using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create index if not exists governance_kb_jurisdiction_idx
  on governance_kb (jurisdiction);

-- ==========================================================================
-- 2. conversation_state (shared across all agents)
-- ==========================================================================
create table if not exists conversation_state (
    session_id        uuid primary key,
    caller_id         text,                -- E.164 phone number
    channel           text not null,       -- 'voice' | 'sms'
    active_agent      text not null default 'concierge',
    intent            text,
    entities          jsonb default '{}'::jsonb,
    last_handoff_id   uuid,
    status            text not null default 'open',  -- open|resolved|escalated|booked|lost
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists conversation_state_caller_idx
  on conversation_state (caller_id);

-- ==========================================================================
-- 3. handoffs (audit log + dashboard source)
-- ==========================================================================
create table if not exists handoffs (
    id           uuid primary key,
    session_id   uuid not null references conversation_state(session_id) on delete cascade,
    from_agent   text not null,
    to_agent     text not null,
    package      jsonb not null,
    created_at   timestamptz not null default now()
);

create index if not exists handoffs_session_idx on handoffs (session_id);

-- ==========================================================================
-- 4. match_governance_kb RPC
-- Used by search_governance_kb. Uses cosine similarity on pgvector.
-- jurisdiction_filter is nullable — pass NULL to search across all.
-- ==========================================================================
create or replace function match_governance_kb(
    query_embedding      vector(512),
    match_count          int default 5,
    jurisdiction_filter  text default null,
    similarity_threshold float default 0.3
)
returns table (
    id            uuid,
    content       text,
    source        text,
    document      text,
    section_title text,
    jurisdiction  text,
    agency_types  text[],
    similarity    float
)
language sql stable
as $$
  select
    k.id,
    k.content,
    k.source,
    k.document,
    k.section_title,
    k.jurisdiction,
    k.agency_types,
    1 - (k.embedding <=> query_embedding) as similarity
  from governance_kb k
  where
    (jurisdiction_filter is null or k.jurisdiction = jurisdiction_filter)
    and 1 - (k.embedding <=> query_embedding) >= similarity_threshold
  order by k.embedding <=> query_embedding
  limit match_count;
$$;

-- After you seed the KB, run: analyze governance_kb;
-- This helps the planner pick the ivfflat index.
