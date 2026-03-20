# Admin Quick Start

← [Back to Main README](../../README.md)


**Goal:** Understand and configure SMUS CI/CD infrastructure for data teams

**Audience:** Platform administrators and DevOps engineers setting up deployment pipelines

---

## Prerequisites

- ✅ AWS account with admin access
- ✅ SageMaker Unified Studio domain and project(s) created manually in the portal (the CLI cannot create these)
- ✅ SMUS domain must use IAM-based authentication — IdC-based domains are not yet supported
- ✅ Python 3.8+ and AWS CLI installed
- ✅ Understanding of AWS IAM and S3

---

## Overview

As an admin, you'll configure:
- **Deployment stages** - Test and Prod environments where data applications deploy
- **Project initialization** - Projects must be created manually in the SMUS portal before deploying
- **CI/CD pipelines** - GitHub Actions or similar automation
- **Monitoring** - Deployment validation and health checks

**Key concept:** A SMUS project is a deployment target. Multiple data applications can deploy to the same target using different deployment approaches (direct git-based, bundle-based, or hybrid).

---

## Step 1: Install the CLI

```bash
pip install aws-smus-cicd-cli
```

---

## Step 2: Understand Deployment Stages

A **stage** is a SMUS project where data applications deploy. Data teams typically use:
- **Dev** - Local development (optional deployment target, used for testing)
- **Test** - Integration testing and validation
- **Prod** - Production deployment

### Deployment Approaches

The CLI supports three deployment approaches:

1. **Direct Git-Based** - Deploy directly from git branches to stages (no bundle creation)
2. **Bundle-Based** - Create versioned bundles, then deploy them to stages (all content from bundle)
3. **Hybrid** - Create bundle for static content (data, configs), pull workflows from git branches per stage

**See more:** [Deployment Approaches Guide](../deployment-approaches.md)

### Stage Configuration

Each stage in `manifest.yaml` specifies:

```yaml
stages:
  test:
    domain:
      id: dzd_xxxxxxxxxxxx    # Option 1: domain ID (visible in the SMUS portal)
      # name: my-domain       # Option 2: domain name
      # tags:                 # Option 3: tag-based lookup
      #   purpose: my-tag
      region: us-east-1       # AWS region
    project:
      name: test-project      # SMUS project name
```

**Key points:**
- Identify your domain using `domain.id`, `domain.name`, or `domain.tags`
- The project must already exist in the SMUS domain before deploying
- Use the same project name across multiple applications to share resources
- Different applications can deploy to the same project

---

## Step 3: Set Up Multi-Stage Configuration

Create a reference `manifest.yaml` for your organization:

```yaml
applicationName: CustomerChurnModel

content:
  git:
    - repository: customer-churn-model
      url: https://github.com/myorg/customer-churn-model.git
  storage:
    - name: data-platform-workflows
      connectionName: default.s3_shared
      include:
        - 'workflows/'

stages:
  test:
    domain:
      name: my-domain
      region: us-east-1
    project:
      name: test-data-platform
    
  prod:
    domain:
      name: my-domain
      region: us-east-1
    project:
      name: prod-data-platform
```

**Note:** Dev project is typically created manually in the console by data teams.

---

## Step 4: Configure Project Connections

Connections define integrations with AWS services and data sources. They can be created automatically during deployment or manually via the console.

### Default Connections

SMUS projects automatically include these connections:
- `default.s3_shared` - Project S3 bucket
- `project.workflow_mwaa` - MWAA environment (if OnDemand Workflows enabled)
- `project.athena` - Athena workgroup
- `project.default_lakehouse` - Lakehouse connection

### Create Connections via Manifest

The recommended approach is to define connections in the bundle manifest under `bootstrap.connections`:

```yaml
stages:
  test:
    domain:
      name: my-domain
      region: us-east-1
    project:
      name: test-data-platform
    bootstrap:
      environments:
        - EnvironmentConfigurationName: 'OnDemand Workflows'
      
      connections:
        - name: s3-raw-data
          type: S3
          properties:
            s3Uri: "s3://raw-data-bucket/incoming/"
        
        - name: spark-etl
          type: SPARK_GLUE
          properties:
            glueVersion: "4.0"
            workerType: "G.2X"
            numberOfWorkers: 10
        
        - name: athena-analytics
          type: ATHENA
          properties:
            workgroupName: "analytics-workgroup"
        
        - name: redshift-warehouse
          type: REDSHIFT
          properties:
            storage:
              clusterName: "analytics-cluster"
            databaseName: "analytics"
            host: "analytics-cluster.abc123.us-east-1.redshift.amazonaws.com"
            port: 5439
```

