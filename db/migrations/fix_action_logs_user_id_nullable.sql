-- Migration: Fix action_logs.user_id to allow NULL values
-- Date: 2026-01-30
-- Description: Changes user_id column in action_logs to allow NULL values and sets ondelete='SET NULL'
--              This fixes the issue where deleting a user causes IntegrityError when action_logs
--              already contain NULL user_id values

-- Step 1: Drop the existing foreign key constraint
-- First, find the constraint name (it may vary, so we'll use a common pattern)
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Find the foreign key constraint name
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'action_logs'::regclass
      AND contype = 'f'
      AND confrelid = 'users'::regclass;
    
    -- Drop the constraint if it exists
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE action_logs DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

-- Step 2: Remove NOT NULL constraint from user_id column
ALTER TABLE action_logs 
ALTER COLUMN user_id DROP NOT NULL;

-- Step 3: Recreate the foreign key with ON DELETE SET NULL
ALTER TABLE action_logs
ADD CONSTRAINT fk_action_logs_user_id 
FOREIGN KEY (user_id) 
REFERENCES users(id) 
ON DELETE SET NULL;

-- Migration note:
-- This allows action_logs to retain audit trail even after user deletion
-- Existing NULL values in user_id are now valid
-- When a user is deleted, their action_logs.user_id will be set to NULL automatically
