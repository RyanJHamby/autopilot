-- The access helpers must not be callable as public RPCs (/rest/v1/rpc/can). Move them to a schema the API does not
-- expose; RLS policies still use them (bound by oid), and only signed-in roles may execute.
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

alter function public.is_owner(uuid) set schema private;
alter function public.can(uuid, text) set schema private;

revoke execute on function private.is_owner(uuid) from public, anon;
revoke execute on function private.can(uuid, text) from public, anon;
grant execute on function private.is_owner(uuid) to authenticated;
grant execute on function private.can(uuid, text) to authenticated;
