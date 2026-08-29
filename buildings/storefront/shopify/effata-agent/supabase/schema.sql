-- Effata Picks — Supabase schema for the autonomous store agent
-- Run this in the Supabase SQL editor (or via migrations).

create extension if not exists vector;

-- Agent action audit log (with rollback support)
create table if not exists agent_actions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  tool_name text not null,
  args jsonb,
  result jsonb,
  reasoning text,
  approved_by text,
  status text check (status in ('pending','approved','rejected','executed','rolled_back')),
  rollback_data jsonb
);

-- Product embeddings for semantic search
create table if not exists product_embeddings (
  id uuid primary key default gen_random_uuid(),
  shopify_product_id text unique not null,
  title text,
  description text,
  embedding vector(1536),
  updated_at timestamptz default now()
);

-- Agent memory / conversation history
create table if not exists agent_memory (
  id uuid primary key default gen_random_uuid(),
  session_id text,
  role text check (role in ('user','assistant','tool')),
  content text,
  tool_name text,
  created_at timestamptz default now()
);

-- Scheduled tasks (mirrors Inngest crons for visibility)
create table if not exists scheduled_tasks (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  cron_expression text,
  last_run timestamptz,
  next_run timestamptz,
  enabled boolean default true,
  config jsonb
);

create index if not exists agent_actions_created_idx on agent_actions(created_at);
create index if not exists agent_memory_session_idx on agent_memory(session_id);

-- Semantic product lookup
create or replace function match_products(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  shopify_product_id text,
  title text,
  description text,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    pe.id,
    pe.shopify_product_id,
    pe.title,
    pe.description,
    1 - (pe.embedding <=> query_embedding) as similarity
  from product_embeddings pe
  where 1 - (pe.embedding <=> query_embedding) > match_threshold
  order by pe.embedding <=> query_embedding
  limit match_count;
end;
$$;
