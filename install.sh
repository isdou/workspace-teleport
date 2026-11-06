#!/usr/bin/env bash
set -e

INSTALL_DIR="${HOME}/.local/bin"
mkdir -p "${INSTALL_DIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing workspace-teleport..."

if [ -f "${SCRIPT_DIR}/workspace_teleport/cli.py" ]; then
    # Local install
    pip3 install -e "${SCRIPT_DIR}" || {
        echo "pip install failed, setting up direct runner..."
        cat << 'EOF' > "${INSTALL_DIR}/workspace-teleport"
#!/usr/bin/env bash
python3 -m workspace_teleport.cli "$@"
EOF
        chmod +x "${INSTALL_DIR}/workspace-teleport"
    }
else
    # Remote one-liner install
    REPO_URL="https://github.com/isdou/workspace-teleport.git"
    CLONE_DIR="${HOME}/.workspace-teleport"
    if [ -d "${CLONE_DIR}" ]; then
        git -C "${CLONE_DIR}" pull
    else
        git clone "${REPO_URL}" "${CLONE_DIR}"
    fi
    pip3 install -e "${CLONE_DIR}" || {
        ln -sf "${CLONE_DIR}/workspace_teleport/cli.py" "${INSTALL_DIR}/workspace-teleport"
    }
fi

echo "==> workspace-teleport installed successfully!"
echo "    Run 'workspace-teleport --help' to get started."
