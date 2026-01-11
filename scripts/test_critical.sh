#!/bin/bash
# scripts/test_critical.sh
# Critical Reliability Gate Test Runner for Linux/Mac
#
# Usage:
#   ./scripts/test_critical.sh          # Run critical tests
#   ./scripts/test_critical.sh -v       # Run with verbose output
#   ./scripts/test_critical.sh --fast   # Run with --reuse-db for speed
#
# Exit codes:
#   0 = All critical tests passed
#   1 = One or more critical tests failed

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Parse arguments
VERBOSE=false
FAST=false

for arg in "$@"; do
    case $arg in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --fast)
            FAST=true
            shift
            ;;
        -h|--help)
            echo "Critical Reliability Gate Test Runner"
            echo ""
            echo "Usage:"
            echo "    ./scripts/test_critical.sh [options]"
            echo ""
            echo "Options:"
            echo "    -v, --verbose    Show detailed test output"
            echo "    --fast           Use --reuse-db for faster execution"
            echo "    -h, --help       Show this help message"
            echo ""
            echo "Examples:"
            echo "    ./scripts/test_critical.sh"
            echo "    ./scripts/test_critical.sh -v"
            echo "    ./scripts/test_critical.sh --fast -v"
            exit 0
            ;;
    esac
done

echo ""
echo -e "${CYAN}======================================${NC}"
echo -e "${CYAN}  CRITICAL RELIABILITY GATE${NC}"
echo -e "${CYAN}======================================${NC}"
echo ""
echo -e "${YELLOW}Running critical tests...${NC}"
echo -e "${YELLOW}These tests must ALL pass to deploy.${NC}"
echo ""

# Build pytest command
PYTEST_ARGS="-m critical --maxfail=1 --strict-markers --strict-config"

if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -v --tb=short -ra"
else
    PYTEST_ARGS="$PYTEST_ARGS -q"
fi

if [ "$FAST" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS --reuse-db"
fi

# Run pytest and capture exit code
START_TIME=$(date +%s)
set +e  # Don't exit on error
python -m pytest $PYTEST_ARGS
EXIT_CODE=$?
set -e
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo -e "${GRAY}--------------------------------------${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CRITICAL TESTS PASSED${NC}"
    echo -e "${GRAY}  Duration: ${DURATION} seconds${NC}"
    echo -e "${GREEN}  Safe to deploy!${NC}"
else
    echo -e "${RED}✗ CRITICAL TESTS FAILED${NC}"
    echo -e "${GRAY}  Duration: ${DURATION} seconds${NC}"
    echo -e "${RED}  DO NOT DEPLOY until fixed!${NC}"
    echo ""
    echo -e "${YELLOW}To debug, run with -v flag:${NC}"
    echo -e "${YELLOW}  ./scripts/test_critical.sh -v${NC}"
fi

echo -e "${GRAY}--------------------------------------${NC}"
echo ""

exit $EXIT_CODE

