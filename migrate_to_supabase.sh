#!/bin/bash
# Migration: Render PostgreSQL → Supabase
# Run: bash migrate_to_supabase.sh

RENDER_URL="postgresql://dashboradbackend_user:ThRgEm6IC81u446UojdEAHTywXAHnwyJ@dpg-d7ispjugvqtc739f5h1g-a.singapore-postgres.render.com/dashboradbackend"
SUPABASE_URL="postgresql://postgres.xztjadqrctytgadbxfqr:Hddashboard%402026@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

echo "Step 1: Dumping data from Render..."
pg_dump "$RENDER_URL" \
  --no-owner \
  --no-acl \
  --schema=public \
  -f render_backup.sql

if [ $? -ne 0 ]; then
  echo "ERROR: Dump failed. Check your Render URL and network connection."
  exit 1
fi

echo "Dump complete: render_backup.sql"

echo "Step 2: Restoring to Supabase..."
psql "$SUPABASE_URL" -f render_backup.sql

if [ $? -ne 0 ]; then
  echo "ERROR: Restore failed. Check your Supabase password."
  exit 1
fi

echo ""
echo "Migration complete!"
echo ""
echo "Next step — update Render env var:"
echo "  Key:   DATABASE_URL"
echo "  Value: $SUPABASE_URL"
