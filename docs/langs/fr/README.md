[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-brightgreen.svg?style=for-the-badge)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](../it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-gray.svg)](../ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](../zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](../he/README.md)

# SMUS CI/CD Pipeline CLI

← [Back to Main README](../../../README.md)


**Automatisez le déploiement d'applications de données à travers les environnements SageMaker Unified Studio**

Déployez des DAGs Airflow, des notebooks Jupyter et des workflows ML du développement à la production en toute confiance. Conçu pour les data scientists, les ingénieurs de données, les ingénieurs ML et les développeurs d'applications GenAI travaillant avec des équipes DevOps.

**Compatible avec votre stratégie de déploiement :** Que vous utilisiez des branches git (basé sur les branches), des artefacts versionnés (basé sur les bundles), des tags git (basé sur les tags) ou un déploiement direct - ce CLI prend en charge votre workflow. Définissez votre application une seule fois, déployez-la à votre façon.

---

## Pourquoi SMUS CI/CD CLI ?

✅ **Couche d'Abstraction AWS** - Le CLI encapsule toute la complexité d'AWS analytics, ML et SMUS - les équipes DevOps n'appellent jamais directement les API AWS  
✅ **Séparation des Responsabilités** - Les équipes data définissent QUOI déployer (manifest.yaml), les équipes DevOps définissent COMMENT et QUAND (workflows CI/CD)  
✅ **Workflows CI/CD Génériques** - Le même workflow fonctionne pour Glue, SageMaker, Bedrock, QuickSight, ou toute combinaison de services AWS  
✅ **Déploiement en Confiance** - Tests et validation automatisés avant la production  
✅ **Gestion Multi-Environnements** - Test → Prod avec configuration spécifique à l'environnement  
✅ **Infrastructure as Code** - Manifests d'application versionnés et déploiements reproductibles  
✅ **Workflows Événementiels** - Déclenchement automatique des workflows via EventBridge lors du déploiement  

---

## Démarrage Rapide

**Installation depuis la source :**
```bash
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

**Déployez votre première application :**
```bash
# Valider la configuration
smus-cicd-cli describe --manifest manifest.yaml --connect

# Créer un bundle de déploiement (optionnel)
smus-cicd-cli bundle --manifest manifest.yaml

# Déployer vers l'environnement de test
smus-cicd-cli deploy --targets test --manifest manifest.yaml

# Exécuter les tests de validation
smus-cicd-cli test --manifest manifest.yaml --targets test
```

**Voir en action :** [Live GitHub Actions Example](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/runs/17631303500)

---

## À Qui S'Adresse Ce Projet ?

### 👨‍💻 Équipes Data (Data Scientists, Data Engineers, Développeurs d'Applications GenAI)
**Vous vous concentrez sur :** Votre application - quoi déployer, où déployer et comment elle fonctionne  
**Vous définissez :** Le manifest de l'application (`manifest.yaml`) avec votre code, vos workflows et configurations  
**Vous n'avez pas besoin de connaître :** Les pipelines CI/CD, GitHub Actions, l'automatisation du déploiement  

→ **[Guide de Démarrage Rapide](docs/getting-started/quickstart.md)** - Déployez votre première application en 10 minutes  

**Inclut des exemples pour :**
- Data Engineering (Glue, Notebooks, Athena)
- Workflows ML (SageMaker, Notebooks)
- Applications GenAI (Bedrock, Notebooks)

**Actions Bootstrap - Automatisez les Tâches Post-Déploiement :**

Définissez des actions dans votre manifest qui s'exécutent automatiquement après le déploiement :
- Déclenchez des workflows immédiatement (sans exécution manuelle)
- Actualisez les tableaux de bord QuickSight avec les dernières données
- Configurez les connexions MLflow pour le suivi des expériences
- Récupérez les logs pour validation
- Émettez des événements pour déclencher des processus en aval

Exemple :
```yaml
bootstrap:
  actions:
    - type: workflow.run
      workflowName: etl_pipeline
      wait: true
    - type: quicksight.refresh_dataset
      refreshScope: IMPORTED
