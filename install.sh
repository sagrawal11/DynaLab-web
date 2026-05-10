#!/bin/bash

echo "Building Upside2 for $(uname -m) architecture..."

# Set up common environment variables
export UPSIDE_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MY_PYTHON="/opt/conda"
export PATH="$MY_PYTHON/bin:$PATH"
export PATH="$UPSIDE_HOME/obj:$PATH"
export PYTHONPATH="$UPSIDE_HOME/py:$PYTHONPATH"
export EIGEN_HOME="/usr/include/eigen3"

# Clean and build
rm -rf obj/*
cd obj

# CMake will detect architecture and use appropriate configuration
cmake ../src/ -DEIGEN3_INCLUDE_DIR=$EIGEN_HOME
make

echo "Build complete!"
