# Infrastructure Overview
- Terraform state stored in S3 bucket: infra-state-prod
- Ansible playbooks in /opt/ansible
- Monitoring: Prometheus + Grafana (port 3000)

## Access Policies
- Bastion host required for DB access
- SSH keys rotated every 90 days
- Root login disabled (use sudo)
