#!/bin/bash

# Cleanup Script for SMUS CICD Demo Resources
# This script cleans up resources created during the full pipeline lifecycle demo

set -e

echo "🧹 SMUS CICD Demo Resource Cleanup"
echo "=================================="

# Configuration
PIPELINE_FILE="${1:-DemoMarketingPipeline.yaml}"
DOMAIN_NAME="${2:-cicd-test-domain}"
PROJECT_NAME="${3:-dev-marketing}"

echo "Pipeline File: $PIPELINE_FILE"
echo "Domain Name: $DOMAIN_NAME"
echo "Project Name: $PROJECT_NAME"
echo ""

# Check if CLI is installed
if ! command -v aws-smus-cicd-cli &> /dev/null; then
    echo "❌ aws-smus-cicd-cli not found. Please install it first:"
    echo "   cd ."
    echo "   pip install -e ."
    exit 1
fi

# Check if pipeline file exists
if [ ! -f "$PIPELINE_FILE" ]; then
    echo "❌ Pipeline file not found: $PIPELINE_FILE"
    echo "Available pipeline files:"
    ls -1 *.yaml 2>/dev/null || echo "  No .yaml files found"
    exit 1
fi

echo "🔍 Checking existing resources..."

# List current targets to see what exists
echo ""
echo "Current pipeline targets:"
aws-smus-cicd-cli describe --bundle "$PIPELINE_FILE" --targets || echo "  No targets found or pipeline invalid"

echo ""
echo "🗑️  Cleaning up demo resources..."
echo ""
echo "ℹ️  Use 'destroy' to remove all deployed resources (S3, Airflow, QuickSight, Glue, catalog)."
echo ""

# Destroy all deployed resources for test target (most common demo target)
echo "Destroying test target resources..."
aws-smus-cicd-cli destroy \
  --manifest "$PIPELINE_FILE" \
  --targets test \
  --force || echo "  No test target to clean up"

# Destroy staging target if it exists
echo ""
echo "Destroying staging target resources..."
aws-smus-cicd-cli destroy \
  --manifest "$PIPELINE_FILE" \
  --targets staging \
  --force || echo "  No staging target to clean up"

# Destroy prod target if it exists
echo ""
echo "Destroying prod target resources..."
aws-smus-cicd-cli destroy \
  --manifest "$PIPELINE_FILE" \
  --targets prod \
  --force || echo "  No prod target to clean up"

# Destroy any other common demo targets
echo ""
echo "Destroying other demo targets..."
for target in demo example marketing analytics; do
    aws-smus-cicd-cli destroy \
      --manifest "$PIPELINE_FILE" \
      --targets "$target" \
      --force 2>/dev/null || echo "  No $target target to clean up"
done

echo ""
echo "✅ Cleanup completed!"
echo ""
echo "📋 Summary:"
echo "  - Attempted cleanup of common demo targets: test, staging, prod, demo, example, marketing, analytics"
echo "  - Use --force flag was used to avoid confirmation prompts"
echo "  - Errors for non-existent targets are expected and ignored"
echo ""
echo "🔍 To verify cleanup, run:"
echo "  aws-smus-cicd-cli describe --bundle $PIPELINE_FILE --targets --connect"
echo ""
echo "💡 To clean up specific targets manually:"
echo "  aws-smus-cicd-cli destroy --manifest $PIPELINE_FILE --targets <target-name> --force"
