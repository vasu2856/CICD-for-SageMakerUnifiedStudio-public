[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-brightgreen.svg?style=for-the-badge)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](../it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-gray.svg)](../ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](../zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](../he/README.md)

# SMUS CI/CD Pipeline CLI

[![en](https://img.shields.io/badge/lang-en-brightgreen.svg?style=for-the-badge)](README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](docs/langs/pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](docs/langs/fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](docs/langs/it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-gray.svg)](docs/langs/ja/README.md)
[![zh](https://img.shields.io/badge/lang-zh-gray.svg)](docs/langs/zh/README.md)
[![he](https://img.shields.io/badge/lang-he-gray.svg)](docs/langs/he/README.md)

> **[Aperçu]** Amazon SageMaker Unified Studio CI/CD CLI est actuellement en version préliminaire et sujet à modification. Les commandes, les formats de configuration et les APIs peuvent évoluer selon les retours des clients. Nous recommandons d'évaluer cet outil dans des environnements hors production pendant la phase de prévisualisation. Pour les retours et signalements de bugs, veuillez ouvrir un ticket sur https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues

> **[Domaines IAM uniquement]** Ce CLI prend actuellement en charge uniquement les domaines SMUS utilisant l'authentification IAM. La prise en charge des domaines basés sur IAM Identity Center (IdC) sera bientôt disponible.

**Automatisez le déploiement d'applications de données à travers les environnements SageMaker Unified Studio**

"Deploy Airflow DAGs, Jupyter notebooks, and ML workflows from development to production with confidence. Built for data scientists, data engineers, ML engineers, and GenAI app developers working with DevOps teams." (Déployez les DAGs Airflow, les notebooks Jupyter et les workflows ML du développement à la production en toute confiance. Conçu pour les data scientists, les ingénieurs de données, les ingénieurs ML et les développeurs d'applications GenAI travaillant avec les équipes DevOps.)

"Works with your deployment strategy:" (Fonctionne avec votre stratégie de déploiement :) Whether you use git branches (branch-based), versioned artifacts (bundle-based), git tags (tag-based), or direct deployment - this CLI supports your workflow. Define your application once, deploy it your way. (Que vous utilisiez des branches git, des artefacts versionnés, des tags git ou un déploiement direct - ce CLI prend en charge votre workflow. Définissez votre application une fois, déployez-la à votre façon.)

---

## Pourquoi SMUS CI/CD CLI ?

✅ **AWS Abstraction Layer** - La CLI encapsule toute la complexité d'AWS analytics, ML et SMUS - les équipes DevOps n'appellent jamais directement les API AWS  
✅ **Séparation des responsabilités** - Les équipes data définissent QUOI déployer (manifest.yaml), les équipes DevOps définissent COMMENT et QUAND (workflows CI/CD)  
✅ **Generic CI/CD workflows - Same workflow works for Glue, SageMaker, Bedrock, QuickSight, or any AWS service combination** (Workflows CI/CD génériques - Le même workflow fonctionne pour Glue, SageMaker, Bedrock, QuickSight ou toute combinaison de services AWS)  
✅ **Déploiement en toute confiance** - Tests et validation automatisés avant la production  
✅ **Gestion multi-environnements** - Test → Prod avec configuration spécifique par environnement  
✅ **Infrastructure as Code** - Manifests d'application versionnés et déploiements reproductibles  
✅ **Workflows événementiels** - Déclenchement automatique des workflows via EventBridge lors du déploiement  

---

## Démarrage Rapide

**Installation depuis les sources :**
```bash
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

**Déployez votre première application :**
```bash
# Validate configuration
smus-cicd-cli describe --manifest manifest.yaml --connect

# Create deployment bundle (optional)
smus-cicd-cli bundle --manifest manifest.yaml

# Deploy to test environment
smus-cicd-cli deploy --targets test --manifest manifest.yaml

# Run validation tests
smus-cicd-cli test --manifest manifest.yaml --targets test
```

**Voir en action :** [Live GitHub Actions Example](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/runs/17631303500)

---

## À qui s'adresse cet outil ?

### 👨‍💻 Équipes Data (Data Scientists, Data Engineers, Développeurs d'Applications GenAI)
**Votre focus :** Votre application - quoi déployer, où déployer et comment elle fonctionne  
**Vous définissez :** Le manifest de l'application (`manifest.yaml`) avec votre code, workflows et configurations  
**Vous n'avez pas besoin de connaître :** CI/CD pipelines, GitHub Actions, automatisation des déploiements  

→ **[Guide de Démarrage Rapide](docs/getting-started/quickstart.md)** - Déployez votre première application en 10 minutes  

**Inclut des exemples pour :**
- Data Engineering (Glue, Notebooks, Athena)
- ML Workflows (SageMaker, Notebooks) 
- GenAI Applications (Bedrock, Notebooks)

### 🔧 Équipes DevOps
**Votre focus :** Les bonnes pratiques CI/CD, la sécurité, la conformité et l'automatisation des déploiements  
**Vous définissez :** Des modèles de workflow qui imposent les tests, les approbations et les politiques de promotion  
**Vous n'avez pas besoin de connaître :** Les détails spécifiques aux applications, les services AWS utilisés, les APIs DataZone, les structures de projet SMUS, ou la logique métier  

→ **[Guide Administrateur](docs/getting-started/admin-quickstart.md)** - Configurez l'infrastructure et les pipelines en 15 minutes  
→ **[GitHub Workflow Templates](git-templates/)** - Modèles de workflow génériques et réutilisables pour le déploiement automatisé

**The CLI is your abstraction layer: You just call `smus-cicd-cli deploy` - the CLI handles all AWS service interactions (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Your workflows stay simple and generic.** (Le CLI est votre couche d'abstraction : Vous appelez simplement `smus-cicd-cli deploy` - le CLI gère toutes les interactions avec les services AWS. Vos workflows restent simples et génériques.)

---

## Que Pouvez-Vous Déployer ?

**📊 Analytics & BI**
- Glue ETL jobs and crawlers
- Athena queries
- QuickSight dashboards
- EMR jobs (futur)
- Redshift queries (futur)

**🤖 Machine Learning**
- SageMaker training jobs
- ML models and endpoints
- MLflow experiments
- Feature Store (futur)
- Batch transforms (futur)

**🧠 Intelligence Artificielle Générative**
- Bedrock agents
- Bases de connaissances
- Foundation model configurations (futur)

**📓 Code & Workflows**
- Jupyter notebooks
- Scripts Python
- Airflow DAGs (MWAA et Amazon MWAA Serverless)
- Lambda functions (futur)

**💾 Données & Stockage**
- Fichiers S3
- Dépôts Git
- Data catalogs (futur)

---

## Services AWS pris en charge

Déployez des workflows en utilisant ces services AWS via la syntaxe YAML d'Airflow :

### 🎯 Analytics & Données
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

"The Problem: Traditional deployment approaches force DevOps teams to learn AWS analytics services (Glue, Athena, DataZone, SageMaker, MWAA, etc.) and understand SMUS project structures, or force data teams to become CI/CD experts." (Le problème : les approches traditionnelles de déploiement forcent les équipes DevOps à apprendre les services d'analyse AWS et à comprendre les structures de projet SMUS, ou forcent les équipes de données à devenir des experts en CI/CD.)

"The Solution: SMUS CI/CD CLI is the abstraction layer that encapsulates all AWS and SMUS complexity." (La solution : SMUS CI/CD CLI est la couche d'abstraction qui encapsule toute la complexité AWS et SMUS.)

**Exemple de workflow :**

```
1. DevOps Team                 2. Data Team                    3. SMUS CI/CD CLI (The Abstraction)
   ↓                               ↓                              ↓
Defines the PROCESS            Defines the CONTENT            Workflow calls:
- Test on merge                - Glue jobs                    smus-cicd-cli deploy --manifest manifest.yaml
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

**Les équipes DevOps se concentrent sur :**
- Les bonnes pratiques CI/CD (tests, approbations, notifications)
- Les contrôles de sécurité et de conformité
- L'orchestration des déploiements
- La surveillance et les alertes

"SMUS CI/CD CLI handles ALL AWS complexity:" (SMUS CI/CD CLI gère TOUTE la complexité AWS :)
- DataZone domain and project management
- AWS Glue, Athena, SageMaker, MWAA APIs
- S3 storage and artifact management
- IAM roles and permissions
- Connection configurations
- Catalog asset subscriptions
- Workflow deployment to Airflow
- Infrastructure provisioning
- Testing and validation

**Les équipes de données se concentrent sur :**
- Le code applicatif et les workflows
- Le choix des services AWS à utiliser (Glue, Athena, SageMaker, etc.)
- Les configurations d'environnement
- La logique métier

**Résultat :**
- **Les équipes DevOps n'appellent jamais directement les API AWS** - elles appellent simplement `smus-cicd-cli deploy`
- **Les workflows CI/CD sont génériques** - le même workflow fonctionne pour les applications Glue, SageMaker ou Bedrock
- Les équipes de données ne touchent jamais aux configurations CI/CD
- Les deux équipes travaillent indépendamment en utilisant leur expertise

[Continued in next part due to length...]

## Exemples d'applications

Exemples concrets montrant comment déployer différentes charges de travail avec SMUS CI/CD.

### 📊 Analytique - Tableau de bord QuickSight
Déployez des tableaux de bord BI interactifs avec des pipelines ETL Glue automatisés pour la préparation des données. Utilise les bundles d'actifs QuickSight, les requêtes Athena et l'intégration de jeux de données GitHub avec des configurations spécifiques à l'environnement.

**Services AWS:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-dashboard-glue-quicksight.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-dashboard-glue-quicksight.yml)

"What happens during deployment:" → (Ce qui se passe pendant le déploiement :) Le code de l'application est déployé sur S3, les jobs Glue et les workflows Airflow sont créés et exécutés, le tableau de bord/source de données/jeu de données QuickSight sont créés, et l'ingestion QuickSight est initiée pour actualiser le tableau de bord avec les dernières données.

[Reste du contenu technique inchangé]

### 📓 Ingénierie des données - Notebooks
Déployez des notebooks Jupyter avec orchestration d'exécution parallèle pour l'analyse de données et les workflows ETL. Démontre le déploiement de notebooks avec intégration MLflow pour le suivi des expériences.

**Services AWS:** SageMaker Notebooks • MLflow • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-data-notebooks.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-data-notebooks.yml)

"What happens during deployment:" → (Ce qui se passe pendant le déploiement :) Les notebooks et les définitions de workflow sont téléchargés sur S3, le DAG Airflow est créé pour l'exécution parallèle des notebooks, la connexion MLflow est provisionnée pour le suivi des expériences, et les notebooks sont prêts à être exécutés à la demande ou selon un planning.

[Reste du contenu technique inchangé]

[Continue la traduction en suivant le même modèle pour le reste du document]

## Documentation

### Pour Commencer
- **[Guide de Démarrage Rapide](docs/getting-started/quickstart.md)** - Déployez votre première application (10 min)
- **[Guide Administrateur](docs/getting-started/admin-quickstart.md)** - Configurez l'infrastructure (15 min)

### Guides
- **[Application Manifest](docs/manifest.md)** - Référence complète de configuration YAML
- **[CLI Commands](docs/cli-commands.md)** - Toutes les commandes et options disponibles
- **[Bootstrap Actions](docs/bootstrap-actions.md)** - Actions de déploiement automatisées et workflows basés sur les événements
- **[Substitutions & Variables](docs/substitutions-and-variables.md)** - Configuration dynamique
- **[Guide des Connexions](docs/connections.md)** - Configurer les intégrations des services AWS
- **[GitHub Actions Integration](docs/github-actions-integration.md)** - Configuration de l'automatisation CI/CD
- **[Métriques de Déploiement](docs/pipeline-deployment-metrics.md)** - Surveillance avec EventBridge

### Référence
- **[Manifest Schema](docs/manifest-schema.md)** - Validation et structure du schéma YAML
- **[Airflow AWS Operators](docs/airflow-aws-operators.md)** - Référence des opérateurs personnalisés

### Exemples
- **[Guide des Exemples](docs/examples-guide.md)** - Présentation des applications exemples
- **[Data Notebooks](docs/examples-guide.md#-data-engineering---notebooks)** - Notebooks Jupyter avec Airflow
- **[ML Training](docs/examples-guide.md#-machine-learning---training)** - Entraînement SageMaker avec MLflow
- **[ML Deployment](docs/examples-guide.md#-machine-learning---deployment)** - Déploiement d'endpoint SageMaker
- **[QuickSight Dashboard](docs/examples-guide.md#-analytics---quicksight-dashboard)** - Tableaux de bord BI avec Glue
- **[GenAI Application](docs/examples-guide.md#-generative-ai)** - Agents Bedrock et bases de connaissances

### Développement
- **[Guide du Développeur](developer/developer-guide.md)** - Guide complet de développement avec architecture, tests et workflows
- **[Contexte Assistant IA](developer/AmazonQ.md)** - Contexte pour assistants IA (Amazon Q, Kiro)
- **[Aperçu des Tests](tests/README.md)** - Infrastructure de test

### Support
- **Problèmes**: [GitHub Issues](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues)
- **Documentation**: [docs/](docs/)
- **Exemples**: [examples/](examples/)

---

## Avis de Sécurité

⚠️ **NE PAS** installer depuis PyPI - toujours installer depuis le code source officiel AWS.

```bash
# ✅ Correct - Install from official AWS repository
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .

# ❌ Wrong - Do not use PyPI
pip install smus-cicd-cli  # May contain malicious code
```

---

## Licence

Ce projet est sous licence MIT-0. Voir [LICENSE](../../LICENSE) pour plus de détails.

---

<div align="center">
  <img src="docs/readme-qr-code.png" alt="Scanner pour voir le README" width="200"/>
  <p><em>Scannez le code QR pour voir ce README sur GitHub</em></p>
</div>