### Supported Connection Types

#### S3 - Object Storage
```yaml
- name: s3-data-lake
  type: S3
  properties:
    s3Uri: "s3://my-data-bucket/data/"
```

#### SPARK_GLUE - Spark on AWS Glue
```yaml
- name: spark-processing
  type: SPARK_GLUE
  properties:
    glueVersion: "4.0"
    workerType: "G.1X"
    numberOfWorkers: 5
```

#### ATHENA - SQL Query Engine
```yaml
- name: athena-analytics
  type: ATHENA
  properties:
    workgroupName: "primary"
```

#### REDSHIFT - Data Warehouse
```yaml
- name: redshift-warehouse
  type: REDSHIFT
  properties:
    storage:
      clusterName: "analytics-cluster"
    databaseName: "analytics"
    host: "analytics-cluster.abc123.us-east-1.redshift.amazonaws.com"
    port: 5439
```

#### SPARK_EMR - Spark on EMR
```yaml
- name: spark-emr
  type: SPARK_EMR
  properties:
    computeArn: "arn:aws:emr-serverless:us-east-1:123456789012:/applications/00abc123def456"
    runtimeRole: "arn:aws:iam::123456789012:role/EMRServerlessExecutionRole"
```

#### MLFLOW - ML Experiment Tracking
```yaml
- name: mlflow-experiments
  type: MLFLOW
  properties:
    trackingServerName: "ml-tracking-server"
    trackingServerArn: "arn:aws:sagemaker:us-east-1:123456789012:mlflow-tracking-server/ml-tracking-server"
```

#### WORKFLOWS_MWAA - Apache Airflow
```yaml
- name: mwaa-workflows
  type: WORKFLOWS_MWAA
  properties:
    mwaaEnvironmentName: "production-airflow-env"
```

#### WORKFLOWS_SERVERLESS - Amazon MWAA Serverless
```yaml
- name: serverless-workflows
  type: WORKFLOWS_SERVERLESS
  properties: {}
```

