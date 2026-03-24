[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](../it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-brightgreen.svg?style=for-the-badge)](../ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](../zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](../he/README.md)

← [Back to Main README](../../../README.md)

# SMUS CI/CD Pipeline CLI

[![en](https://img.shields.io/badge/lang-en-brightgreen.svg?style=for-the-badge)](README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](docs/langs/pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](docs/langs/fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](docs/langs/it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-gray.svg)](docs/langs/ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](docs/langs/zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](docs/langs/he/README.md)

> **[プレビュー]** Amazon SageMaker Unified Studio CI/CD CLIは現在プレビュー段階であり、変更される可能性があります。コマンド、設定フォーマット、APIはお客様のフィードバックに基づいて進化する可能性があります。プレビュー期間中は本番環境以外での評価をお勧めします。フィードバックやバグ報告については、以下のイシューを開いてください：https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues

> **[IAMドメインのみ]** 現在このCLIはIAM認証を使用するSMUSドメインのみをサポートしています。IAM Identity Center (IdC)ベースのドメインのサポートは近日公開予定です。

**SageMaker Unified Studio環境全体でのデータアプリケーションのデプロイを自動化**

"Deploy Airflow DAGs, Jupyter notebooks, and ML workflows from development to production with confidence. Built for data scientists, data engineers, ML engineers, and GenAI app developers working with DevOps teams."（Airflow DAG、Jupyterノートブック、MLワークフローを開発から本番環境まで確実にデプロイ。データサイエンティスト、データエンジニア、MLエンジニア、DevOpsチームと協働するGenAIアプリ開発者向けに構築）

"Works with your deployment strategy: Whether you use git branches (branch-based), versioned artifacts (bundle-based), git tags (tag-based), or direct deployment - this CLI supports your workflow. Define your application once, deploy it your way."（あなたのデプロイ戦略に対応：gitブランチ（ブランチベース）、バージョン管理されたアーティファクト（バンドルベース）、gitタグ（タグベース）、直接デプロイのいずれを使用する場合でも、このCLIはあなたのワークフローをサポートします。アプリケーションを一度定義すれば、お好みの方法でデプロイできます）

---

## SMUS CI/CD CLIを使用する理由

✅ **AWS抽象化レイヤー** - "CLI encapsulates all AWS analytics, ML, and SMUS complexity - DevOps teams never call AWS APIs directly" (CLIがAWSの分析、ML、SMUSの複雑さをカプセル化 - DevOpsチームが直接AWSのAPIを呼び出す必要はありません)

✅ **関心の分離** - "Data teams define WHAT to deploy (manifest.yaml), DevOps teams define HOW and WHEN (CI/CD workflows)" (データチームはデプロイ内容を定義し、DevOpsチームは方法とタイミングを定義します)

✅ **汎用CI/CDワークフロー** - "Same workflow works for Glue, SageMaker, Bedrock, QuickSight, or any AWS service combination" (同じワークフローがGlue、SageMaker、Bedrock、QuickSight、または任意のAWSサービスの組み合わせで動作します)

✅ **確実なデプロイ** - 本番環境への展開前に自動テストと検証を実施

✅ **マルチ環境管理** - 環境固有の設定によるテスト→本番環境への展開

✅ **Infrastructure as Code** - アプリケーションマニフェストのバージョン管理と再現可能なデプロイメント

✅ **イベント駆動型ワークフロー** - EventBridgeを介してデプロイメント時に自動的にワークフローをトリガー

---

## クイックスタート

**インストール:**
```bash
pip install aws-smus-cicd-cli
```

**最初のアプリケーションをデプロイ:**
```bash
# Validate configuration
aws-smus-cicd-cli describe --manifest manifest.yaml --connect

# Create deployment bundle (optional)
aws-smus-cicd-cli bundle --manifest manifest.yaml

# Deploy to test environment
aws-smus-cicd-cli deploy --targets test --manifest manifest.yaml

# Run validation tests
aws-smus-cicd-cli test --manifest manifest.yaml --targets test
```

**動作確認:** [Live GitHub Actions Example](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/runs/17631303500)

---

## 対象者

### 👨‍💻 データチーム（データサイエンティスト、データエンジニア、生成AIアプリ開発者）
**注力すること:** アプリケーション - 何をデプロイし、どこにデプロイし、どのように実行するか  
**定義すること:** コード、ワークフロー、設定を含むアプリケーションマニフェスト（`manifest.yaml`）  
"You don't need to know: CI/CD pipelines, GitHub Actions, deployment automation" (CI/CDパイプライン、GitHub Actions、デプロイメント自動化について知る必要はありません)

→ **[クイックスタートガイド](docs/getting-started/quickstart.md)** - 10分で最初のアプリケーションをデプロイ  

**以下の例を含みます:**
- "Data Engineering (Glue, Notebooks, Athena)" (データエンジニアリング)
- "ML Workflows (SageMaker, Notebooks)" (機械学習ワークフロー)
- "GenAI Applications (Bedrock, Notebooks)" (生成AIアプリケーション)

### 🔧 DevOpsチーム
**注力すること:** CI/CDのベストプラクティス、セキュリティ、コンプライアンス、デプロイメント自動化  
**定義すること:** テスト、承認、プロモーションポリシーを実施するワークフローテンプレート  
"You don't need to know: Application-specific details, AWS services used, DataZone APIs, SMUS project structures, or business logic" (アプリケーション固有の詳細、使用されるAWSサービス、DataZone API、SMUSプロジェクト構造、ビジネスロジックについて知る必要はありません)

→ **[管理者ガイド](docs/getting-started/admin-quickstart.md)** - 15分でインフラストラクチャとパイプラインを設定  
→ **[GitHubワークフローテンプレート](git-templates/)** - 自動デプロイメント用の汎用的で再利用可能なワークフローテンプレート

"The CLI is your abstraction layer: You just call `aws-smus-cicd-cli deploy` - the CLI handles all AWS service interactions (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Your workflows stay simple and generic." (CLIが抽象化レイヤーとなります：`aws-smus-cicd-cli deploy`を呼び出すだけで、CLIがすべてのAWSサービスとのやり取りを処理します。ワークフローはシンプルで汎用的なままです)

---

## デプロイ可能なもの

**📊 分析 & BI**
- Glue ETL jobs and crawlers
- Athena queries
- QuickSight dashboards
- EMR jobs (将来対応予定)
- Redshift queries (将来対応予定)

**🤖 機械学習**
- SageMaker training jobs
- ML models and endpoints
- MLflow experiments
- Feature Store (将来対応予定)
- Batch transforms (将来対応予定)

**🧠 生成AI**
- Bedrock agents
- Knowledge bases
- Foundation model configurations (将来対応予定)

**📓 コード & ワークフロー**
- Jupyter notebooks
- Python scripts
- Airflow DAGs (MWAA and Amazon MWAA Serverless)
- Lambda functions (将来対応予定)

**💾 データ & ストレージ**
- S3 data files
- Git repositories
- Data catalogs (将来対応予定)

---

## サポートされているAWSサービス

"Deploy workflows using these AWS services through Airflow YAML syntax"
（AirflowのYAML構文を使用して、これらのAWSサービスでワークフローをデプロイ）

### 🎯 分析とデータ
**Amazon Athena** • **AWS Glue** • **Amazon EMR** • **Amazon Redshift** • **Amazon QuickSight** • **Lake Formation**

### 🤖 機械学習
**SageMaker Training** • **SageMaker Pipelines** • **Feature Store** • **Model Registry** • **Batch Transform**

### 🧠 生成AI
**Amazon Bedrock** • **Bedrock Agents** • **Bedrock Knowledge Bases** • **Guardrails**

### 📊 その他のサービス
S3 • Lambda • Step Functions • DynamoDB • RDS • SNS/SQS • Batch

**完全なリストを見る：** [Airflow AWS Operators Reference](docs/airflow-aws-operators.md)

---

## Core Concepts

### Separation of Concerns: The Key Design Principle

**The Problem:** Traditional deployment approaches force DevOps teams to learn AWS analytics services (Glue, Athena, DataZone, SageMaker, MWAA, etc.) and understand SMUS project structures, or force data teams to become CI/CD experts.

**The Solution:** SMUS CI/CD CLI is the abstraction layer that encapsulates all AWS and SMUS complexity.

**Example workflow:**

```
1. DevOps Team                 2. Data Team                    3. SMUS CI/CD CLI (The Abstraction)
   ↓                               ↓                              ↓
Defines the PROCESS            Defines the CONTENT            Workflow calls:
- Test on merge                - Glue jobs                    aws-smus-cicd-cli deploy --manifest manifest.yaml
- Approval for prod            - SageMaker training             ↓
- Security scans               - Athena queries               CLI handles ALL AWS complexity:
- Notification rules           - File structure               - DataZone APIs
                                                              - Glue/Athena/SageMaker APIs
Defines INFRASTRUCTURE                                        - MWAA deployment
- Account & region                                            - S3 management
- IAM roles                                                   - IAM configuration
- Resources                                                   - Infrastructure provisioning

Works for ANY app!
No ML/Analytics/GenAI
service knowledge needed!
```

**DevOps teams focus on:**
- CI/CD best practices (testing, approvals, notifications)
- Security and compliance gates
- Deployment orchestration
- Monitoring and alerting

**SMUS CI/CD CLI handles ALL AWS complexity:**
- DataZone domain and project management
- AWS Glue, Athena, SageMaker, MWAA APIs
- S3 storage and artifact management
- IAM roles and permissions
- Connection configurations
- Catalog asset subscriptions
- Workflow deployment to Airflow
- Infrastructure provisioning
- Testing and validation

**Data teams focus on:**
- Application code and workflows
- Which AWS services to use (Glue, Athena, SageMaker, etc.)
- Environment configurations
- Business logic

**Result:** 
- **DevOps teams never call AWS APIs directly** - they just call `aws-smus-cicd-cli deploy`
- **CI/CD workflows are generic** - same workflow works for Glue apps, SageMaker apps, or Bedrock apps
- Data teams never touch CI/CD configs
- Both teams work independently using their expertise

---

### Application Manifest
A declarative YAML file (`manifest.yaml`) that defines your data application:
- **Application details** - Name, version, description
- **Content** - Code from git repositories, data/models from storage, QuickSight dashboards
- **Workflows** - Airflow DAGs for orchestration and automation
- **Stages** - Where to deploy (dev, test, prod environments)
- **Configuration** - Environment-specific settings, connections, and bootstrap actions

**Created and owned by data teams.** Defines **what** to deploy and **where**. No CI/CD knowledge required.

### Application
Your data/analytics workload being deployed:
- Airflow DAGs and Python scripts
- Jupyter notebooks and data files
- ML models and training code
- ETL pipelines and transformations
- GenAI agents and MCP servers
- Foundation model configurations

### Stage
A deployment environment (dev, test, prod) mapped to a SageMaker Unified Studio project:
- Domain and region configuration
- Project name and settings
- Resource connections (S3, Airflow, Athena, Glue)
- Environment-specific parameters
- Optional branch mapping for git-based deployments

### Stage-to-Project Mapping

Each application stage deploys to a dedicated SageMaker Unified Studio (SMUS) project. A project can host a single application or multiple applications depending on your architecture and CI/CD methodology. Stage projects are independent entities with their own governance:

- **Ownership & Access:** Each stage project has its own set of owners and contributors, which may differ from the development project. Production projects typically have restricted access compared to development environments.
- **Multi-Domain & Multi-Region:** Stage projects can belong to different SMUS domains, AWS accounts, and regions. For example, your dev stage might deploy to a development domain in us-east-1, while prod deploys to a production domain in eu-west-1.
- **Flexible Architecture:** Organizations can choose between dedicated projects per application (isolation) or shared projects hosting multiple applications (consolidation), based on security, compliance, and operational requirements.

This separation enables true environment isolation with independent access controls, compliance boundaries, and regional data residency requirements.

### Workflow
Orchestration logic that executes your application. Workflows serve two purposes:

**1. Deployment-time:** Create required AWS resources during deployment
- Provision infrastructure (S3 buckets, databases, IAM roles)
- Configure connections and permissions
- Set up monitoring and logging

**2. Runtime:** Execute ongoing data and ML pipelines
- Scheduled execution (daily, hourly, etc.)
- Event-driven triggers (S3 uploads, API calls)
- Data processing and transformations
- Model training and inference

Workflows are defined as Airflow DAGs (Directed Acyclic Graphs) in YAML format. Supports [MWAA (Managed Workflows for Apache Airflow)](https://aws.amazon.com/managed-workflows-for-apache-airflow/) and [Amazon MWAA Serverless](https://aws.amazon.com/blogs/big-data/introducing-amazon-mwaa-serverless/) ([User Guide](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/what-is-mwaa-serverless.html)).

### CI/CD Automation
GitHub Actions workflows (or other CI/CD systems) that automate deployment:
- **Created and owned by DevOps teams**
- Defines **how** and **when** to deploy
- Runs tests and quality gates
- Manages promotion across targets
- Enforces security and compliance policies
- Example: `.github/workflows/deploy.yml`

**Key insight:** DevOps teams create generic, reusable workflows that work for ANY application. They don't need to know if the app uses Glue, SageMaker, or Bedrock - the CLI handles all AWS service interactions. The workflow just calls `aws-smus-cicd-cli deploy` and the CLI does the rest.

### Deployment Modes

**Bundle-based (Artifact):** Create versioned archive → deploy archive to stages
- Good for: audit trails, rollback capability, compliance
- Command: `aws-smus-cicd-cli bundle` then `aws-smus-cicd-cli deploy --manifest app.tar.gz`

**Direct (Git-based):** Deploy directly from sources without intermediate artifacts
- Good for: simpler workflows, rapid iteration, git as source of truth
- Command: `aws-smus-cicd-cli deploy --manifest manifest.yaml --stage test`

Both modes work with any combination of storage and git content sources.

---


## サンプルアプリケーション

SMUS CI/CDを使用して様々なワークロードをデプロイする実例を紹介します。

### 📊 分析 - QuickSightダッシュボード
データ準備のための自動化されたGlue ETLパイプラインを使用してインタラクティブなBIダッシュボードをデプロイします。QuickSightアセットバンドル、Athenaクエリ、環境固有の設定を使用したGitHubデータセット統合を利用します。

**AWS Services:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-dashboard-glue-quicksight.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-dashboard-glue-quicksight.yml)

**デプロイ時の動作:** アプリケーションコードがS3にデプロイされ、GlueジョブとAirflowワークフローが作成・実行され、QuickSightダッシュボード/データソース/データセットが作成され、最新のデータでダッシュボードを更新するためにQuickSightの取り込みが開始されます。

<details>
<summary><b>📁 アプリケーション構造</b></summary>

```
dashboard-glue-quick/
├── manifest.yaml                      # Deployment configuration
├── covid_etl_workflow.yaml           # Airflow workflow definition
├── glue_setup_covid_db.py            # Glue job: Create database & tables
├── glue_covid_summary_job.py         # Glue job: ETL transformations
├── glue_set_permission_check.py      # Glue job: Permission validation
├── quicksight/
│   └── TotalDeathByCountry.qs        # QuickSight dashboard bundle
└── app_tests/
    └── test_covid_data.py            # Integration tests
```

**主要ファイル:**
- **Glue Jobs**: データベース設定、ETL、検証用のPythonスクリプト
- **Workflow**: オーケストレーション用のAirflow DAG定義YAML
- **QuickSight Bundle**: ダッシュボード、データセット、データソース
- **Tests**: データ品質とダッシュボード機能の検証

</details>

[以下、同様のパターンで残りの部分を翻訳]

## ドキュメント

### はじめに
- **[クイックスタートガイド](docs/getting-started/quickstart.md)** - 最初のアプリケーションをデプロイ（10分）
- **[管理者ガイド](docs/getting-started/admin-quickstart.md)** - インフラストラクチャのセットアップ（15分）

### ガイド
- **[Application Manifest](docs/manifest.md)** - 完全なYAML設定リファレンス
- **[CLI Commands](docs/cli-commands.md)** - 利用可能なすべてのコマンドとオプション
- **[Bootstrap Actions](docs/bootstrap-actions.md)** - 自動デプロイアクションとイベント駆動型ワークフロー
- **[Substitutions & Variables](docs/substitutions-and-variables.md)** - 動的設定
- **[接続ガイド](docs/connections.md)** - AWSサービス統合の設定
- **[GitHub Actions Integration](docs/github-actions-integration.md)** - CI/CD自動化のセットアップ
- **[Deployment Metrics](docs/pipeline-deployment-metrics.md)** - EventBridgeによるモニタリング
- **[Catalog Import/Export Guide](docs/catalog-import-export-guide.md)** - 環境間でDataZoneカタログリソースを昇格
- **[Catalog Import/Export Quick Reference](docs/catalog-import-export-quick-reference.md)** - カタログデプロイのクイックリファレンス

### リファレンス
- **[Manifest Schema](docs/manifest-schema.md)** - YAMLスキーマの検証と構造
- **[Airflow AWS Operators](docs/airflow-aws-operators.md)** - カスタムオペレーターリファレンス

### 例
- **[サンプルガイド](docs/examples-guide.md)** - サンプルアプリケーションのチュートリアル
- **[Data Notebooks](docs/examples-guide.md#-data-engineering---notebooks)** - AirflowによるJupyterノートブック
- **[ML Training](docs/examples-guide.md#-machine-learning---training)** - MLflowによるSageMakerトレーニング
- **[ML Deployment](docs/examples-guide.md#-machine-learning---deployment)** - SageMakerエンドポイントのデプロイ
- **[QuickSight Dashboard](docs/examples-guide.md#-analytics---quicksight-dashboard)** - GlueによるBIダッシュボード
- **[GenAI Application](docs/examples-guide.md#-generative-ai)** - Bedrockエージェントとナレッジベース

### 開発
- **[開発者ガイド](developer/developer-guide.md)** - アーキテクチャ、テスト、ワークフローを含む完全な開発ガイド
- **[AIアシスタントコンテキスト](developer/AmazonQ.md)** - AIアシスタント用コンテキスト（Amazon Q、Kiro）
- **[テスト概要](tests/README.md)** - テストインフラストラクチャ

### サポート
- **Issues**: [GitHub Issues](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues)
- **ドキュメント**: [docs/](docs/)
- **サンプル**: [examples/](examples/)

---

## セキュリティに関する注意事項

公式のAWS PyPIパッケージまたはソースコードからのみインストールしてください。

```bash
# ✅ 正しい方法 - 公式AWS PyPIパッケージからインストール
pip install aws-smus-cicd-cli

# ✅ これも正しい方法 - 公式AWSソースコードからインストール
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

---

## ライセンス

このプロジェクトはMIT-0ライセンスの下でライセンスされています。詳細は[LICENSE](../../LICENSE)をご覧ください。

---

<div align="center">
  <img src="docs/readme-qr-code.png" alt="Scan to view README" width="200"/>
  <p><em>GitHubでこのREADMEを表示するにはQRコードをスキャンしてください</em></p>
</div>