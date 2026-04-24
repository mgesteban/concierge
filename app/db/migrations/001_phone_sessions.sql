-- Phone → CMA session lookup. Keyed on E.164 phone number. One session
-- per caller, reused across SMS + voice turns for continuity. Sessions
-- idle for weeks on the CMA side, so we never need to rotate unless a
-- caller hits an unrecoverable error.
create table if not exists phone_sessions (
    phone            text primary key,         -- E.164, e.g. +14155551212
    cma_session_id   text not null,
    created_at       timestamptz not null default now(),
    last_used_at     timestamptz not null default now()
);

create index if not exists phone_sessions_last_used_idx
  on phone_sessions (last_used_at desc);
