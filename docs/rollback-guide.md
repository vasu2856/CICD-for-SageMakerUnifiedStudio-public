# Rollback Guide

← [Back to Main README](../README.md)

This guide explains how to recover from a bad deployment using the `destroy` and `deploy` commands — both manually and through automated rollback workflows.

---

## Overview

A "bad deployment" can mean different things:

- A workflow fails after deployment (broken Glue job, bad notebook, misconfigured Airflow DAG)
- A QuickSight dashboard is broken
- A deployment introduced a regression in a previously working stage and you need to revert to a known-good version of your application
- DataZone catalog entered an undesirable state

The SMUS CI/CD CLI supports two recovery strategies:

| Strategy | When to use | How |
|----------|-------------|-----|
| **Redeploy previous version** | You have a previous bundle or git state | `deploy` with the previous artifact |
| **Destroy and redeploy** | State is corrupted or you need a clean slate | `destroy` then `deploy` |

---

## Strategy 1: Redeploy Previous Version

If your deployment is bundle-based (using `aws-smus-cicd-cli bundle`), each bundle is a versioned artifact stored in S3. Rolling back is simply redeploying the previous bundle.

### Manual Rollback

```bash
# 1. Identify the previous good bundle in S3
aws s3 ls s3://your-bundle-bucket/bundles/ --recursive | sort

# 2. Download the previous bundle locally
aws s3 cp s3://your-bundle-bucket/bundles/MyApp-v1.2.0.zip ./artifacts/MyApp.zip

# 3. Deploy from the local bundle
#    (deploy picks up ./artifacts/MyApp.zip automatically)
aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml

# 4. Verify the rollback
aws-smus-cicd-cli monitor --manifest manifest.yaml --targets prod
```

### When This Is Enough

Redeploying a previous bundle is sufficient when:
- The issue is in application code (notebooks, Glue scripts, DAGs)
- S3 files are the primary deployed artifact
- The DataZone project and connections are still healthy
- No new AWS resources were created by the bad deployment that need cleaning up

### When This Is NOT Enough

A simple redeploy won't fully restore state if:
- The bad deployment created new AWS resources (Glue jobs, QuickSight dashboards) that will not be part of the updated bundle
- Workflow-created resources (e.g. Glue jobs) have stale configuration from the bad deployment
- You need a completely clean environment before redeploying

In those cases, use Strategy 2.

---

## Strategy 2: Destroy and Redeploy (Clean Slate)

This is the most complete rollback approach. It removes resources deployed by the bad version, then redeploys the known-good version from scratch. 

Note: resources created by other resources (ex: Bedrock Agent created by the SageMaker notebook) will still exist, so customers should clean up such resources manually.

### Step 1: Destroy the Bad Deployment

```bash
# Destroy all resources for the affected stage
aws-smus-cicd-cli destroy \
  --manifest manifest.yaml \
  --targets prod \
  --force
```

The destroy command will:
1. Validate all resources (read-only, no changes yet)
2. Print a full destruction plan
3. Stop any active Airflow workflow runs
4. Delete workflow-created resources (Glue jobs, etc.)
5. Delete Airflow workflows
6. Delete QuickSight dashboards, datasets, and data sources
7. Delete S3 objects at declared target paths
8. Delete catalog resources (if configured)
9. Delete the DataZone project (only if `project.create: true`)

> **Note:** If `project.create: false` in your manifest, the DataZone project is preserved. Only deployed content is removed. This is the typical case for rollbacks — you keep the project and just clean up the deployed resources.

### Step 2: Redeploy the Previous Good Version

```bash
# Option A: Redeploy from a previous bundle artifact
#   Download the specific versioned bundle, then deploy
aws s3 cp s3://your-bundle-bucket/bundles/MyApp-v1.2.0.zip ./artifacts/MyApp.zip
aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml

# Option B: Redeploy from a previous git commit
git checkout v1.2.0
aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml
```

### Step 3: Verify

```bash
# Check deployment status
aws-smus-cicd-cli monitor --manifest manifest.yaml --targets prod

# Run validation tests
aws-smus-cicd-cli test --manifest manifest.yaml --targets prod
```

---

## Rollback Decision Tree

