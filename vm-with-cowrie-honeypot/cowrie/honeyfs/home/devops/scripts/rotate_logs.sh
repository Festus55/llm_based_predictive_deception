#!/bin/bash
# Log rotation utility
find /var/log/app -name "*.log" -mtime +7 -exec gzip {} \;
find /var/log/app -name "*.gz" -mtime +30 -delete
echo "Logs rotated."
