#!/bin/bash
# NLE-Bench Benchmark Runner
#
# This script provides a convenient way to run NLE-Bench benchmarks.
#
# Usage:
#   ./scripts/run_benchmark.sh [OPTIONS]
#
# Options:
#   -p, --provider    Provider: anthropic, openai, google, vllm (default: anthropic)
#   -m, --model       Model identifier
#   -t, --track       Track: canonical, open (default: canonical)
#   -l, --levels      Levels to run (comma-separated, e.g., L1,L2)
#   -r, --runs        Runs per scenario (default: 3)
#   -q, --quick       Quick mode (10 scenarios)
#   -o, --output      Output directory (default: results)
#   --vllm-url        vLLM server URL (default: http://localhost:8000/v1)
#   --reasoning-effort OpenAI reasoning effort: low, medium, high
#   -h, --help        Show this help message
#
# Environment variables:
#   ANTHROPIC_API_KEY - API key for Anthropic
#   OPENAI_API_KEY    - API key for OpenAI
#   GOOGLE_API_KEY    - API key for Google Gemini
#   VLLM_BASE_URL     - vLLM server URL
#
# Examples:
#   # Run with the Anthropic paper reference family
#   ./scripts/run_benchmark.sh -p anthropic -m claude-sonnet-4-6-2026-02-17
#
#   # Run with the OpenAI GPT-5.4 Responses API paper setting
#   ./scripts/run_benchmark.sh -p openai -m gpt-5.4 --reasoning-effort medium
#
#   # Run with local vLLM
#   ./scripts/run_benchmark.sh -p vllm -m Qwen/Qwen3-32B
#
#   # Quick mode with specific levels
#   ./scripts/run_benchmark.sh -p anthropic -m claude-sonnet-4-6-2026-02-17 -q -l L1,L2

set -e

# Default values
PROVIDER="anthropic"
MODEL=""
TRACK="canonical"
LEVELS=""
RUNS="3"
QUICK=""
OUTPUT="results"
VLLM_URL="${VLLM_BASE_URL:-http://localhost:8000/v1}"
REASONING_EFFORT="${OPENAI_REASONING_EFFORT:-}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--provider)
            PROVIDER="$2"
            shift 2
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -t|--track)
            TRACK="$2"
            shift 2
            ;;
        -l|--levels)
            LEVELS="$2"
            shift 2
            ;;
        -r|--runs)
            RUNS="$2"
            shift 2
            ;;
        -q|--quick)
            QUICK="--quick"
            shift
            ;;
        -o|--output)
            OUTPUT="$2"
            shift 2
            ;;
        --vllm-url)
            VLLM_URL="$2"
            shift 2
            ;;
        --reasoning-effort)
            REASONING_EFFORT="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,38p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set default models per provider
if [[ -z "$MODEL" ]]; then
    case $PROVIDER in
        anthropic)
            MODEL="claude-sonnet-4-6-2026-02-17"
            ;;
        openai)
            MODEL="gpt-5.4"
            ;;
        google)
            MODEL="gemini-3-flash-preview"
            ;;
        vllm)
            MODEL="Qwen/Qwen3-32B"
            ;;
    esac
fi

if [[ "$PROVIDER" == "openai" && "$MODEL" == gpt-5* && -z "$REASONING_EFFORT" ]]; then
    REASONING_EFFORT="medium"
fi

# Check API keys
case $PROVIDER in
    anthropic)
        if [[ -z "$ANTHROPIC_API_KEY" ]]; then
            echo "Error: ANTHROPIC_API_KEY environment variable not set"
            exit 1
        fi
        ;;
    openai)
        if [[ -z "$OPENAI_API_KEY" ]]; then
            echo "Error: OPENAI_API_KEY environment variable not set"
            exit 1
        fi
        ;;
    google)
        if [[ -z "${GOOGLE_API_KEY:-${GEMINI_API_KEY:-}}" ]]; then
            echo "Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set"
            exit 1
        fi
        ;;
esac

# Build command
CMD="python -m nlebench"
CMD="$CMD --provider $PROVIDER"
CMD="$CMD --model $MODEL"
CMD="$CMD --track $TRACK"
CMD="$CMD --runs $RUNS"
CMD="$CMD --output $OUTPUT"

if [[ -n "$LEVELS" ]]; then
    # Convert comma-separated to space-separated
    LEVELS_ARGS=$(echo "$LEVELS" | tr ',' ' ')
    CMD="$CMD --levels $LEVELS_ARGS"
fi

if [[ -n "$QUICK" ]]; then
    CMD="$CMD $QUICK"
fi

if [[ "$PROVIDER" == "vllm" ]]; then
    CMD="$CMD --vllm-url $VLLM_URL"
fi

if [[ "$PROVIDER" == "openai" && -n "$REASONING_EFFORT" ]]; then
    CMD="$CMD --reasoning-effort $REASONING_EFFORT"
fi

# Print configuration
echo "=============================================="
echo "NLE-Bench Runner"
echo "=============================================="
echo "Provider: $PROVIDER"
echo "Model:    $MODEL"
echo "Track:    $TRACK"
echo "Runs:     $RUNS"
echo "Output:   $OUTPUT"
if [[ -n "$LEVELS" ]]; then
    echo "Levels:   $LEVELS"
fi
if [[ -n "$QUICK" ]]; then
    echo "Mode:     Quick"
fi
if [[ "$PROVIDER" == "vllm" ]]; then
    echo "vLLM URL: $VLLM_URL"
fi
if [[ "$PROVIDER" == "openai" && -n "$REASONING_EFFORT" ]]; then
    echo "Reasoning: $REASONING_EFFORT"
fi
echo "=============================================="
echo ""
echo "Running: $CMD"
echo ""

# Execute
exec $CMD
