-- Run this in Supabase Dashboard > SQL Editor.
-- Adds a nullable profile image URL to existing users without deleting data.
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS img_url text;
