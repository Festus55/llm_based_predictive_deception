---
title:  Honeypot Predictive Deception
authors:
  - name: Leonardo Barone
  - name: Leonardo Ciacco
  - name: Enrico Giannini
---

# HONEYPOT PREDICTIVE DECEPTION

An AI-powered honeypot system that uses LLM-based predictive analysis to dynamically deploy Canarytokens as traps, anticipating attacker behavior in real-time during SSH sessions.

--- 

This project implements a **predictive deception** system that enhances traditional honeypots with machine learning capabilities. When an attacker connects to the honeypot via SSH, the system: 

1. **Monitors** the attacker's command history in real-time
2. **Predicts** the attacker's next likely actions using a fine-tuned LLM (Gemma 3 4B and Gemma 3 12B)
3. **Deploys** targeted Canarytokens as traps before the attacker reaches them
4. **Alerts** security teams when traps are triggered

## Architecture

```mermaid
flowchart LR
  subgraph OUTSIDE["Outside"]
    direction TB
    ADMIN["Admin"]
    ATTACKER["Attacker"]
  end

  subgraph HOST["debian-HOST"]
    %% SSH Access
    FSSH["SSH:4321"]
    P22["port 22"]
    P6453["port 6453"]

    %% Canary Infrastructure
    subgraph CANARY["Canarytokens Docker"]
      direction TB
      NGINX["Nginx:8008 (Public)"]
      FRONT["Frontend:8082 (Internal)"]
      SWITCH["Switchboard"]
    end

    LLM["LLM Automation"]
    LISTENER["Listener:9000"]
    MONGO["MongoDB"]

    %% Periodic log ingester
    INGEST["Log Ingester\nEvery X minutes"]:::ingester

    %% VM Honeypot
    subgraph VM["debian-VM"]
      COWRIE["Cowrie:2222"]:::honeypot
      REAL_SSH["SSH:22"]
      TOKEN["Canary File/Link"]:::canary
      COWRIE_JSON["cowrie.json log file"]:::logfile
    end
  end

  %% SSH Flows
  ADMIN -->|SSH 4321| FSSH
  ADMIN -->|SSH 6453| P6453
  ATTACKER -->|SSH 22| P22
  P22 -->|FORWARD| COWRIE
  P6453 -->|FORWARD| REAL_SSH

  %% Canary Creation Flow
  COWRIE -->|1. Attacker Commands| LLM
  LLM -->|2. Generate Token| FRONT
  FRONT -->|3. Return Token URL| LLM
  LLM -->|4. Send Path & URL| COWRIE
  COWRIE -->|5. Create File| TOKEN

  %% Trigger Flow
  TOKEN -.->|6. Attacker Opens| ATTACKER
  ATTACKER -.->|7. Trigger HTTP :8008| NGINX
  NGINX -->|Proxy| SWITCH
  SWITCH -->|8. Webhook POST| LISTENER
  LISTENER -->|9. Save| MONGO

  %% Periodic Cowrie log ingestion
  INGEST -->|SCP pull cowrie.json| REAL_SSH
  REAL_SSH -->|Read VM log file| COWRIE_JSON
  INGEST -->|Parse JSON lines + Insert| MONGO

  %% Styling
  classDef honeypot fill:#ffe6e6,stroke:#cc0000,stroke-width:2px,color:#660000;
  classDef canary fill:#ffffcc,stroke:#ffcc00,stroke-width:2px,stroke-dasharray: 5 5,color:#333;
  classDef ingester fill:#e3f2fd,stroke:#0d47a1,color:#000;
  classDef logfile fill:#f3e5f5,stroke:#6a1b9a,color:#000;

  style VM fill:#1f4b7a,stroke:#7fb3ff,stroke-width:2px,color:#ffffff;
  style HOST fill:#4a4a4a,stroke:#a0a0a0,stroke-width:1px,color:#ffffff;
  style CANARY fill:#333333,stroke:#00ff00,stroke-width:1px,color:#fff;
  style LISTENER fill:#e0f2f1,stroke:#004d40,color:#000;
  style MONGO fill:#e8f5e9,stroke:#1b5e20,color:#000;
```

## Repository Structure

