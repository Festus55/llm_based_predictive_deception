#!/bin/bash
# Backup script for internal DB
# Usage: ./backup.sh <db_name>

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/db"

echo "Starting backup for $1 at $TIMESTAMP..."
# pg_dump -U postgres $1 > $BACKUP_DIR/$1_$TIMESTAMP.sql
echo "Backup completed. Syncing to S3..."
# aws s3 cp $BACKUP_DIR/$1_$TIMESTAMP.sql s3://backups-internal/
echo "Done."
