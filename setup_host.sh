#!/bin/bash

set -e

SSH_PORT=4321
VM_NAME="vm-honeypot"
VM_IP="192.168.122.17"

REPO_ROOT=$(pwd)
PUB_IFACE=$(ip -br addr | awk '/UP/ {print $1}')

echo "--- Starting host setup on interface: $PUB_IFACE ---"

# KVM and Libvirt
echo "[+] Installing KVM and libvirt..."
apt-get update && apt-get upgrade -y
apt-get install -y qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virtinst python3-pip git curl gnupg
systemctl enable --now libvirtd
virsh net-autostart default
virsh net-start default

# SSH
echo "[+] Changing host SSH port to $SSH_PORT..."
sed -i "s/#Port 22/Port $SSH_PORT/" /etc/ssh/sshd_config
systemctl reload ssh

# Firewalld
echo "[+] Configuring firewalld..."
echo 'net.ipv4.ip_forward=1' | tee /etc/sysctl.d/99-ip-forward.conf
sysctl --system

systemctl stop ufw && systemctl disable ufw
apt-get install -y firewalld
systemctl enable --now firewalld

firewall-cmd --permanent --zone=public --add-interface=$PUB_IFACE

# tcp ports
firewall-cmd --permanent --zone=public \
    --add-port={9000/tcp,6443/tcp,8008/tcp,4321/tcp,22/tcp,6453/tcp}
# udp port
firewall-cmd --permanent --zone=public --add-port=51820/udp

firewall-cmd --permanent --zone=public --add-masquerade
firewall-cmd --permanent --zone=public --add-forward

# port forw to let hackers in the VM
firewall-cmd --permanent --zone=public \
    --add-forward-port=port=22:proto=tcp:toport=2222:toaddr=$VM_IP

# port forw for VM access
firewall-cmd --permanent --zone=public \
    --add-forward-port=port=6453:proto=tcp:toport=22:toaddr=$VM_IP

# libvirt internal zone
firewall-cmd --permanent --zone=libvirt --add-port=8000/tcp # LLM API
firewall-cmd --permanent --zone=libvirt --add-port=8082/tcp # Canary Server

firewall-cmd --reload
echo "[+] Firewall configured."

# MongoDB setup
echo "[+] Installing MongoDB..."
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
   sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg \
   --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.2 main" | sudo tee /etc/apt/sources.list.d/mongodb-org-8.2.list

apt-get update
apt-get install -y mongodb-org
systemctl enable --now mongod

# Listener setup
echo "[+] Setting up Webhook Listener..."
pip3 install flask pymongo gunicorn paramiko --break-system-packages

# systemd service for the listener so it stays up
cat <<EOF > /etc/systemd/system/honeypot-listener.service
[Unit]
Description=Honeypot Webhook Listener
After=network.target mongod.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_ROOT
ExecStart=/bin/bash $REPO_ROOT/listener/start-canary-listener-ingester.sh
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now honeypot-listener

# Canarytokens Docker setup
echo "[+] Setting up Canarytokens..."
# Install Docker
curl -fsSL https://get.docker.com | sh

cd $REPO_ROOT
cd canarytokens-docker

echo "IMPORTAN!! Edit manually 'frontend.env' and 'switchboard.env'"

docker compose up -d

# LLM Server Setup
echo "[+] Installing vLLM..."
pip3 install vllm


# start VM Installation
echo "[+] Starting VM Installation..."
echo "!! MANUAL ACTION:"
echo "   - set the Static IP to $VM_IP"
echo "   - install 'SSH Server'"
echo "   - create user 'person'"
echo "   - 'Ctrl+]' to exit the console if needed"

read -p "press Enter to launch virt-install..."

virt-install \
    --virt-type kvm \
    --name $VM_NAME \
    --location https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/ \
    --os-variant debian12 \
    --disk size=100 \
    --memory 8192 \
    --vcpus 6 \
    --network network=default,model=virtio \
    --graphics none \
    --console pty,target_type=serial \
    --extra-args "console=ttyS0,115200n8"