```
honeypot_predictive_deception/
├── README.md
├── listener9000.py                    # Webhook listener for Canarytoken alerts
... TODO when repo ok
```

## Supported Trap Types

The system can deploy various types of Canarytokens based on predicted attacker intent:

| Trap Category | Template Examples | Detection Method |
|---------------|-------------------|------------------|
| **AWS Credentials** | `AWS_CLI_DEFAULT`, `AWS_ENV_WEBAPP`, `AWS_PY_S3_UPLOADER` | AWS API monitoring |
| **Kubernetes** | `K8S_USER_DEFAULT`, `K8S_CI_PIPELINE`, `K8S_ROOT_ADMIN` | K8s API token monitoring |
| **WireGuard VPN** | `VPN_WG_SERVER_IFACE`, `VPN_WG_MOBILE` | VPN client activation |
| **HTTP Traps** | `TRAP_BASH_LOGROTATE`, `TRAP_PY_POSTGRES_DUMP` | Script execution callback |
| **Leak Files** | `LEAK_PLAINTEXT_CREDS`, `LEAK_INFRA_INVENTORY` | File access monitoring |
| **PDF Lures** | `LURE_CONTEXT_PHISHING`, `LURE_CONTEXT_PROJECT` | PDF reader phone-home |
| **File Substitution** | `FILE_SUBSTITUTION_HTTP` | Download detection |

---

## Installation

### Prerequisites

- Debian-based VPS with nested virtualization support
- NVIDIA L4 Gpu with 24GB vRAM
- At least 16GB RAM
- Public IP address

---

### 1. Setup of the Debian VPS (Host)

> **Note:** If using Google Cloud, you must open required ports in the GCP firewall and enable nested virtualization. 

#### 1.1 System Update and Virtualization Setup

1. Update the system:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. Install QEMU/KVM + libvirt:
   ```bash
   sudo apt install -y qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virtinst
   sudo systemctl enable --now libvirtd
   ```

3. Start and autostart the 'default' network:
   ```bash
   sudo virsh net-autostart default
   sudo virsh net-start default
   ```

4. Change the host SSH port to free up port 22 for the honeypot:
   ```bash
   sudo sed -i 's/#Port 22/Port 4321/' /etc/ssh/sshd_config
   sudo systemctl reload ssh
   ```

#### 1.2 VM Creation

5. Create the honeypot VM: 
   ```bash
   sudo virt-install \
       --virt-type kvm \
       --name vm-honeypot \
       --location https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/ \
       --os-variant debian12 \
       --disk size=100 \
       --memory 8192 \
       --vcpus 6 \
       --network network=default,model=virtio \
       --graphics none \
       --console pty,target_type=serial \
       --extra-args "console=ttyS0,115200n8"
   ```

   > **Important:** During installation, ensure you install the SSH Server. 

   **VM Management Commands:**
   | Action | Command |
   |--------|---------|
   | Exit VM console | `Ctrl+]` |
   | Enter VM console | `sudo virsh console vm-honeypot` |
   | Force enter console | `sudo virsh console vm-honeypot --force` |
   | Shutdown VM | `sudo virsh shutdown vm-honeypot` |
   | Start VM | `sudo virsh start vm-honeypot` |
   | Reboot VM | `sudo virsh reboot vm-honeypot` |

6. Generate SSH keys and copy to VM:
   ```bash
   ssh-keygen -t ed25519 -f ~/. ssh/cowrie_key -N ""
   # Copy public key to VM's authorized_keys
   ```

#### 1.3 Networking and Firewall

7. Get network information:
   ```bash
   # Get public interface name (e.g., ens4)
   ip -br addr

   # Get VM IP address (e.g., 192.168.122.17)
   sudo virsh domifaddr vm-honeypot
   ```

8. Enable IP forwarding:
   ```bash
   echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl. d/99-ip-forward.conf
   sudo sysctl --system
   ```

