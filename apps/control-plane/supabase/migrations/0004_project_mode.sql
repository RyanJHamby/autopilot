alter table projects add column mode text not null default 'dormant' check (mode in ('standard', 'yolo', 'dormant'));
alter table projects add column is_public boolean not null default false;
