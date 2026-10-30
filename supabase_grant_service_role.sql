-- Run this in Supabase Dashboard -> SQL Editor as the project owner/postgres role.
-- Keep SUPABASE_SECRET_KEY / service_role credentials on the backend only.
-- This grants the backend role CRUD access to existing public tables; RLS policies
-- do not replace SQL table privileges, and service_role should never be exposed to clients.

grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select, update on all sequences in schema public to service_role;

-- Apply the same privileges to tables/sequences created in the future by postgres.
alter default privileges for role postgres in schema public
grant select, insert, update, delete on tables to service_role;

alter default privileges for role postgres in schema public
grant usage, select, update on sequences to service_role;