9. Configure firewalld: 
   ```bash
   # Disable UFW if active
   sudo systemctl stop ufw && sudo systemctl disable ufw

   # Enable and start firewalld
   sudo systemctl enable --now firewalld

   # Configure public zone (replace ens4 with your interface)
   sudo firewall-cmd --permanent --zone=public --add-interface=ens4

   # Open required ports
   sudo firewall-cmd --permanent --zone=public --add-port=4321/tcp   # Host SSH
   sudo firewall-cmd --permanent --zone=public --add-port=9000/tcp   # Webhook listener
   sudo firewall-cmd --permanent --zone=public --add-port=6453/tcp   # VM SSH access
   sudo firewall-cmd --permanent --zone=public --add-port=8008/tcp   # Canarytoken triggers
   sudo firewall-cmd --permanent --zone=public --add-port=8082/tcp   # Canarytoken generation
   sudo firewall-cmd --permanent --zone=public --add-port=6443/tcp   # Kubeconfig tokens
   sudo firewall-cmd --permanent --zone=public --add-port=51820/udp  # WireGuard tokens

   # Enable masquerading and forwarding
   sudo firewall-cmd --permanent --zone=public --add-masquerade
   sudo firewall-cmd --permanent --zone=public --add-forward

   # Port forwarding rules (replace 192.168.122.17 with your VM IP)
   sudo firewall-cmd --permanent --zone=public \
       --add-forward-port=port=22:proto=tcp: toport=2222:toaddr=192.168.122.17
   sudo firewall-cmd --permanent --zone=public \
       --add-forward-port=port=6453:proto=tcp:toport=22: toaddr=192.168.122.17

   # Libvirt zone configuration
   sudo firewall-cmd --permanent --zone=libvirt --add-port=8000/tcp  # LLM API
   sudo firewall-cmd --permanent --zone=libvirt --add-port=80/tcp    # Canary server

   # Apply changes
   sudo firewall-cmd --reload

   # Add nftables rules for VM traffic (replace handle number as needed)
   sudo nft insert rule ip filter LIBVIRT_FWI position 0 \
       oifname "virbr0" ip daddr 192.168.122.17 tcp dport 2222 ct state new accept
   sudo nft insert rule ip filter LIBVIRT_FWI position 0 \
       oifname "virbr0" ip daddr 192.168.122.17 tcp dport 22 ct state new accept
   ```

#### 1.4 Database Setup

10. Install MongoDB:
    ```bash
    # Follow official MongoDB installation guide for Debian: 
    # https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-debian/
    
    sudo systemctl enable --now mongod
    ```

#### 1.5 Webhook Listener

11. Set up the webhook listener:
    ```bash
    # Install dependencies
    pip3 install flask pymongo gunicorn

    # Start the listener (production)
    ./start-listener.sh

    # Or run directly for testing
    python3 listener9000.py
    ```

#### 1.6 Cowrie Log Ingestion

12. Set up the Cowrie log ingestion service:
    ```bash
    # Install dependencies
    pip3 install paramiko pymongo

    # Configure SSH key path in save-log-cowrie.py
    # Run the ingestion service
    python3 save-log-cowrie.py
    ```

    This script polls the VM every 10 minutes and saves Cowrie logs to MongoDB.

#### 1.7 Viewing Data

```bash
# Connect to MongoDB
mongosh "mongodb://localhost:27017"

# Select database
use honeypot_db

# View Canarytoken alerts
db.canary_alerts.find().sort({ _id:  -1 }).limit(10)
db.canary_alerts.find({ src_ip: "x.x.x. x" })

# View Cowrie events
db.cowrie_events.find().sort({ _ingested_at: -1 }).limit(10)

# Or use the helper script
python3 view-alerts.py
```

---

### 2. Setup of Canarytokens Server

1. Install Docker and Docker Compose. 

2. Clone and configure the Canarytokens server:
   ```bash
   git clone https://github.com/thinkst/canarytokens-docker
   cd canarytokens-docker
   cp switchboard.env.dist switchboard.env
   cp frontend. env.dist frontend. env
   ```

3. Generate WireGuard key seed:
   ```bash
   dd bs=32 count=1 if=/dev/urandom 2>/dev/null | base64
   ```

4. Edit configuration files:
   - `frontend.env`: Set `CANARY_PUBLIC_IP` and domains
   - `switchboard.env`: Configure email/webhook settings and WireGuard seed
   - `docker-compose.yml`: Adjust port mappings if needed

5. Start the services:
   ```bash
   docker compose up -d

   # View logs
   docker logs -f frontend
   docker logs -f switchboard
   ```

