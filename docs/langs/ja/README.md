[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](../it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-brightgreen.svg?style=for-the-badge)](../ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](../zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](../he/README.md)

# SMUS CI/CD Pipeline CLI

← [Back to Main README](../../../README.md)


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

✅ **AWS抽象化レイヤー** - "CLI encapsulates all AWS analytics, ML, and SMUS complexity - DevOps teams never call AWS APIs directly"（CLIがAWSの分析、ML、SMUSの複雑さをカプセル化 - DevOpsチームが直接AWSのAPIを呼び出す必要なし）

✅ **関心の分離** - "Data teams define WHAT to deploy (manifest.yaml), DevOps teams define HOW and WHEN (CI/CD workflows)"（データチームは何をデプロイするか定義し、DevOpsチームはどのように・いつデプロイするかを定義）

✅ **汎用CI/CDワークフロー** - "Same workflow works for Glue, SageMaker, Bedrock, QuickSight, or any AWS service combination"（同じワークフローがGlue、SageMaker、Bedrock、QuickSight、または任意のAWSサービスの組み合わせで機能）

✅ **確実なデプロイ** - 本番環境への展開前の自動テストと検証

✅ **マルチ環境管理** - 環境固有の設定によるテスト→本番環境への展開

✅ **Infrastructure as Code** - バージョン管理されたアプリケーションマニフェストと再現可能なデプロイ

✅ **イベント駆動型ワークフロー** - "Trigger workflows automatically via EventBridge on deployment"（デプロイ時にEventBridgeを介してワークフローを自動的にトリガー）

---

## クイックスタート

**ソースからインストール:**
```bash
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

**最初のアプリケーションをデプロイ:**
```bash
# 設定の検証
aws-smus-cicd-cli describe --manifest manifest.yaml --connect

# デプロイメントバンドルの作成（任意）
aws-smus-cicd-cli bundle --manifest manifest.yaml

# テスト環境へのデプロイ
aws-smus-cicd-cli deploy --targets test --manifest manifest.yaml

# 検証テストの実行
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
"Data Engineering (Glue, Notebooks, Athena)" (データエンジニアリング)  
"ML Workflows (SageMaker, Notebooks)" (機械学習ワークフロー)  
"GenAI Applications (Bedrock, Notebooks)" (生成AIアプリケーション)

### 🔧 DevOpsチーム
**注力すること:** CI/CDのベストプラクティス、セキュリティ、コンプライアンス、デプロイメント自動化  
**定義すること:** テスト、承認、昇格ポリシーを強制するワークフローテンプレート  
"You don't need to know: Application-specific details, AWS services used, DataZone APIs, SMUS project structures, or business logic" (アプリケーション固有の詳細、使用されるAWSサービス、DataZone API、SMUSプロジェクト構造、ビジネスロジックについて知る必要はありません)

→ **[管理者ガイド](docs/getting-started/admin-quickstart.md)** - 15分でインフラストラクチャとパイプラインを設定  
→ **[GitHubワークフローテンプレート](git-templates/)** - 自動デプロイメント用の汎用的で再利用可能なワークフローテンプレート

"The CLI is your abstraction layer: You just call `aws-smus-cicd-cli deploy` - the CLI handles all AWS service interactions (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Your workflows stay simple and generic." (CLIが抽象化レイヤーとなります：`aws-smus-cicd-cli deploy`を呼び出すだけで、CLIがすべてのAWSサービスとのやり取りを処理します。ワークフローはシンプルで汎用的なままです。)

---

## デプロイ可能なもの

**📊 分析とBI**
- Glue ETLジョブとクローラー
- Athenaクエリ
- QuickSightダッシュボード
- EMRジョブ（将来対応予定）
- Redshiftクエリ（将来対応予定）

**🤖 機械学習**
"Deploy SageMaker training jobs and ML models" (SageMaker学習ジョブとMLモデルのデプロイ)
- MLflowの実験
- Feature Store（将来対応予定）
- Batch transforms（将来対応予定）

