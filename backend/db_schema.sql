-- PipeScan PostgreSQL schema.
-- This file documents the two business tables requested by the project:
-- 1. inspection_records stores user-submitted inspection data.
-- 2. inspection_reports stores generated report output.

create table if not exists pipe_segments (
    id serial primary key,
    pipe_code varchar(80) not null unique,
    length_m double precision not null,
    diameter_mm double precision not null,
    region_type varchar(40) not null default 'normal',
    soil_type varchar(40) not null default 'unknown',
    location varchar(200) not null default '',
    remark text not null default '',
    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table if not exists inspection_records (
    id serial primary key,
    pipe_id integer not null references pipe_segments(id) on delete cascade,
    input_data jsonb not null,
    defects jsonb not null,
    created_at timestamp not null default now()
);

create table if not exists inspection_reports (
    id serial primary key,
    pipe_id integer not null references pipe_segments(id) on delete cascade,
    inspection_id integer not null references inspection_records(id) on delete cascade,
    evaluation jsonb not null,
    markdown text not null,
    report_path varchar(500) not null,
    created_at timestamp not null default now()
);

create index if not exists ix_pipe_segments_pipe_code on pipe_segments(pipe_code);
create index if not exists ix_inspection_records_pipe_id on inspection_records(pipe_id);
create index if not exists ix_inspection_reports_pipe_id on inspection_reports(pipe_id);
create index if not exists ix_inspection_reports_inspection_id on inspection_reports(inspection_id);