6. **Token URL Fix:** The generated token URLs need port 8008 appended:
   ```python
   # This is handled automatically in honeypot.py
   result['token_url'] = result['token_url']. replace(WEBHOOK_IP, f"{WEBHOOK_IP}:8008")
   ```

**API Usage Example:**
```bash
# Supported types: web, adobe_pdf, kubeconfig, wireguard, aws_keys
curl -sS -X POST "http://192.168.122.1:8082/generate" \
  -d "memo=Honeypot_Intrusion" \
  -d "type=web" \
  -d "webhook_url=http://<YOUR_PUBLIC_IP>:9000/webhook"
```

---

### 3. Setup of AWS Keys Infrastructure

For AWS credential Canarytokens: 

1. Install Terraform and AWS CLI. 

2. Configure AWS CLI:
   ```bash
   aws configure
   # Enter:  Access Key, Secret Key, Region (e.g., us-east-2)
   ```

3. Deploy infrastructure:
   ```bash
   git clone https://github.com/thinkst/canarytokens. git
   cd canarytokens/aws-token-infra
   ```

4. Create `terraform.tfvars`:
   ```hcl
   playbook_url      = "https://example.com"
   randomised_suffix = "honeypotv1"
   slack_webhook_url = "http://<YOUR_PUBLIC_IP>:9000/webhook"
   ticket_team       = "HoneypotAdmin"
   ticket_url        = "https://example.com"
   ```

5. Apply Terraform:
   ```bash
   terraform init
   terraform apply
   ```

6. Update `frontend.env` with the output URL:
   ```bash
   CANARY_AWSID_URL="https://xxxxx.execute-api.us-east-2.amazonaws.com/prod/CreateUserAPITokens"
   ```

---

### 4. Setup of the Honeypot VM

#### 4.1 Standard Installation (Recommended)

1. Update the system:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. Install Cowrie dependencies:
   ```bash
   sudo apt install -y git python3-pip python3-venv libssl-dev libffi-dev \
       build-essential libpython3-dev python3-minimal authbind
   ```

3. Create the cowrie user and clone the repository:
   ```bash
   sudo adduser --disabled-password cowrie
   sudo su - cowrie

   git clone https://github.com/cowrie/cowrie
   cd cowrie
   ```

4. Set up the virtual environment: 
   ```bash
   python3 -m venv cowrie-env
   source cowrie-env/bin/activate

   pip install --upgrade pip
   pip install -e .
   
   # Install additional dependencies for LLM integration
   pip install treq pikepdf reportlab
   ```

5. Configure Cowrie:
   ```bash
   cp etc/cowrie.cfg.dist etc/cowrie. cfg
   # Edit etc/cowrie.cfg as needed
   ```

6. **Install modified Cowrie components** (from this repository):
   ```bash
   # Copy modified files to Cowrie installation
   cp scripts/cowrie_app/honeypot. py src/cowrie/shell/honeypot.py
   cp scripts/cowrie_app/fs.py src/cowrie/shell/fs.py
   cp scripts/cowrie_app/curl.py src/cowrie/commands/curl.py
   cp scripts/cowrie_app/wget.py src/cowrie/commands/wget.py
   
   # Copy templates
   mkdir -p src/cowrie/shell/templates
   cp scripts/cowrie_app/cowrie_templates_master.json src/cowrie/shell/templates/template.json
   ```

7. Start Cowrie:
   ```bash
   cowrie start
   # To stop:  cowrie stop
   ```

#### 4.2 Docker Installation (Alternative)

```bash
# Create volume for logs
docker volume create cowrie-var

# Start Cowrie
docker run -d \
  --name cowrie-honeypot \
  -p 2222:2222 \
  -v cowrie-var:/cowrie/cowrie-git/var \
  cowrie/cowrie

# View logs
docker logs -f cowrie-honeypot

# Stop and remove
docker stop cowrie-honeypot
docker rm cowrie-honeypot
docker volume rm cowrie-var
```

> **Note:** The Docker installation requires additional configuration to integrate the LLM components. 

---

### 5. LLM Server Setup

The system uses vLLM to serve the fine-tuned Gemma 3 model. 

1. Install vLLM on the host:
   ```bash
   pip install vllm
   ```