```
Bad deployment detected
        │
        ▼
Did the bad deployment create new AWS resources
(Glue jobs, QuickSight dashboards, new workflows)?
        │
   Yes  │  No
        │   └──► Redeploy previous bundle/commit
        │         aws s3 cp s3://bucket/bundles/MyApp-prev.zip ./artifacts/MyApp.zip
        │         aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml
        ▼
Is the DataZone project still healthy
(connections reachable, project ACTIVE)?
        │
   Yes  │  No
        │   └──► Contact AWS support or recreate project manually
        │         then redeploy
        ▼
Destroy and redeploy:
  1. aws-smus-cicd-cli destroy --targets prod --force
  2. aws s3 cp s3://bucket/bundles/MyApp-prev.zip ./artifacts/MyApp.zip
     aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml
  3. aws-smus-cicd-cli test --targets prod
```

---

## Preserving State During Rollback

### Catalog Resources

If your manifest includes `deployment_configuration.catalog`, the destroy command will delete all project-owned catalog resources (glossaries, assets, data products, etc.). To skip catalog deletion during a rollback:

```yaml
# manifest.yaml — temporarily disable catalog deletion
stages:
  prod:
    deployment_configuration:
      catalog:
        disable: true   # Catalog resources will NOT be deleted by destroy
```

Then run destroy and re-enable catalog deployment before redeploying.

### DataZone Project

By default, `destroy` only deletes the project if `project.create: true`. If your manifest has `project.create: false` (the typical production setup), the project is always preserved during destroy — only deployed content is removed.

```yaml
stages:
  prod:
    project:
      name: prod-marketing
      create: false   # Project is never deleted by destroy
```

---

## Automated Rollback with GitHub Actions

For production environments, you can automate rollback as a GitHub Actions workflow that triggers on deployment failure.

### Workflow: Automated Rollback on Failure

Create `.github/workflows/rollback.yml`:

```yaml
name: Rollback Deployment

on:
  workflow_dispatch:
    inputs:
      stage:
        description: 'Stage to roll back (e.g. prod, test)'
        required: true
        default: 'prod'
      previous_bundle:
        description: 'S3 URI of the previous good bundle (leave empty to use latest tag)'
        required: false

jobs:
  rollback:
    name: "Rollback ${{ github.event.inputs.stage }}"
    runs-on: ubuntu-latest
    environment: aws-env-prod   # Requires manual approval for prod rollbacks

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-region: ${{ vars.AWS_REGION }}
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          role-session-name: smus-rollback

      - name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli

      - name: Destroy bad deployment
        run: |
          aws-smus-cicd-cli destroy \
            --manifest manifest.yaml \
            --targets ${{ github.event.inputs.stage }} \
            --force \
            --output JSON | tee destroy-output.json

      - name: Upload destroy output
        uses: actions/upload-artifact@v4
        with:
          name: destroy-output
          path: destroy-output.json

      - name: Redeploy previous version
        run: |
          BUNDLE="${{ github.event.inputs.previous_bundle }}"
          if [ -n "$BUNDLE" ]; then
            # Download the specific versioned bundle, then deploy
            aws s3 cp "$BUNDLE" ./artifacts/MyApp.zip
            aws-smus-cicd-cli deploy \
              --targets ${{ github.event.inputs.stage }} \
              --manifest manifest.yaml
          else
            # Fall back to latest git tag
            PREV_TAG=$(git describe --tags --abbrev=0 HEAD~1)
            echo "Rolling back to tag: $PREV_TAG"
            git checkout "$PREV_TAG"
            aws-smus-cicd-cli deploy \
              --targets ${{ github.event.inputs.stage }} \
              --manifest manifest.yaml
          fi

      - name: Validate rollback
        run: |
          aws-smus-cicd-cli test \
            --manifest manifest.yaml \
            --targets ${{ github.event.inputs.stage }}

      - name: Monitor post-rollback status
        run: |
          aws-smus-cicd-cli monitor \
            --manifest manifest.yaml \
            --targets ${{ github.event.inputs.stage }} \
            --output JSON | tee monitor-output.json
```

### Workflow: Auto-Rollback on Failed Deployment

This pattern automatically triggers rollback when a deployment job fails. Add it to your existing deployment workflow:

```yaml
name: Deploy with Auto-Rollback

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: "Deploy to Production"
    runs-on: ubuntu-latest
    environment: aws-env-prod
    outputs:
      deployed: ${{ steps.deploy.outputs.deployed }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-region: ${{ vars.AWS_REGION }}
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          role-session-name: smus-deploy

      - name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli

      - name: Deploy
        id: deploy
        run: |
          aws-smus-cicd-cli deploy \
            --targets prod \
            --manifest manifest.yaml
          echo "deployed=true" >> $GITHUB_OUTPUT

      - name: Run post-deployment tests
        id: tests
        run: |
          aws-smus-cicd-cli test \
            --manifest manifest.yaml \
            --targets prod

  rollback-on-failure:
    name: "Auto-Rollback on Failure"
    runs-on: ubuntu-latest
    environment: aws-env-prod
    needs: deploy
    # Only runs if the deploy job failed
    if: failure() && needs.deploy.outputs.deployed == 'true'

    steps:
      - uses: actions/checkout@v4
        with:
          # Check out the previous commit (before the bad deployment)
          ref: ${{ github.event.before }}

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-region: ${{ vars.AWS_REGION }}
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          role-session-name: smus-rollback

      - name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli

      - name: Destroy failed deployment
        run: |
          aws-smus-cicd-cli destroy \
            --manifest manifest.yaml \
            --targets prod \
            --force

      - name: Redeploy previous commit
        run: |
          aws-smus-cicd-cli deploy \
            --targets prod \
            --manifest manifest.yaml

      - name: Notify rollback
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "⚠️ Production rollback triggered for ${{ github.repository }}.\nCommit ${{ github.sha }} was rolled back to ${{ github.event.before }}."
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## Bundle-Based Rollback (Recommended for Production)

The preferred rollback strategy is bundle-based deployment, where each deployment creates a versioned artifact. This gives you instant rollback to any previous version without needing to re-run the build.

### How It Works

```
Commit A (v1.2.0) → bundle-v1.2.0.zip → deployed to prod ✅
Commit B (v1.3.0) → bundle-v1.3.0.zip → deployed to prod ❌ (bad)
                                          ↓
                                    Rollback: destroy prod
                                    then deploy bundle-v1.2.0.zip
```

### Setting Up Bundle-Based Deployment

In your `manifest.yaml`:

```yaml
bundlesDirectory: s3://your-bundle-bucket/bundles
```

In your deployment workflow, tag bundles with the git SHA or version:

```yaml
- name: Create bundle
  run: |
    aws-smus-cicd-cli bundle \
      --manifest manifest.yaml \
      --targets prod
    # Bundle is automatically uploaded to s3://your-bundle-bucket/bundles/MyApp.zip
    # Optionally copy with a versioned name:
    aws s3 cp \
      s3://your-bundle-bucket/bundles/MyApp.zip \
      s3://your-bundle-bucket/bundles/MyApp-${{ github.sha }}.zip
```

### Rollback to a Specific Version

```bash
# List available bundles
aws s3 ls s3://your-bundle-bucket/bundles/ | grep MyApp

# Destroy current deployment
aws-smus-cicd-cli destroy --targets prod --force

# Download the specific versioned bundle locally
aws s3 cp s3://your-bundle-bucket/bundles/MyApp-abc1234.zip ./artifacts/MyApp.zip

# Deploy — the CLI picks up ./artifacts/MyApp.zip automatically
aws-smus-cicd-cli deploy --targets prod --manifest manifest.yaml
```

---

## Rollback Checklist

Before triggering a rollback, work through this checklist:

- [ ] Identify the scope: which stage(s) are affected?
- [ ] Identify the last known-good version (versioned bundle in S3 or git commit/tag)
- [ ] Check if the DataZone project is still reachable (`aws-smus-cicd-cli describe --connect`)
- [ ] Decide whether a simple redeploy is sufficient or a destroy+redeploy is needed
- [ ] If using destroy: check if `deployment_configuration.catalog` needs `disable: true` to preserve catalog resources
- [ ] Notify stakeholders before starting rollback on production
- [ ] After rollback: run `aws-smus-cicd-cli test` to validate the restored state
- [ ] Document the incident: what failed, what was rolled back, and why

---

## Related Documentation

- **[CLI Commands Reference](cli-commands.md)** — Full `destroy` and `deploy` command documentation
- **[Bootstrap Actions](bootstrap-actions.md)** — Post-deployment actions that run during `deploy`
- **[GitHub Actions Integration](github-actions-integration.md)** — CI/CD setup and approval gates
- **[Deployment Metrics](pipeline-deployment-metrics.md)** — EventBridge events for monitoring deployments