**See more:** [Bundle Manifest Reference - Connections](../bundle-manifest.md#connections)

### Create Connections Manually (Console)

For existing projects, you can also create connections via the SMUS portal:

1. Navigate to SMUS project
2. Go to **Connections** tab
3. Click **Create connection**
4. Select connection type and configure properties

### Reference Connections in Workflows

Data teams reference these connections in their workflows using variable substitution:

```yaml
# workflows/data_processing.yaml
tasks:
  load_from_redshift:
    operator: "airflow.providers.amazon.aws.transfers.redshift_to_s3.RedshiftToS3Operator"
    redshift_conn_id: "${proj.connection.redshift_warehouse.id}"
    s3_bucket: "${proj.s3.root}"
    s3_key: "data/export.csv"
```

**See more:** [Substitutions and Variables Guide](../substitutions-and-variables.md)

---

## Step 5: Understand CLI Usage Across Stages

The CLI is used differently depending on your deployment approach:

### Direct Git-Based Deployment
```bash
# Deploy directly from git to test
aws-smus-cicd-cli deploy --stages test --manifest manifest.yaml

# Deploy to production
aws-smus-cicd-cli deploy --stages prod --manifest manifest.yaml
```

### Bundle-Based Deployment
```bash
# Create bundle (typically from dev)
aws-smus-cicd-cli bundle --manifest manifest.yaml --targets dev

# Deploy bundle to test
aws-smus-cicd-cli deploy --stages test --manifest manifest.yaml --manifest path/to/bundle.tar.gz

# Deploy same bundle to production
aws-smus-cicd-cli deploy --stages prod --manifest manifest.yaml --manifest path/to/bundle.tar.gz
```

### Hybrid Deployment
```bash
# Create bundle once (contains some content like data files, configs)
aws-smus-cicd-cli bundle --manifest manifest.yaml --targets dev

# Deploy to test: pulls workflows from release_test branch + data from bundle
aws-smus-cicd-cli deploy --stages test --manifest manifest.yaml --manifest path/to/bundle.tar.gz

# Deploy to prod: pulls workflows from release_prod branch + data from bundle
aws-smus-cicd-cli deploy --stages prod --manifest manifest.yaml --manifest path/to/bundle.tar.gz
```

### Validation Commands (All Approaches)
```bash
# Validate deployment
aws-smus-cicd-cli test --stages test --manifest manifest.yaml

# Check logs
aws-smus-cicd-cli logs --stages test --workflow my_workflow --live

# Monitor health
aws-smus-cicd-cli monitor --stages test --manifest manifest.yaml
```

**Key insight:** 
- Direct git-based: Fast iteration, everything from git branches
- Bundle-based: Versioned artifacts, everything from bundle
- Hybrid: Bundle for static content (data, configs), git branches for workflows

---

## Step 6: Set Up CI/CD Authentication (Optional)

If you want to automate deployments via CI/CD, configure authentication between your CI/CD platform and AWS.

### Quick Setup for GitHub Actions

```bash
# Deploy OIDC integration using CloudFormation
aws cloudformation deploy \
  --template-file tests/scripts/setup/1-account-setup/github-oidc-role.yaml \
  --stack-name smus-cli-github-integration \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    GitHubOrg=your-org \
    GitHubRepo=your-repo \
    GitHubEnvironment=aws-env
```

**Get the role ARN:**
```bash
aws cloudformation describe-stacks \
  --stack-name smus-cli-github-integration \
  --query 'Stacks[0].Outputs[?OutputKey==`RoleArn`].OutputValue' \
  --output text
```

### Other CI/CD Platforms

- **GitLab CI:** [GitLab AWS OIDC](https://docs.gitlab.com/ee/ci/cloud_services/aws/)
- **Azure DevOps:** [Azure AWS Connection](https://learn.microsoft.com/en-us/azure/devops/pipelines/library/connect-to-azure)
- **Jenkins:** Use AWS credentials plugin

### Required Permissions

> **⚠️ TODO:** Document minimum required IAM permissions.
> 
> **Current reference:** See `tests/scripts/setup/1-account-setup/github-oidc-role.yaml`

**For detailed CI/CD setup:**
- [GitHub Actions Workflows](../../git-templates/) - Pre-built templates
- [Application Guide](../github-workflow-application-guide.md) - For data teams
- [DevOps Guide](../github-workflow-devops-guide.md) - For platform teams

---

## Step 7: Set Up CI/CD Workflows (Optional)

Automate deployments using your CI/CD platform. The SMUS CI/CD CLI commands are the same across all platforms.

### GitHub Actions - Direct Git-Based Deployment

```yaml
name: Deploy Data Application (Direct)

on:
  push:
    branches: [main, release_test, release_prod]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: arn:aws:iam::123456789:role/GitHubActionsRole
          aws-region: us-east-1
      
      - name: Deploy to Test
        if: github.ref == 'refs/heads/release_test'
        run: aws-smus-cicd-cli deploy --stages test --manifest manifest.yaml
      
      - name: Deploy to Production
        if: github.ref == 'refs/heads/release_prod'
        run: aws-smus-cicd-cli deploy --stages prod --manifest manifest.yaml
      
      - name: Validate Deployment
        run: aws-smus-cicd-cli test --stages test --manifest manifest.yaml
```

### GitHub Actions - Bundle-Based Deployment

```yaml
name: Deploy Data Application (Bundle)

on:
  push:
    branches: [main]

jobs:
  deploy-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli- name: Install SMUS CI/CD CLI
        run: pip install aws-smus-cicd-cli
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: arn:aws:iam::123456789:role/GitHubActionsRole
          aws-region: us-east-1
      
      - name: Create Bundle
        run: aws-smus-cicd-cli bundle --manifest manifest.yaml --targets dev
      
      - name: Upload Bundle
        uses: actions/upload-artifact@v3
        with:
          name: application-bundle
          path: "*.tar.gz"
      
      - name: Deploy to Test
        run: aws-smus-cicd-cli deploy --stages test --manifest manifest.yaml --manifest *.tar.gz
      
      - name: Validate Deployment
        run: aws-smus-cicd-cli test --stages test --manifest manifest.yaml

  deploy-prod:
    needs: deploy-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v3
      
      - name: Download Bundle
        uses: actions/download-artifact@v3
        with:
          name: application-bundle
      
      - name: Deploy to Production
        run: aws-smus-cicd-cli deploy --stages prod --manifest manifest.yaml --manifest *.tar.gz
      
      - name: Monitor Production
        run: aws-smus-cicd-cli monitor --stages prod --manifest manifest.yaml
```

**For complete CI/CD setup:**
- **GitHub Actions:** See [git-templates/](../../git-templates/) for pre-built workflows
  - `direct-branch/` - Direct git-based deployment
  - `bundle-based/` - Bundle-based deployment
  - `hybrid-bundle-branch/` - Hybrid approach
- **Other platforms:** Adapt the CLI commands to your platform's syntax

**Key insight:** CI/CD just automates the CLI commands you'd run manually.

**See more:** [GitHub Actions Integration Guide](../github-actions-integration.md)

---

## Step 8: Validate Deployment with Monitoring

After deployment, use these commands to verify everything works:

### Check Deployment Status
```bash
# View overall bundle health
aws-smus-cicd-cli monitor --stages test --manifest manifest.yaml
```

**Output:**
```
Target: test
Project: test-data-platform
Status: ✓ Healthy

Workflows:
  ✓ metrics_etl (Active, Last run: Success)
  ✓ model_training (Active, Last run: Success)

Storage:
  ✓ workflows/ (3 files synced)

Connections:
  ✓ default.s3_shared
  ✓ project.workflow_mwaa
```

### View Workflow Logs
```bash
# Live logs for specific workflow
aws-smus-cicd-cli logs --stages test --workflow metrics_etl --live

# Historical logs
aws-smus-cicd-cli logs --stages test --workflow metrics_etl --date 2025-01-13
```

### Run Tests
```bash
# Execute validation tests
aws-smus-cicd-cli test --stages test --manifest manifest.yaml
```

**Output:**
```
Running tests for target: test

✓ Workflow files validated
✓ Connections accessible
✓ S3 storage accessible
✓ MWAA environment healthy

All tests passed
```

---

## Step 9: Set Up Monitoring and Metrics Integration

### CloudWatch Integration

The CLI automatically creates CloudWatch metrics for deployments:

```bash
# View deployment metrics
aws cloudwatch get-metric-statistics \
  --namespace SMUS/CICD \
  --metric-name DeploymentSuccess \
  --dimensions Name=Target,Value=test \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-13T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

### Create CloudWatch Dashboard

```bash
# Create monitoring dashboard
aws cloudwatch put-dashboard \
  --dashboard-name SMUS-CICD-Monitor \
  --dashboard-body file://dashboard.json
```

**dashboard.json:**
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["SMUS/CICD", "DeploymentSuccess", {"stat": "Sum"}],
          [".", "DeploymentFailure", {"stat": "Sum"}]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Deployment Status"
      }
    }
  ]
}
```

### Set Up Alerts

```bash
# Create SNS topic for alerts
aws sns create-topic --name smus-cicd-alerts

# Create alarm for deployment failures
aws cloudwatch put-metric-alarm \
  --alarm-name smus-deployment-failures \
  --alarm-description "Alert on SMUS deployment failures" \
  --metric-name DeploymentFailure \
  --namespace SMUS/CICD \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789:smus-cicd-alerts
```

---

## Step 10: Document for Data Teams

Create team documentation explaining the setup:

**`docs/deployment-guide.md`:**
```markdown
# Data Application Deployment Guide

## Overview
Our SMUS projects are configured as deployment stages:
- **test-data-platform** - Testing and validation
- **prod-data-platform** - Production deployment

Multiple data applications can deploy to the same project.

## Deployment Process
1. Develop in your dev project
2. Create bundle: `aws-smus-cicd-cli bundle --manifest manifest.yaml --targets dev`
3. Push to GitHub → Automatic deployment to test
4. After validation → Automatic deployment to prod

## Monitoring Your Deployment
- Check status: `aws-smus-cicd-cli monitor --stages test --manifest manifest.yaml`
- View logs: `aws-smus-cicd-cli logs --stages test --workflow YOUR_WORKFLOW --live`
- Run tests: `aws-smus-cicd-cli test --stages test --manifest manifest.yaml`

## Support
- Slack: #data-platform-support
- Email: platform-team@example.com
```

---

## Next Steps

### For Data Teams
- **[Data Team Quick Start](quickstart.md)** - Guide for building and deploying applications

### Advanced Configuration
- **[Bundle Manifest Reference](../bundle-manifest.md)** - Complete YAML specification
- **[CLI Commands Reference](../cli-commands.md)** - All available commands
- **[Monitoring and Metrics](../monitoring-and-metrics.md)** - Detailed monitoring setup

### Examples
- See [examples directory](../../examples/) for complete working examples

---

## Key Takeaways

1. **Projects are deployment stages** - One SMUS project can host multiple data applications
2. **Three deployment approaches** - Direct git-based, bundle-based, or hybrid
3. **Projects must exist before deploying** - Create projects manually in the SMUS portal before first deployment
4. **Monitoring is essential** - Use `monitor`, `logs`, and `test` commands to validate deployments
5. **CI/CD automates flow** - GitHub Actions handles test → prod progression

**Questions?** Contact the platform team for support.