2. Start the LLM API server:
   ```bash
   # Using the provided script
   ./scripts/cowrie_app/startup_API_server. sh

   # Or manually
   python -m vllm. entrypoints.openai.api_server \
       --model google/gemma-3-12b-it \
       --lora-modules honeypot=./adapters/gemma-3-12b \
       --port 8000 \
       --host 0.0.0.0
   ```

   The LLM API will be available at `http://192.168.122.1:8000/v1/chat/completions`.

---

## Fine-Tuning the Model

The repository includes scripts for fine-tuning Gemma 3 on honeypot session data. 

### Dataset Preparation

1. Parse raw Cowrie logs: 
   ```bash
   python scripts/parse.py
   python scripts/process_sessions.py
   ```

2. Create sliding window sequences:
   ```bash
   python scripts/mk_sliding_windows.py
   ```

3. Generate training data using knowledge distillation: 
   ```bash
   # Uses GPT-4 to generate trap predictions
   python scripts/batched\ knowledge\ distillation/sonar_batch_processor.py
   ```

4. Format for training:
   ```bash
   python scripts/training/parse_toJSONL.py
   python scripts/training/dedup.py
   python scripts/training/split.py
   ```

### Training

Use the provided Jupyter notebook or Python script: 

```bash
# Using Unsloth for efficient fine-tuning
python scripts/training/unsloth_train_12B.py

# Or use the notebook
jupyter notebook scripts/training/Gemma3_(12B).ipynb
```

The trained LoRA adapters will be saved to the `adapters/` directory.

---

## How It Works

1. **Attacker connects** to port 22 (forwarded to Cowrie on port 2222)
2. **Cowrie intercepts** commands and builds a session history
3. **Every N commands**, the session history is sent to the LLM API
4. **LLM predicts** the attacker's next likely commands and intents
5. **Based on predictions**, the system: 
   - Generates appropriate Canarytokens via the API
   - Injects trap files into Cowrie's virtual filesystem
6. **When attacker triggers a trap**, the Canarytoken server sends a webhook
7. **Webhook listener** receives the alert and stores it in MongoDB
8. **Security team** is notified of the intrusion

---

## Configuration

### Key Configuration Files

| File | Purpose |
|------|---------|
| `scripts/cowrie_app/honeypot.py` | LLM API URL, Canarytoken API URL, webhook IP |
| `etc/cowrie.cfg` | Cowrie configuration |
| `listener9000.py` | MongoDB connection string |
| `save-log-cowrie.py` | SSH connection to VM, polling interval |

### Environment Variables

```bash
# honeypot.py configuration
URL = "http://192.168.122.1:8000/v1/chat/completions"  # LLM API
API_URL = "http://192.168.122.1:8082/generate"          # Canarytoken API
WEBHOOK_IP = "35.208.122.89"                            # Public IP for webhooks
CMD_BETWEEN_LLM_CALLS = 2                               # Commands between LLM calls
```

---

## Troubleshooting

### Common Issues

1. **VM not accessible**:  Check firewall rules and nftables configuration
2. **LLM API timeout**: Ensure vLLM server is running and accessible from VM
3. **Canarytokens not generating**:  Verify Docker containers are running
4. **Webhooks not received**: Check port 9000 is open and listener is running

### Logs

```bash
# Cowrie logs (on VM)
tail -f /home/cowrie/cowrie/var/log/cowrie/cowrie.log

# Webhook listener logs
tail -f valid_alerts.log

# vLLM server logs
tail -f scripts/cowrie_app/vllm_server. log

# Docker container logs
docker logs -f frontend
docker logs -f switchboard
```

---

## Authors

- Leonardo Barone
- Leonardo Ciacco
- Enrico Giannini

---

## License

This project is for research and educational purposes.  See individual component licenses (Cowrie, Canarytokens) for their respective terms.

---

## Acknowledgments

- [Cowrie SSH/Telnet Honeypot](https://github.com/cowrie/cowrie)
- [Canarytokens by Thinkst](https://github.com/thinkst/canarytokens-docker)
- [vLLM](https://github.com/vllm-project/vllm)
- [Unsloth](https://github.com/unslothai/unsloth) for efficient LLM fine-tuning
