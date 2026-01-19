#!/bin/bash
#
# Setup script for GitHub Actions self-hosted runner on HPC cluster
#
# Prerequisites:
# - Access to sbatch command
# - Conda environment at /opt/conda/envs/alphafold3
# - GitHub repo with Actions enabled
#
# Usage:
#   ./setup_runner.sh <GITHUB_REPO_URL> <RUNNER_TOKEN>
#
# Get RUNNER_TOKEN from:
#   Repo Settings > Actions > Runners > New self-hosted runner
#

set -e

REPO_URL="${1:-}"
RUNNER_TOKEN="${2:-}"
RUNNER_DIR="${HOME}/actions-runner"
RUNNER_NAME="af3-runner-$(hostname)"
RUNNER_LABELS="self-hosted,af3-runner"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check arguments
if [ -z "$REPO_URL" ] || [ -z "$RUNNER_TOKEN" ]; then
    echo "Usage: $0 <GITHUB_REPO_URL> <RUNNER_TOKEN>"
    echo ""
    echo "Example:"
    echo "  $0 https://github.com/username/protein-competition ABCDEF123456"
    echo ""
    echo "Get RUNNER_TOKEN from:"
    echo "  Repo Settings > Actions > Runners > New self-hosted runner"
    exit 1
fi

# Check prerequisites
log_info "Checking prerequisites..."

if ! command -v sbatch &> /dev/null; then
    log_error "sbatch not found. Must run on HPC login node."
    exit 1
fi

if [ ! -d "/opt/conda/envs/alphafold3" ]; then
    log_warn "Conda environment /opt/conda/envs/alphafold3 not found."
    log_warn "AF3 jobs may fail. Continue anyway? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        exit 1
    fi
fi

# Create runner directory
log_info "Creating runner directory at ${RUNNER_DIR}..."
mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

# Download latest runner
log_info "Downloading GitHub Actions runner..."
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep -oP '"tag_name": "v\K[^"]+')
curl -sL "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" -o runner.tar.gz
tar xzf runner.tar.gz
rm runner.tar.gz

# Configure runner
log_info "Configuring runner..."
./config.sh \
    --url "${REPO_URL}" \
    --token "${RUNNER_TOKEN}" \
    --name "${RUNNER_NAME}" \
    --labels "${RUNNER_LABELS}" \
    --unattended \
    --replace

# Create systemd service file (user-level)
log_info "Creating systemd user service..."
mkdir -p "${HOME}/.config/systemd/user"

cat > "${HOME}/.config/systemd/user/github-runner.service" << EOF
[Unit]
Description=GitHub Actions Runner
After=network.target

[Service]
Type=simple
WorkingDirectory=${RUNNER_DIR}
ExecStart=${RUNNER_DIR}/run.sh
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Enable lingering for user services to run without login
log_info "Enabling user service..."
loginctl enable-linger $(whoami) 2>/dev/null || log_warn "Could not enable lingering. Service may stop on logout."

systemctl --user daemon-reload
systemctl --user enable github-runner.service

log_info "========================================"
log_info "Setup complete!"
log_info "========================================"
echo ""
echo "To start the runner:"
echo "  systemctl --user start github-runner.service"
echo ""
echo "To check status:"
echo "  systemctl --user status github-runner.service"
echo ""
echo "To view logs:"
echo "  journalctl --user -u github-runner.service -f"
echo ""
echo "Or run manually:"
echo "  cd ${RUNNER_DIR} && ./run.sh"
echo ""
log_info "Runner will appear in GitHub repo Settings > Actions > Runners"
