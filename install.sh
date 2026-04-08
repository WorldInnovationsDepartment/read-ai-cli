#!/usr/bin/env bash
# Read AI CLI — install into isolated venv
set -e

VENV_DIR="${READAI_VENV:-$HOME/.venvs/read-ai}"
REPO="git+https://github.com/WorldInnovationsDepartment/read-ai-cli.git"

echo "🎙️  Installing Read AI CLI..."
echo ""

# Create venv
if [ -d "$VENV_DIR" ]; then
    echo "→ Venv exists at $VENV_DIR, upgrading..."
else
    echo "→ Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# Install
echo "→ Installing read-ai-cli..."
"$VENV_DIR/bin/pip" install --upgrade "$REPO" --quiet

# Verify
"$VENV_DIR/bin/readai" --help > /dev/null 2>&1

echo ""
echo "✓ Installed! Binary: $VENV_DIR/bin/readai"
echo ""

# Detect shell config
if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.bashrc"
fi

echo "To use 'readai' without activating the venv, run:"
echo ""
echo "  echo 'alias readai=\"$VENV_DIR/bin/readai\"' >> $SHELL_RC && source $SHELL_RC"
echo ""
