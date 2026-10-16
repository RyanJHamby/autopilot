-- Nothing in this schema is for anonymous visitors. Remove Supabase's default anon grants (RLS already denies;
-- this makes the denial a clean 401/permission error instead of relying on policies alone).
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke all on sequences from anon;