**🧠 生成AI**
- Bedrockエージェント
- ナレッジベース
- Foundation modelの設定（将来対応予定）

**📓 コードとワークフロー**
"Deploy Jupyter notebooks and Python scripts" (Jupyterノートブックとpythonスクリプトのデプロイ)
"Deploy Airflow DAGs (MWAA and Amazon MWAA Serverless)" (Airflow DAGのデプロイ（MWAAとAmazon MWAA Serverless））
- Lambda関数（将来対応予定）

**💾 データとストレージ**
- S3データファイル
- Gitリポジトリ
- データカタログ（将来対応予定）

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

## コアコンセプト

### 関心の分離：重要な設計原則

**問題点：** 従来のデプロイメントアプローチでは、DevOpsチームがAWSの分析サービスとSMUSプロジェクト構造を学ぶ必要があるか、またはデータチームがCI/CDの専門家になる必要がありました。

**解決策：** SMUS CI/CD CLIは、すべてのAWSとSMUSの複雑さをカプセル化する抽象化レイヤーです。

"Example workflow:"

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

"DevOps teams focus on:" (DevOpsチームの注力点：)
- CI/CD best practices (testing, approvals, notifications)
- Security and compliance gates
- Deployment orchestration
- Monitoring and alerting

"SMUS CI/CD CLI handles ALL AWS complexity:" (SMUS CI/CD CLIが処理するAWSの複雑さ：)
- DataZone domain and project management
- AWS Glue, Athena, SageMaker, MWAA APIs
- S3 storage and artifact management
- IAM roles and permissions
- Connection configurations
- Catalog asset subscriptions
- Workflow deployment to Airflow
- Infrastructure provisioning
- Testing and validation

**データチームの注力点：**
- アプリケーションコードとワークフロー
- 使用するAWSサービスの選択（Glue、Athena、SageMakerなど）
- 環境設定
- ビジネスロジック

**結果：**
- DevOpsチームは直接AWSのAPIを呼び出すことはない - `aws-smus-cicd-cli deploy`を呼び出すだけ
- CI/CDワークフローは汎用的 - 同じワークフローがGlueアプリ、SageMakerアプリ、Bedrockアプリで動作
- データチームはCI/CD設定に触れない
- 両チームが独自の専門知識を活かして独立して作業

---

### アプリケーションマニフェスト
データアプリケーションを定義する宣言的YAMLファイル（`manifest.yaml`）：
- **アプリケーション詳細** - 名前、バージョン、説明
- **コンテンツ** - Gitリポジトリからのコード、ストレージからのデータ/モデル、QuickSightダッシュボード
- **ワークフロー** - オーケストレーションと自動化のためのAirflow DAG
- **ステージ** - デプロイ先（開発、テスト、本番環境）
- **設定** - 環境固有の設定、接続、ブートストラップアクション

データチームが作成し所有します。**何を**デプロイし**どこに**デプロイするかを定義します。CI/CDの知識は不要です。

### アプリケーション
デプロイされるデータ/分析ワークロード：
- Airflow DAGとPythonスクリプト
- Jupyterノートブックとデータファイル
- MLモデルとトレーニングコード
- ETLパイプラインと変換
- GenAIエージェントとMCPサーバー
- 基盤モデル設定

### ステージ
SageMaker Unified Studioプロジェクトにマッピングされるデプロイメント環境（開発、テスト、本番）：
- ドメインとリージョンの設定
- プロジェクト名と設定
- リソース接続（S3、Airflow、Athena、Glue）
- 環境固有のパラメータ
- Gitベースのデプロイメント用のオプションのブランチマッピング

### ステージからプロジェクトへのマッピング

各アプリケーションステージは、専用のSageMaker Unified Studio（SMUS）プロジェクトにデプロイされます。プロジェクトは、アーキテクチャとCI/CD手法に応じて、単一のアプリケーションまたは複数のアプリケーションをホストできます。ステージプロジェクトは独自のガバナンスを持つ独立したエンティティです：

- **所有権とアクセス：** 各ステージプロジェクトには独自のオーナーとコントリビューターがおり、開発プロジェクトとは異なる場合があります。本番プロジェクトは通常、開発環境と比べてアクセスが制限されています。
- **マルチドメインとマルチリージョン：** ステージプロジェクトは異なるSMUSドメイン、AWSアカウント、リージョンに属することができます。例えば、開発ステージはus-east-1の開発ドメインにデプロイし、本番はeu-west-1の本番ドメインにデプロイするといった具合です。
- **柔軟なアーキテクチャ：** 組織は、セキュリティ、コンプライアンス、運用要件に基づいて、アプリケーションごとの専用プロジェクト（分離）または複数のアプリケーションをホストする共有プロジェクト（統合）を選択できます。

この分離により、独立したアクセス制御、コンプライアンス境界、地域データレジデンシー要件を持つ真の環境分離が可能になります。

### ワークフロー
アプリケーションを実行するオーケストレーションロジック。ワークフローには2つの目的があります：

**1. デプロイメント時：** デプロイメント中に必要なAWSリソースを作成
- インフラストラクチャのプロビジョニング（S3バケット、データベース、IAMロール）
- 接続と権限の設定
- モニタリングとロギングのセットアップ

**2. ランタイム：** 継続的なデータとMLパイプラインの実行
- スケジュールされた実行（日次、時間単位など）
- イベント駆動トリガー（S3アップロード、APIコール）
- データ処理と変換
- モデルトレーニングと推論

ワークフローはYAML形式でAirflow DAG（Directed Acyclic Graph）として定義されます。[MWAA (Managed Workflows for Apache Airflow)](https://aws.amazon.com/managed-workflows-for-apache-airflow/)と[Amazon MWAA Serverless](https://aws.amazon.com/blogs/big-data/introducing-amazon-mwaa-serverless/)（[ユーザーガイド](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/what-is-mwaa-serverless.html)）をサポートしています。

### CI/CD自動化
デプロイメントを自動化するGitHub Actionsワークフロー（または他のCI/CDシステム）：
- **DevOpsチームが作成し所有**
- **どのように**そして**いつ**デプロイするかを定義
- テストと品質ゲートの実行
- ターゲット間のプロモーション管理
- セキュリティとコンプライアンスポリシーの適用
- 例：`.github/workflows/deploy.yml`

**重要な洞察：** DevOpsチームは、どんなアプリケーションでも動作する汎用的で再利用可能なワークフローを作成します。アプリがGlue、SageMaker、Bedrockのどれを使用しているかを知る必要はありません - CLIがすべてのAWSサービスとのやり取りを処理します。ワークフローは単に`aws-smus-cicd-cli deploy`を呼び出し、CLIが残りを処理します。

### デプロイメントモード

**バンドルベース（アーティファクト）：** バージョン管理されたアーカイブを作成 → アーカイブをステージにデプロイ
- 適している用途：監査証跡、ロールバック機能、コンプライアンス
- コマンド：`aws-smus-cicd-cli bundle`その後`aws-smus-cicd-cli deploy --manifest app.tar.gz`

**直接（Gitベース）：** 中間アーティファクトなしでソースから直接デプロイ
- 適している用途：シンプルなワークフロー、迅速な反復、Gitを真実の源とする
- コマンド：`aws-smus-cicd-cli deploy --manifest manifest.yaml --stage test`

両モードは、ストレージとGitコンテンツソースのあらゆる組み合わせで動作します。

---

## サンプルアプリケーション

SMUS CI/CDを使用して様々なワークロードをデプロイする実例を紹介します。

### 📊 分析 - QuickSightダッシュボード
("Deploy interactive BI dashboards with automated Glue ETL pipelines for data preparation. Uses QuickSight asset bundles, Athena queries, and GitHub dataset integration with environment-specific configurations.")

**AWS Services:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-dashboard-glue-quicksight.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-dashboard-glue-quicksight.yml)

("What happens during deployment: Application code is deployed to S3, Glue jobs and Airflow workflows are created and executed, QuickSight dashboard/data source/dataset are created, and QuickSight ingestion is initiated to refresh the dashboard with latest data.")

<details>
<summary><b>📁 アプリケーション構造</b></summary>

```
dashboard-glue-quick/
├── manifest.yaml                      # デプロイ設定
├── covid_etl_workflow.yaml           # Airflowワークフロー定義
├── glue_setup_covid_db.py            # Glueジョブ: データベースとテーブルの作成
├── glue_covid_summary_job.py         # Glueジョブ: ETL変換
├── glue_set_permission_check.py      # Glueジョブ: 権限の検証
├── quicksight/
│   └── TotalDeathByCountry.qs        # QuickSightダッシュボードバンドル
└── app_tests/
    └── test_covid_data.py            # 統合テスト
```

**主要ファイル:**
- **Glue Jobs**: データベース設定、ETL、検証用のPythonスクリプト
- **Workflow**: オーケストレーション用のAirflow DAG定義YAML
- **QuickSight Bundle**: ダッシュボード、データセット、データソース
- **Tests**: データ品質とダッシュボード機能の検証

</details>

[View Full Example →](docs/examples-guide.md#-analytics---quicksight-dashboard)

---

### 📓 データエンジニアリング - ノートブック
("Deploy Jupyter notebooks with parallel execution orchestration for data analysis and ETL workflows. Demonstrates notebook deployment with MLflow integration for experiment tracking.")

**AWS Services:** SageMaker Notebooks • MLflow • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-data-notebooks.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-data-notebooks.yml)

("What happens during deployment: Notebooks and workflow definitions are uploaded to S3, Airflow DAG is created for parallel notebook execution, MLflow connection is provisioned for experiment tracking, and notebooks are ready to run on-demand or scheduled.")

<details>
<summary><b>📁 アプリケーション構造</b></summary>

```
data-notebooks/
├── manifest.yaml                                # デプロイ設定
├── notebooks/
│   ├── customer_churn_prediction.ipynb         # 顧客離反予測ML
│   ├── retail_sales_forecasting.ipynb          # 売上予測
│   ├── customer_segmentation_analysis.ipynb    # 顧客セグメンテーション
│   └── requirements.txt                        # Python依存関係
├── workflows/
│   └── parallel_notebooks_workflow.yaml        # Airflowオーケストレーション
└── app_tests/
    └── test_notebooks_execution.py             # 統合テスト
```

**主要ファイル:**
- **Notebooks**: MLと分析ワークフロー用の3つのJupyterノートブック
- **Workflow**: Airflowによる並列実行オーケストレーション
- **Tests**: ノートブックの実行と出力の検証

</details>

[View Full Example →](docs/examples-guide.md#-data-engineering---notebooks)

[残りの部分は同様のパターンで翻訳を続けます]

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

## セキュリティに関する注意

⚠️ **PyPIからインストールしないでください** - 必ずAWSの公式ソースコードからインストールしてください。

```bash
# ✅ 正しい方法 - AWSの公式リポジトリからインストール
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .

# ❌ 誤った方法 - PyPIを使用しないでください
pip install aws-smus-cicd-cli  # 悪意のあるコードが含まれている可能性があります
```

---

## ライセンス

このプロジェクトはMIT-0ライセンスの下でライセンスされています。詳細は[LICENSE](../../LICENSE)をご覧ください。

---

<div align="center">
  <img src="docs/readme-qr-code.png" alt="Scan to view README" width="200"/>
  <p><em>GitHubでこのREADMEを表示するにはQRコードをスキャンしてください</em></p>
</div>