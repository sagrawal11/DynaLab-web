#!/bin/bash
set -e

# Source conda setup and activate environment
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env

# Prefer the bind-mounted workspace when present (dev container development).
# The image also contains a clone at /upside2-md, but that tree is not the
# checkout you are editing unless you are running a standalone docker run.
if [[ -z "${UPSIDE_HOME:-}" || ! -f "${UPSIDE_HOME}/start/Single_Replica.py" ]]; then
    if [[ -d /workspaces ]]; then
        for _ws in /workspaces/*/; do
            if [[ -f "${_ws}start/Single_Replica.py" && -f "${_ws}benchmarks/matrix.json" ]]; then
                export UPSIDE_HOME="${_ws%/}"
                break
            fi
        done
    fi
fi
export UPSIDE_HOME="${UPSIDE_HOME:-/upside2-md}"
export PATH="$UPSIDE_HOME/py:$UPSIDE_HOME/obj:$PATH"
export PYTHONPATH="$UPSIDE_HOME/py:$PYTHONPATH"
export MY_PYTHON="/opt/conda"
export EIGEN_HOME="/usr/include/eigen3"

# Platform-agnostic compiler settings
export CC=gcc
export CXX=g++

# If no arguments, start an interactive shell
if [ $# -eq 0 ]; then
    exec bash
else
    # Run user's command
    exec "$@"
fi
