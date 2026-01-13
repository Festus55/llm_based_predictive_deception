# Deployment Checklist
- [x] Pull latest images from internal registry
- [x] Update .env configurations (staging)
- [ ] Run migration scripts (pending DB backup)
- [ ] Switch traffic to blue/green deployment

## Issues
- Connection timeout on port 5432 (investigate firewall rules)
- Redis cache invalidation failing intermittently
