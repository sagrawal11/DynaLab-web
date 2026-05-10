#!/bin/bash
# .devcontainer/post-create.sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting Post-Create Setup ---"

# --- Verify the conda env is healthy, recreate if not ---
# Guards against a half-baked /opt/conda/envs/upside2-env that can be left
# behind by a partial conda env-create during image build (see Dockerfile).
echo "Verifying upside2-env conda environment..."
ENV_PATH=/opt/conda/envs/upside2-env
NEEDS_RECREATE=0
if [ ! -d "$ENV_PATH/conda-meta" ]; then
    echo "  upside2-env is missing conda-meta; will recreate."
    NEEDS_RECREATE=1
elif ! "$ENV_PATH/bin/python" -c "import flask, sklearn, mdtraj, tables, matplotlib, prody, pkg_resources, requests" 2>/dev/null; then
    echo "  upside2-env is missing required packages; will recreate."
    NEEDS_RECREATE=1
fi
if [ "$NEEDS_RECREATE" = "1" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    sudo rm -rf "$ENV_PATH"
    conda env create -f "$SCRIPT_DIR/environment.yml"
    sudo chown -R user:user /opt/conda
    # Belt-and-suspenders setuptools pin: prody 2.4.1 imports pkg_resources
    # at module load time, but setuptools 81+ removed it from the dist. We
    # already pin setuptools<81 in environment.yml, but pip-forcing it here
    # guards against any future channel that ships a newer setuptools.
    "$ENV_PATH/bin/pip" install --force-reinstall 'setuptools<81'
    "$ENV_PATH/bin/python" -c "import flask, sklearn, mdtraj, tables, matplotlib, prody, pkg_resources, requests" \
        || { echo "ERROR: upside2-env recreate succeeded but imports still fail." >&2; exit 1; }
    echo "  upside2-env recreated."
else
    echo "  upside2-env looks healthy."
fi

# --- Build the C++ Code ---
echo "Setting up build environment for C++ compilation..."
export EIGEN_HOME=/usr/include/eigen3

echo "Building Upside C++ code..."
sudo ./install.sh

echo "--- Post-Create Setup Complete ---"

# --- Configure Shell for Interactive Use ---
echo "Configuring .bashrc for interactive shells..."
echo '' >> ~/.bashrc
echo '# >>> conda initialize >>>' >> ~/.bashrc
echo '# !! Contents within this block are managed by '\''conda init'\'' !!' >> ~/.bashrc
echo '__conda_setup="$('\'/opt/conda/bin/conda\'' '\''shell.bash'\'' '\''hook'\'' 2> /dev/null)"' >> ~/.bashrc
echo 'if [ $? -eq 0 ]; then' >> ~/.bashrc
echo '    eval "$__conda_setup"' >> ~/.bashrc
echo 'else' >> ~/.bashrc
echo '    if [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then' >> ~/.bashrc
echo '        . "/opt/conda/etc/profile.d/conda.sh"' >> ~/.bashrc
echo '    else' >> ~/.bashrc
echo '        export PATH="/opt/conda/bin:$PATH"' >> ~/.bashrc
echo '    fi' >> ~/.bashrc
echo 'fi' >> ~/.bashrc
echo 'unset __conda_setup' >> ~/.bashrc
echo '# <<< conda initialize <<<' >> ~/.bashrc
echo '' >> ~/.bashrc
echo '# Activate the default conda environment' >> ~/.bashrc
echo 'conda activate upside2-env' >> ~/.bashrc