```

### 🔧 Équipes DevOps
**Vous vous concentrez sur :** Les bonnes pratiques CI/CD, la sécurité, la conformité et l'automatisation du déploiement  
**Vous définissez :** Des modèles de workflow qui appliquent les tests, les approbations et les politiques de promotion  
**Vous n'avez pas besoin de connaître :** Les détails spécifiques aux applications, les services AWS utilisés, les API DataZone, les structures de projet SMUS, ou la logique métier  

→ **[Guide Administrateur](docs/getting-started/admin-quickstart.md)** - Configurez l'infrastructure et les pipelines en 15 minutes  
→ **[Modèles de Workflow GitHub](git-templates/)** - Modèles de workflow génériques et réutilisables pour le déploiement automatisé

**Le CLI est votre couche d'abstraction :** Vous appelez simplement `smus-cicd-cli deploy` - le CLI gère toutes les interactions avec les services AWS (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.) et exécute les actions bootstrap (exécutions de workflow, streaming de logs, actualisations QuickSight, événements EventBridge). Vos workflows restent simples et génériques.

---

## Fonctionnalités Clés

### 🚀 Déploiement Automatisé
- **Manifest d'Application** - Définissez le contenu, les workflows et les cibles de déploiement de votre application en YAML
- **Déploiement Flexible** - Modes de déploiement basés sur les bundles (artéfacts) ou directs (basés sur git)
- **Déploiement Multi-Cibles** - Déployez vers test et prod avec une seule commande
- **Variables d'Environnement** - Configuration dynamique utilisant la substitution `${VAR}`
- **Contrôle de Version** - Suivez les déploiements dans S3 ou git pour l'historique des déploiements

### 🔍 Tests & Validation
- **Tests Automatisés** - Exécutez des tests de validation avant la promotion en production
- **Contrôles Qualité** - Bloquez les déploiements si les tests échouent
- **Surveillance des Workflows** - Suivez l'état d'exécution et les logs
- **Contrôles de Santé** - Vérifiez l'exactitude du déploiement

### 🔄 Intégration Pipeline CI/CD
- **GitHub Actions** - Workflows pipeline CI/CD préconçus pour le déploiement automatisé
- **GitLab CI** - Support natif pour les pipelines CI/CD GitLab
- **Variables d'Environnement** - Configuration flexible pour toute plateforme CI/CD
- **Support Webhook** - Déclenchez des déploiements à partir d'événements externes

### 🏗️ Gestion de l'Infrastructure
- **Création de Projet** - Provisionnez automatiquement les projets SageMaker Unified Studio
- **Configuration des Connexions** - Configurez les connexions S3, Airflow, Athena et Lakehouse
- **Mappage des Ressources** - Liez les ressources AWS aux connexions du projet
- **Gestion des Permissions** - Contrôlez l'accès et la collaboration

### ⚡ Actions Bootstrap
- **Exécution Automatisée des Workflows** - Déclenchez automatiquement les workflows pendant le déploiement avec `workflow.run` (utilisez `trailLogs: true` pour diffuser les logs et attendre la fin)
- **Récupération des Logs** - Récupérez les logs des workflows pour la validation et le débogage avec `workflow.logs`
- **Actualisation des Jeux de Données QuickSight** - Actualisez automatiquement les tableaux de bord après le déploiement ETL avec `quicksight.refresh_dataset`
- **Intégration EventBridge** - Émettez des événements personnalisés pour l'automatisation en aval et l'orchestration CI/CD avec `eventbridge.put_events`
- **Connexions DataZone** - Provisionnez MLflow et d'autres connexions de service pendant le déploiement
- **Exécution Séquentielle** - Les actions s'exécutent dans l'ordre pendant `smus-cicd-cli deploy` pour une initialisation et une validation fiables

### 📊 Intégration du Catalogue
- **Découverte des Ressources** - Trouvez automatiquement les ressources de catalogue requises (Glue, Lake Formation, DataZone)
- **Gestion des Abonnements** - Demandez l'accès aux tables et jeux de données
- **Workflows d'Approbation** - Gérez l'accès aux données inter-projets
- **Suivi des Ressources** - Surveillez les dépendances du catalogue

---

## Que Pouvez-Vous Déployer ?

**📊 Analytique & BI**
- Jobs et crawlers Glue ETL
- Requêtes Athena
- Tableaux de bord QuickSight
- Jobs EMR (à venir)
- Requêtes Redshift (à venir)

**🤖 Machine Learning**
- Jobs d'entraînement SageMaker
- Modèles ML et points de terminaison
- Expériences MLflow
- Feature Store (à venir)
- Transformations par lots (à venir)

**🧠 IA Générative**
- Agents Bedrock
- Bases de connaissances
- Configurations de modèles de base (à venir)

**📓 Code & Workflows**
- Notebooks Jupyter
- Scripts Python
- DAGs Airflow (MWAA et Amazon MWAA Serverless)
- Fonctions Lambda (à venir)

**💾 Données & Stockage**
- Fichiers de données S3
- Dépôts Git
- Catalogues de données (à venir)

---

## Services AWS pris en charge

Déployez des workflows en utilisant ces services AWS via la syntaxe YAML d'Airflow :

### 🎯 Analytique & Données
**Amazon Athena** • **AWS Glue** • **Amazon EMR** • **Amazon Redshift** • **Amazon QuickSight** • **Lake Formation**

### 🤖 Machine Learning
**SageMaker Training** • **SageMaker Pipelines** • **Feature Store** • **Model Registry** • **Batch Transform**

### 🧠 IA Générative
**Amazon Bedrock** • **Bedrock Agents** • **Bedrock Knowledge Bases** • **Guardrails**

### 📊 Services Additionnels
S3 • Lambda • Step Functions • DynamoDB • RDS • SNS/SQS • Batch

**Voir la liste complète :** [Airflow AWS Operators Reference](docs/airflow-aws-operators.md)

---

## Concepts Fondamentaux

### Séparation des Préoccupations : Le Principe de Conception Clé

**Le Problème :** Les approches traditionnelles de déploiement forcent les équipes DevOps à apprendre les services analytiques AWS (Glue, Athena, DataZone, SageMaker, MWAA, etc.) et à comprendre les structures de projet SMUS, ou forcent les équipes de données à devenir des experts en CI/CD.

**La Solution :** SMUS CI/CD CLI est la couche d'abstraction qui encapsule toute la complexité AWS et SMUS :

```
Équipes de Données              SMUS CI/CD CLI                    Équipes DevOps
    ↓                              ↓                             ↓
