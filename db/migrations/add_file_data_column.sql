-- Migration: Add file_data column to task_files table
-- Date: 2026-01-12
-- Description: Adds file_data column to store all files in base64 format in database instead of disk

-- Add file_data column to task_files table
ALTER TABLE task_files 
ADD COLUMN file_data TEXT NULL;

-- Migration note:
-- This column will store all files (documents, photos, etc.) in base64 format
-- Existing files in photo_base64 column will continue to work
-- New files will use file_data column
-- file_path column is kept for backward compatibility with old files on disk

