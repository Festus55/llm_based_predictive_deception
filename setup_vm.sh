#!/bin/bash

set -e

REPO_ROOT="${REPO_ROOT:-/home/person/repo}"
COWRIE_USER="cowrie"
CS_USER="person"
COWRIE_HOME="/home/${COWRIE_USER}"
CS_PORT=2222
LLM_PORT=2223
STD_PORT=2224

# installing cowrie dependencies..
apt-get update
apt-get install -y git python3-pip python3-venv python3-minimal build-essential libssl-dev libffi-dev libpython3-dev authbind

adduser --disabled-password "${COWRIE_USER}"

# connection switcher (as systemd service) (user person)
cp "${REPO_ROOT}/vm-with-cowrie-honeypot/connection_switcher.py" "/home/${CS_USER}/connection_switcher.py"
chown "${CS_USER}:${CS_USER}" "/home/${CS_USER}/connection_switcher.py"
chmod 0644 "/home/${CS_USER}/connection_switcher.py"

cat >/etc/systemd/system/connection-switcher.service <<EOF
[Unit]
Description=Connection Switcher for Cowrie
After=network.target
[Service]
User=${CS_USER}
WorkingDirectory=/home/${CS_USER}
ExecStart=/usr/bin/python3 /home/${CS_USER}/connection_switcher.py
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now connection-switcher

# because we need cowrie standard and cowrie with LLM
setup_cowrie_instance() {
  local name="$1" port="$2" with_llm="$3"
  local inst_dir="${COWRIE_HOME}/${name}"

  sudo -u "${COWRIE_USER}" bash -c "
    cd ${COWRIE_HOME}
    git clone https://github.com/cowrie/cowrie ${name}
    cd ${inst_dir}
    python3 -m venv cowrie-env
    source cowrie-env/bin/activate
    pip install --upgrade pip
    pip install -e .
    pip install treq pikepdf reportlab
  "

  # cowrie.cfg
  cp "${inst_dir}/etc/cowrie.cfg.dist" "${inst_dir}/etc/cowrie.cfg"
  sed -i "s|^listen_endpoints.*|listen_endpoints = tcp:${port}:interface=0.0.0.0|" "${cfg}"

  if [ "${with_llm}" = "yes" ]; then
    # LLM instance: modified shell + commands + fs + templates
    cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/shell/honeypot.py" "${inst_dir}/src/cowrie/shell/honeypot.py"
    mkdir -p "${inst_dir}/src/cowrie/shell/templates"
    cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/shell/templates/template.json" "${inst_dir}/src/cowrie/shell/templates/template.json"
  fi

  # both instances have a new fs.py
  cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/data/fs.pickle" "${inst_dir}/src/cowrie/data/fs.pickle"
  cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/commands/curl.py" "${inst_dir}/src/cowrie/commands/curl.py"
  cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/commands/wget.py" "${inst_dir}/src/cowrie/commands/wget.py"
  cp "${REPO_ROOT}/vm-with-cowrie-honeypot/cowrie/src/cowrie/commands/chmod.py" "${inst_dir}/src/cowrie/commands/chmod.py"

  chown -R "${COWRIE_USER}:${COWRIE_USER}" "${inst_dir}"
}

# setting up the cowrie instances
setup_cowrie_instance "cowrie" "${LLM_PORT}" "yes"
setup_cowrie_instance "cowrie-standard" "${STD_PORT}" "no"

# starting the cowries
sudo -u "${COWRIE_USER}" bash -c "
  cd ${COWRIE_HOME}/cowrie
  source cowrie-env/bin/activate
  cowrie start
"
sudo -u "${COWRIE_USER}" bash -c "
  cd ${COWRIE_HOME}/cowrie-standard
  source cowrie-env/bin/activate
  cowrie start
"

echo "VM setup complete with connection switcher running as ${SWITCH_USER} and cowrie instances running as ${COWRIE_USER}."
