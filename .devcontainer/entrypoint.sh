#!/bin/bash
set -e

# Source conda setup and activate environment
source /opt/conda/etc/profile.d/conda.sh
conda activate upside2-env

# Universal environment variables (no architecture-specific paths)
export UPSIDE_HOME="/upside2-md"
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