manifest.yaml             smus-cicd-cli deploy                GitHub Actions
(QUOI & OÙ)             (ABSTRACTION AWS)               (COMMENT & QUAND)
```

**Les équipes de données se concentrent sur :**
- Le code applicatif et les workflows
- Quels services AWS utiliser (Glue, Athena, SageMaker, etc.)
- Les configurations d'environnement
- La logique métier

**SMUS CI/CD CLI gère TOUTE la complexité AWS :**
- Gestion des domaines et projets DataZone
- APIs AWS Glue, Athena, SageMaker, MWAA
- Gestion du stockage S3 et des artefacts
- Rôles et permissions IAM
- Configurations des connexions
- Souscriptions aux ressources du catalogue
- Déploiement des workflows vers Airflow
- Provisionnement de l'infrastructure
- Tests et validation

**Les équipes DevOps se concentrent sur :**
- Les bonnes pratiques CI/CD (tests, approbations, notifications)
- Les contrôles de sécurité et conformité
- L'orchestration des déploiements
- La surveillance et les alertes

**Résultat :**
- Les équipes de données ne touchent jamais aux configs CI/CD
- **Les équipes DevOps n'appellent jamais directement les APIs AWS** - elles appellent simplement `smus-cicd-cli deploy`
- **Les workflows CI/CD sont génériques** - le même workflow fonctionne pour les apps Glue, SageMaker ou Bedrock
- Les deux équipes travaillent indépendamment selon leur expertise

---

### Manifest d'Application
Un fichier YAML déclaratif (`manifest.yaml`) qui définit votre application de données :
- **Détails de l'application** - Nom, version, description
- **Contenu** - Code des dépôts git, données/modèles du stockage, tableaux de bord QuickSight
- **Workflows** - DAGs Airflow pour l'orchestration et l'automatisation
- **Stages** - Où déployer (environnements dev, test, prod)
- **Configuration** - Paramètres spécifiques à l'environnement, connexions et actions d'amorçage

**Créé et géré par les équipes de données.** Définit **quoi** déployer et **où**. Aucune connaissance CI/CD requise.

### Application
Votre charge de travail données/analytique à déployer :
- DAGs Airflow et scripts Python
- Notebooks Jupyter et fichiers de données
- Modèles ML et code d'entraînement
- Pipelines ETL et transformations
- Agents GenAI et serveurs MCP
- Configurations de modèles fondamentaux

### Stage
Un environnement de déploiement (dev, test, prod) mappé à un projet SageMaker Unified Studio :
- Configuration du domaine et de la région
- Nom et paramètres du projet
- Connexions aux ressources (S3, Airflow, Athena, Glue)
- Paramètres spécifiques à l'environnement
- Mapping de branches optionnel pour les déploiements basés sur git

### Workflow
Logique d'orchestration qui exécute votre application. Les workflows servent deux objectifs :

**1. Au déploiement :** Créer les ressources AWS requises pendant le déploiement
- Provisionner l'infrastructure (buckets S3, bases de données, rôles IAM)
- Configurer les connexions et permissions
- Mettre en place la surveillance et les logs

**2. À l'exécution :** Exécuter les pipelines de données et ML continus
- Exécution planifiée (quotidienne, horaire, etc.)
- Déclencheurs événementiels (uploads S3, appels API)
- Traitement et transformations de données
- Entraînement et inférence de modèles

Les workflows sont définis comme des DAGs Airflow (Graphes Acycliques Dirigés) en format YAML. Supporte [MWAA (Managed Workflows for Apache Airflow)](https://aws.amazon.com/managed-workflows-for-apache-airflow/) et [Amazon MWAA Serverless](https://aws.amazon.com/blogs/big-data/introducing-amazon-mwaa-serverless/) ([Guide Utilisateur](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/what-is-mwaa-serverless.html)).

### Automatisation CI/CD
Workflows GitHub Actions (ou autres systèmes CI/CD) qui automatisent le déploiement :
- **Créés et gérés par les équipes DevOps**
- Définit **comment** et **quand** déployer
- Exécute les tests et contrôles qualité
- Gère la promotion entre les cibles
- Applique les politiques de sécurité et conformité
- Exemple : `.github/workflows/deploy.yml`

**Point clé :** Les équipes DevOps créent des workflows génériques et réutilisables qui fonctionnent pour N'IMPORTE QUELLE application. Ils n'ont pas besoin de savoir si l'app utilise Glue, SageMaker ou Bedrock - le CLI gère toutes les interactions avec les services AWS. Le workflow appelle simplement `smus-cicd-cli deploy` et le CLI fait le reste.

### Modes de Déploiement

**Basé sur Bundle (Artefact) :** Créer une archive versionnée → déployer l'archive vers les stages
- Bon pour : pistes d'audit, capacité de rollback, conformité
- Commande : `smus-cicd-cli bundle` puis `smus-cicd-cli deploy --manifest app.tar.gz`

**Direct (Basé sur Git) :** Déployer directement depuis les sources sans artefacts intermédiaires
- Bon pour : workflows plus simples, itération rapide, git comme source de vérité
- Commande : `smus-cicd-cli deploy --manifest manifest.yaml --stage test`

Les deux modes fonctionnent avec toute combinaison de sources de stockage et git.

---

### Comment Tout Fonctionne Ensemble

```
1. Équipe de Données           2. Équipe DevOps              3. SMUS CI/CD CLI (L'Abstraction)
   ↓                              ↓                             ↓
Crée manifest.yaml            Crée workflow générique       Le workflow appelle :
- Jobs Glue                    - Test à la fusion            smus-cicd-cli deploy --manifest manifest.yaml
- Entraînement SageMaker      - Approbation pour prod         ↓
- Requêtes Athena             - Scans de sécurité          CLI gère TOUTE la complexité AWS :
- Emplacements S3             - Règles de notification      - APIs DataZone
                                                            - APIs Glue/Athena/SageMaker
                              Fonctionne pour TOUTE app !   - Déploiement MWAA
                              Pas de connaissance AWS       - Gestion S3
                              nécessaire !                  - Configuration IAM
                                                            - Provisionnement infrastructure
                                                              ↓
                                                            Succès !
```

**La beauté :**
- Les équipes de données n'apprennent jamais GitHub Actions
- **Les équipes DevOps n'appellent jamais les APIs AWS** - le CLI encapsule toute la complexité AWS analytics, ML et SMUS
- Les workflows CI/CD sont simples : juste appeler `smus-cicd-cli deploy`
- Le même workflow fonctionne pour TOUTE application, quels que soient les services AWS utilisés

---

## Example Applications

Real-world examples showing how to deploy different workloads with SMUS CI/CD.

### 📊 Analytics - QuickSight Dashboard
Deploy interactive BI dashboards with automated Glue ETL pipelines for data preparation. Uses QuickSight asset bundles, Athena queries, and GitHub dataset integration with environment-specific configurations.

**AWS Services:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**What happens during deployment:** Application code is deployed to S3, Glue jobs and Airflow workflows are created and executed, QuickSight dashboard/data source/dataset are created, and QuickSight ingestion is initiated to refresh the dashboard with latest data.

<details>
<summary><b>View Manifest</b></summary>

```yaml
applicationName: IntegrationTestETLWorkflow

content:
  storage:
    - name: dashboard-glue-quick
      connectionName: default.s3_shared
      include: [dashboard-glue-quick]
  
  git:
    - repository: covid-19-dataset
      url: https://github.com/datasets/covid-19.git
  
  quicksight:
    - dashboardId: sample-dashboard
      assetBundle: quicksight/sample-dashboard.qs
      owners:
        - arn:aws:quicksight:${DEV_DOMAIN_REGION:us-east-2}:*:user/default/Admin/*
  
  workflows:
    - workflowName: covid_dashboard_glue_quick_pipeline
      connectionName: default.workflow_serverless

stages:
  test:
    domain:
      region: us-east-2
    project:
      name: test-marketing
      owners:
        - Eng1
        - arn:aws:iam::${AWS_ACCOUNT_ID}:role/GitHubActionsRole-SMUS-CLI-Tests
    environment_variables:
      S3_PREFIX: test
      GRANT_TO: Admin,service-role/aws-quicksight-service-role-v0
    bootstrap:
      actions:
        - type: workflow.logs
          workflowName: covid_dashboard_glue_quick_pipeline
          live: true
          lines: 10000
        - type: quicksight.refresh_dataset
          refreshScope: IMPORTED
          ingestionType: FULL_REFRESH
          wait: false
    deployment_configuration:
      quicksight:
        overrideParameters:
          ResourceIdOverrideConfiguration:
            PrefixForAllResources: deployed-{stage.name}-covid-
```

</details>

**[View Full Example →](docs/examples-guide.md#-analytics---quicksight-dashboard)**

---

### 📓 Data Engineering - Notebooks
Deploy Jupyter notebooks with parallel execution orchestration for data analysis and ETL workflows. Demonstrates notebook deployment with MLflow integration for experiment tracking.

**AWS Services:** SageMaker Notebooks • MLflow • S3 • MWAA Serverless

**What happens during deployment:** Notebooks and workflow definitions are uploaded to S3, Airflow DAG is created for parallel notebook execution, MLflow connection is provisioned for experiment tracking, and notebooks are ready to run on-demand or scheduled.

<details>
<summary><b>View Manifest</b></summary>

```yaml
applicationName: IntegrationTestNotebooks

content:
  storage:
    - name: notebooks
      connectionName: default.s3_shared
      include:
        - notebooks/
        - workflows/
      exclude:
        - .ipynb_checkpoints/
        - __pycache__/
  
  workflows:
    - workflowName: parallel_notebooks_execution
      connectionName: default.workflow_serverless

stages:
  test:
    domain:
      region: us-east-1
    project:
      name: test-marketing
      owners:
        - Eng1
        - arn:aws:iam::${AWS_ACCOUNT_ID}:role/GitHubActionsRole-SMUS-CLI-Tests
    environment_variables:
      S3_PREFIX: test
    deployment_configuration:
      storage:
        - name: notebooks
          connectionName: default.s3_shared
          targetDirectory: notebooks/bundle/notebooks
    bootstrap:
      actions:
        - type: datazone.create_connection
          name: mlflow-server
          connection_type: MLFLOW
          properties:
            trackingServerArn: arn:aws:sagemaker:${STS_REGION}:${STS_ACCOUNT_ID}:mlflow-tracking-server/smus-integration-mlflow-use2
            trackingServerName: smus-integration-mlflow-use2
```

</details>

**[View Full Example →](docs/examples-guide.md#-data-engineering---notebooks)**

---

### 🤖 Machine Learning - Training
Train ML models with SageMaker using the [SageMaker SDK](https://sagemaker.readthedocs.io/) and [SageMaker Distribution](https://github.com/aws/sagemaker-distribution/tree/main/src) images. Track experiments with MLflow and automate training pipelines with environment-specific configurations.

**AWS Services:** SageMaker Training • MLflow • S3 • MWAA Serverless

**What happens during deployment:** Training code and workflow definitions are uploaded to S3 with compression, Airflow DAG is created for training orchestration, MLflow connection is provisioned for experiment tracking, and SageMaker training jobs are created and executed using SageMaker Distribution images.

<details>
<summary><b>View Manifest</b></summary>

```yaml
applicationName: IntegrationTestMLTraining

content:
  storage:
    - name: training-code
      connectionName: default.s3_shared
      include: [ml/training/code]
    
    - name: training-workflows
      connectionName: default.s3_shared
      include: [ml/training/workflows]
  
  workflows:
    - workflowName: ml_training_workflow
      connectionName: default.workflow_serverless

stages:
  test:
    domain:
      region: us-east-1
    project:
      name: test-ml-training
      create: true
      owners:
        - Eng1
        - arn:aws:iam::${AWS_ACCOUNT_ID}:role/GitHubActionsRole-SMUS-CLI-Tests
      role:
        arn: arn:aws:iam::${AWS_ACCOUNT_ID}:role/SMUSCICDTestRole
    environment_variables:
      S3_PREFIX: test
    deployment_configuration:
      storage:
        - name: training-code
          connectionName: default.s3_shared
          targetDirectory: ml/bundle/training-code
          compression: gz
        - name: training-workflows
          connectionName: default.s3_shared
          targetDirectory: ml/bundle/training-workflows
    bootstrap:
      actions:
        - type: datazone.create_connection
          name: mlflow-server
          connection_type: MLFLOW
          properties:
            trackingServerArn: arn:aws:sagemaker:${STS_REGION}:${STS_ACCOUNT_ID}:mlflow-tracking-server/smus-integration-mlflow-use2
```

</details>

**[View Full Example →](docs/examples-guide.md#-machine-learning---training)**

---

### 🤖 Machine Learning - Deployment
Deploy trained ML models as SageMaker real-time inference endpoints. Uses SageMaker SDK for endpoint configuration and [SageMaker Distribution](https://github.com/aws/sagemaker-distribution/tree/main/src) images for serving.

**AWS Services:** SageMaker Endpoints • S3 • MWAA Serverless

**What happens during deployment:** Model artifacts, deployment code, and workflow definitions are uploaded to S3, Airflow DAG is created for endpoint deployment orchestration, SageMaker endpoint configuration and model are created, and the inference endpoint is deployed and ready to serve predictions.

<details>
<summary><b>View Manifest</b></summary>

```yaml
applicationName: IntegrationTestMLDeployment

content:
  storage:
    - name: deployment-code
      connectionName: default.s3_shared
      include: [ml/deployment/code]
    
    - name: deployment-workflows
      connectionName: default.s3_shared
      include: [ml/deployment/workflows]
    
    - name: model-artifacts
      connectionName: default.s3_shared
      include: [ml/output/model-artifacts/latest]
  
  workflows:
    - workflowName: ml_deployment_workflow
      connectionName: default.workflow_serverless

stages:
  test:
    domain:
      region: us-east-1
    project:
      name: test-ml-deployment
      create: true
      owners:
        - Eng1
        - arn:aws:iam::${AWS_ACCOUNT_ID}:role/GitHubActionsRole-SMUS-CLI-Tests
      role:
        arn: arn:aws:iam::${AWS_ACCOUNT_ID}:role/SMUSCICDTestRole
    environment_variables:
      S3_PREFIX: test
    deployment_configuration:
      storage:
        - name: deployment-code
          connectionName: default.s3_shared
          targetDirectory: ml/bundle/deployment-code
        - name: deployment-workflows
          connectionName: default.s3_shared
          targetDirectory: ml/bundle/deployment-workflows
        - name: model-artifacts
          connectionName: default.s3_shared
          targetDirectory: ml/bundle/model-artifacts
```

</details>

**[View Full Example →](docs/examples-guide.md#-machine-learning---deployment)**

---

### 🧠 Generative AI
Deploy GenAI applications with Bedrock agents and knowledge bases. Demonstrates RAG (Retrieval Augmented Generation) workflows with automated agent deployment and testing.

**AWS Services:** Amazon Bedrock • S3 • MWAA Serverless

**What happens during deployment:** Agent configuration and workflow definitions are uploaded to S3, Airflow DAG is created for agent deployment orchestration, Bedrock agents and knowledge bases are configured, and the GenAI application is ready for inference and testing.

<details>
<summary><b>View Manifest</b></summary>

```yaml
applicationName: IntegrationTestGenAIWorkflow

content:
  storage:
    - name: agent-code
      connectionName: default.s3_shared
      include: [genai/job-code]
    
    - name: genai-workflows
      connectionName: default.s3_shared
      include: [genai/workflows]
  
  workflows:
    - workflowName: genai_dev_workflow
      connectionName: default.workflow_serverless

stages:
  test:
    domain:
      region: us-east-1
    project:
      name: test-marketing
      owners:
        - Eng1
        - arn:aws:iam::${AWS_ACCOUNT_ID}:role/GitHubActionsRole-SMUS-CLI-Tests
    environment_variables:
      S3_PREFIX: test
    deployment_configuration:
      storage:
        - name: agent-code
          connectionName: default.s3_shared
          targetDirectory: genai/bundle/agent-code
        - name: genai-workflows
          connectionName: default.s3_shared
          targetDirectory: genai/bundle/workflows
```

</details>

**[View Full Example →](docs/examples-guide.md#-generative-ai)**

---

**[See All Examples with Detailed Walkthroughs →](docs/examples-guide.md)**

---

---

<details>
<summary><h2>📋 Feature Checklist</h2></summary>

**Legend:** ✅ Supported | 🔄 Planned | 🔮 Future

### Core Infrastructure
| Feature | Status | Notes |
|---------|--------|-------|
| YAML configuration | ✅ | [Manifest Guide](docs/manifest.md) |
| Infrastructure as Code | ✅ | [Deploy Command](docs/cli-commands.md#deploy) |
| Multi-environment deployment | ✅ | [Stages](docs/manifest-schema.md#stages) |
| CLI tool | ✅ | [CLI Commands](docs/cli-commands.md) |
| Version control integration | ✅ | [GitHub Actions](docs/github-actions-integration.md) |

### Deployment & Bundling
| Feature | Status | Notes |
|---------|--------|-------|
| Artifact bundling | ✅ | [Bundle Command](docs/cli-commands.md#bundle) |
| Bundle-based deployment | ✅ | [Deploy Command](docs/cli-commands.md#deploy) |
| Direct deployment | ✅ | [Deploy Command](docs/cli-commands.md#deploy) |
| Deployment validation | ✅ | [Describe Command](docs/cli-commands.md#describe) |
| Incremental deployment | 🔄 | Upload only changed files |
| Rollback support | 🔮 | Automated rollback |
| Blue-green deployment | 🔮 | Zero-downtime deployments |

### Developer Experience
| Feature | Status | Notes |
|---------|--------|-------|
| Project templates | 🔄 | `smus-cicd-cli init` with templates |
| Manifest initialization | ✅ | [Create Command](docs/cli-commands.md#create) |
| Interactive setup | 🔄 | Guided configuration prompts |
| Local development | ✅ | [CLI Commands](docs/cli-commands.md) |
| VS Code extension | 🔮 | IntelliSense and validation |

### Configuration
| Feature | Status | Notes |
|---------|--------|-------|
| Variable substitution | ✅ | [Substitutions Guide](docs/substitutions-and-variables.md) |
| Environment-specific config | ✅ | [Stages](docs/manifest-schema.md#stages) |
| Secrets management | 🔮 | AWS Secrets Manager integration |
| Config validation | ✅ | [Manifest Schema](docs/manifest-schema.md) |
| Connection management | ✅ | [Connections Guide](docs/connections.md) |

### Resources & Workloads
| Feature | Status | Notes |
|---------|--------|-------|
| Airflow DAGs | ✅ | [Workflows](docs/manifest-schema.md#workflows) |
| Jupyter notebooks | ✅ | [SageMakerNotebookOperator](docs/airflow-aws-operators.md#amazon-sagemaker) |
| Glue ETL jobs | ✅ | [GlueJobOperator](docs/airflow-aws-operators.md#aws-glue) |
| Athena queries | ✅ | [AthenaOperator](docs/airflow-aws-operators.md#amazon-athena) |
| SageMaker training | ✅ | [SageMakerTrainingOperator](docs/airflow-aws-operators.md#amazon-sagemaker) |
| SageMaker endpoints | ✅ | [SageMakerEndpointOperator](docs/airflow-aws-operators.md#amazon-sagemaker) |
| QuickSight dashboards | ✅ | [QuickSight Deployment](docs/quicksight-deployment.md) |
| Bedrock agents | ✅ | [BedrockInvokeModelOperator](docs/airflow-aws-operators.md#amazon-bedrock) |
| Lambda functions | 🔄 | [LambdaInvokeFunctionOperator](docs/airflow-aws-operators.md#aws-lambda) |
| EMR jobs | ✅ | [EmrAddStepsOperator](docs/airflow-aws-operators.md#amazon-emr) |
| Redshift queries | ✅ | [RedshiftDataOperator](docs/airflow-aws-operators.md#amazon-redshift) |

### Bootstrap Actions
| Feature | Status | Notes |
|---------|--------|-------|
| Workflow execution | ✅ | [workflow.run](docs/bootstrap-actions.md#workflowrun---trigger-workflow-execution) |
| Log retrieval | ✅ | [workflow.logs](docs/bootstrap-actions.md#workflowlogs---fetch-workflow-logs) |
| QuickSight refresh | ✅ | [quicksight.refresh_dataset](docs/bootstrap-actions.md#quicksightrefresh_dataset---trigger-dataset-ingestion) |
| EventBridge events | ✅ | [eventbridge.put_events](docs/bootstrap-actions.md#customput_events---emit-custom-events) |
| DataZone connections | ✅ | [datazone.create_connection](docs/bootstrap-actions.md) |
| Sequential execution | ✅ | [Execution Flow](docs/bootstrap-actions.md#execution-flow) |

### CI/CD Integration
| Feature | Status | Notes |
|---------|--------|-------|
| GitHub Actions | ✅ | [GitHub Actions Guide](docs/github-actions-integration.md) |
| GitLab CI | ✅ | [CLI Commands](docs/cli-commands.md) |
| Azure DevOps | ✅ | [CLI Commands](docs/cli-commands.md) |
| Jenkins | ✅ | [CLI Commands](docs/cli-commands.md) |
| Service principals | ✅ | [GitHub Actions Guide](docs/github-actions-integration.md) |
| OIDC federation | ✅ | [GitHub Actions Guide](docs/github-actions-integration.md) |

### Testing & Validation
| Feature | Status | Notes |
|---------|--------|-------|
| Unit testing | ✅ | [Test Command](docs/cli-commands.md#test) |
| Integration testing | ✅ | [Test Command](docs/cli-commands.md#test) |
| Automated tests | ✅ | [Test Command](docs/cli-commands.md#test) |
| Quality gates | ✅ | [Test Command](docs/cli-commands.md#test) |
| Workflow monitoring | ✅ | [Monitor Command](docs/cli-commands.md#monitor) |

### Monitoring & Observability
| Feature | Status | Notes |
|---------|--------|-------|
| Deployment monitoring | ✅ | [Deploy Command](docs/cli-commands.md#deploy) |
| Workflow monitoring | ✅ | [Monitor Command](docs/cli-commands.md#monitor) |
| Custom alerts | ✅ | [Deployment Metrics](docs/pipeline-deployment-metrics.md) |
| Metrics collection | ✅ | [Deployment Metrics](docs/pipeline-deployment-metrics.md) |
| Deployment history | ✅ | [Bundle Command](docs/cli-commands.md#bundle) |

### AWS Service Integration
| Feature | Status | Notes |
|---------|--------|-------|
| Amazon MWAA | ✅ | [Workflows](docs/manifest-schema.md#workflows) |
| MWAA Serverless | ✅ | [Workflows](docs/manifest-schema.md#workflows) |
| AWS Glue | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#aws-glue) |
| Amazon Athena | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#amazon-athena) |
| SageMaker | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#amazon-sagemaker) |
| Amazon Bedrock | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#amazon-bedrock) |
| Amazon QuickSight | ✅ | [QuickSight Deployment](docs/quicksight-deployment.md) |
| DataZone | ✅ | [Manifest Schema](docs/manifest-schema.md) |
| EventBridge | ✅ | [Deployment Metrics](docs/pipeline-deployment-metrics.md) |
| Lake Formation | ✅ | [Connections Guide](docs/connections.md) |
| Amazon S3 | ✅ | [Storage](docs/manifest-schema.md#storage) |
| AWS Lambda | 🔄 | [Airflow Operators](docs/airflow-aws-operators.md#aws-lambda) |
| Amazon EMR | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#amazon-emr) |
| Amazon Redshift | ✅ | [Airflow Operators](docs/airflow-aws-operators.md#amazon-redshift) |

### Advanced Features
| Feature | Status | Notes |
|---------|--------|-------|
| Multi-region deployment | ✅ | [Stages](docs/manifest-schema.md#stages) |
| Cross-project deployment | ✅ | [Stages](docs/manifest-schema.md#stages) |
| Dependency management | ✅ | [Airflow Operators](docs/airflow-aws-operators.md) |
| Catalog subscriptions | ✅ | [Manifest Schema](docs/manifest-schema.md) |
| Multi-service orchestration | ✅ | [Airflow Operators](docs/airflow-aws-operators.md) |
| Drift detection | 🔮 | Detect configuration drift |
| State management | 🔄 | Comprehensive state tracking |

</details>

---


## Documentation

### Pour Commencer
- **[Guide de Démarrage Rapide](docs/getting-started/quickstart.md)** - Déployez votre première application (10 min)
- **[Guide Administrateur](docs/getting-started/admin-quickstart.md)** - Configurez l'infrastructure (15 min)

### Guides
- **[Manifest d'Application](docs/manifest.md)** - Référence complète de configuration YAML
- **[Commandes CLI](docs/cli-commands.md)** - Toutes les commandes et options disponibles
- **[Actions Bootstrap](docs/bootstrap-actions.md)** - Actions de déploiement automatisées et workflows événementiels
- **[Substitutions & Variables](docs/substitutions-and-variables.md)** - Configuration dynamique
- **[Guide des Connexions](docs/connections.md)** - Configurer les intégrations des services AWS
- **[Intégration GitHub Actions](docs/github-actions-integration.md)** - Configuration de l'automatisation CI/CD
- **[Métriques de Déploiement](docs/pipeline-deployment-metrics.md)** - Surveillance avec EventBridge

### Référence
- **[Schéma du Manifest](docs/manifest-schema.md)** - Validation et structure du schéma YAML
- **[Opérateurs AWS Airflow](docs/airflow-aws-operators.md)** - Référence des opérateurs personnalisés

### Exemples
- **[Guide des Exemples](docs/examples-guide.md)** - Présentation des applications exemples
- **[Notebooks de Données](docs/examples-guide.md#-data-engineering---notebooks)** - Notebooks Jupyter avec Airflow
- **[Entraînement ML](docs/examples-guide.md#-machine-learning---training)** - Entraînement SageMaker avec MLflow
- **[Déploiement ML](docs/examples-guide.md#-machine-learning---deployment)** - Déploiement d'endpoint SageMaker
- **[Tableau de Bord QuickSight](docs/examples-guide.md#-analytics---quicksight-dashboard)** - Tableaux de bord BI avec Glue
- **[Application GenAI](docs/examples-guide.md#-generative-ai)** - Agents Bedrock et bases de connaissances

### Développement
- **[Guide de Développement](docs/development.md)** - Contribution et tests
- **[Aperçu des Tests](tests/README.md)** - Infrastructure de test

### Support
- **Problèmes**: [GitHub Issues](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues)
- **Documentation**: [docs/](docs/)
- **Exemples**: [examples/](examples/)

---

## Avis de Sécurité

⚠️ **NE PAS** installer depuis PyPI - toujours installer depuis le code source officiel AWS.

```bash
# ✅ Correct - Installation depuis le dépôt officiel AWS
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .

# ❌ Incorrect - Ne pas utiliser PyPI
pip install smus-cicd-cli  # Peut contenir du code malveillant
```

---

## Licence

Ce projet est sous licence MIT-0. Voir [LICENSE](../../LICENSE) pour plus de détails.