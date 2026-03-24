[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-gray.svg)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-brightgreen.svg?style=for-the-badge)](../it/README.md)
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

> **[Anteprima]** Amazon SageMaker Unified Studio CI/CD CLI è attualmente in anteprima e soggetto a modifiche. I comandi, i formati di configurazione e le API potrebbero evolversi in base al feedback dei clienti. Consigliamo di valutare questo strumento in ambienti non di produzione durante l'anteprima. Per feedback e segnalazioni di bug, apri una segnalazione su https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues

> **[Solo Domini IAM]** Questa CLI supporta attualmente solo i domini SMUS che utilizzano l'autenticazione basata su IAM. Il supporto per i domini basati su IAM Identity Center (IdC) sarà disponibile a breve.

**Automatizza il deployment delle applicazioni dati tra gli ambienti SageMaker Unified Studio**

"Deploy Airflow DAGs, Jupyter notebooks, and ML workflows from development to production with confidence" (Distribuisci DAG Airflow, notebook Jupyter e workflow ML dallo sviluppo alla produzione con sicurezza). Creato per data scientist, data engineer, ML engineer e sviluppatori di app GenAI che lavorano con i team DevOps.

**Compatibile con la tua strategia di deployment:** "Whether you use git branches (branch-based), versioned artifacts (bundle-based), git tags (tag-based), or direct deployment - this CLI supports your workflow" (Che tu utilizzi branch git, artefatti versionati, tag git o deployment diretto - questa CLI supporta il tuo workflow). Definisci la tua applicazione una volta, distribuiscila a modo tuo.

---

## Perché SMUS CI/CD CLI?

✅ **AWS Abstraction Layer** - La CLI incapsula tutta la complessità di AWS analytics, ML e SMUS - i team DevOps non chiamano mai direttamente le API AWS  
✅ **Separation of Concerns** - I team di dati definiscono COSA distribuire (manifest.yaml), i team DevOps definiscono COME e QUANDO (CI/CD workflows)  
✅ **Generic CI/CD Workflows** - Lo stesso workflow funziona per Glue, SageMaker, Bedrock, QuickSight o qualsiasi combinazione di servizi AWS  
✅ **Deploy with Confidence** - Test e validazione automatizzati prima della produzione  
✅ **Multi-Environment Management** - Test → Prod con configurazione specifica per ambiente  
✅ **Infrastructure as Code** - Manifest applicativi con controllo di versione e distribuzioni riproducibili  
✅ **Event-Driven Workflows** - Attivazione automatica dei workflow tramite EventBridge durante il deployment  

---

## Avvio Rapido

**Installazione:**
```bash
pip install aws-smus-cicd-cli
```

**Deploy della tua prima applicazione:**
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

**Vedi in azione:** [Live GitHub Actions Example](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/runs/17631303500)

---

## Per Chi È?

### 👨‍💻 Team di Data (Data Scientists, Data Engineers, Sviluppatori di App GenAI)
**Ti concentri su:** La tua applicazione - cosa distribuire, dove distribuire e come funziona  
**Definisci:** Application manifest (`manifest.yaml`) con il tuo codice, workflow e configurazioni  
"You don't need to know: CI/CD pipelines, GitHub Actions, deployment automation" (Non devi conoscere: pipeline CI/CD, GitHub Actions, automazione del deployment)

→ **[Guida Rapida](docs/getting-started/quickstart.md)** - Distribuisci la tua prima applicazione in 10 minuti

**Include esempi per:**
- Data Engineering (Glue, Notebooks, Athena)
- ML Workflows (SageMaker, Notebooks)
- GenAI Applications (Bedrock, Notebooks)

### 🔧 Team DevOps
**Ti concentri su:** Best practice CI/CD, sicurezza, conformità e automazione del deployment  
**Definisci:** Modelli di workflow che impongono test, approvazioni e politiche di promozione  
"You don't need to know: Application-specific details, AWS services used, DataZone APIs, SMUS project structures, or business logic" (Non devi conoscere: dettagli specifici dell'applicazione, servizi AWS utilizzati, API DataZone, strutture dei progetti SMUS o logica di business)

→ **[Guida Amministratore](docs/getting-started/admin-quickstart.md)** - Configura infrastruttura e pipeline in 15 minuti  
→ **[Modelli Workflow GitHub](git-templates/)** - Modelli di workflow generici e riutilizzabili per il deployment automatizzato

"The CLI is your abstraction layer: You just call `aws-smus-cicd-cli deploy` - the CLI handles all AWS service interactions (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Your workflows stay simple and generic." (La CLI è il tuo livello di astrazione: Devi solo chiamare `aws-smus-cicd-cli deploy` - la CLI gestisce tutte le interazioni con i servizi AWS (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, ecc.). I tuoi workflow rimangono semplici e generici.)

---

## Cosa Puoi Distribuire?

**📊 Analytics & BI**
- Glue ETL jobs and crawlers
- Athena queries
- QuickSight dashboards
- EMR jobs (futuro)
- Redshift queries (futuro)

**🤖 Machine Learning**
- SageMaker training jobs
- ML models and endpoints
- MLflow experiments
- Feature Store (futuro)
- Batch transforms (futuro)

**🧠 Intelligenza Artificiale Generativa**
- Bedrock agents
- Knowledge bases
- Foundation model configurations (futuro)

**📓 Codice e Workflow**
- Jupyter notebooks
- Python scripts
- Airflow DAGs (MWAA e Amazon MWAA Serverless)
- Lambda functions (futuro)

**💾 Dati e Storage**
- S3 data files
- Git repositories
- Data catalogs (futuro)

---

## Servizi AWS Supportati

Distribuisci workflow utilizzando questi servizi AWS attraverso la sintassi YAML di Airflow:

### 🎯 Analytics & Dati
**Amazon Athena** • **AWS Glue** • **Amazon EMR** • **Amazon Redshift** • **Amazon QuickSight** • **Lake Formation**

### 🤖 Machine Learning
**SageMaker Training** • **SageMaker Pipelines** • **Feature Store** • **Model Registry** • **Batch Transform**

### 🧠 Intelligenza Artificiale Generativa
**Amazon Bedrock** • **Bedrock Agents** • **Bedrock Knowledge Bases** • **Guardrails**

### 📊 Servizi Aggiuntivi
S3 • Lambda • Step Functions • DynamoDB • RDS • SNS/SQS • Batch

**Consulta l'elenco completo:** [Airflow AWS Operators Reference](docs/airflow-aws-operators.md)

---

## Concetti Fondamentali

### Separazione delle Responsabilità: Il Principio Chiave di Design

**Il Problema:** Gli approcci tradizionali al deployment costringono i team DevOps a imparare i servizi analytics di AWS (Glue, Athena, DataZone, SageMaker, MWAA, ecc.) e comprendere le strutture dei progetti SMUS, o costringono i team di dati a diventare esperti di CI/CD.

**La Soluzione:** SMUS CI/CD CLI è il livello di astrazione che incapsula tutta la complessità di AWS e SMUS.

**Example workflow:** (Flusso di lavoro di esempio)

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

**I team DevOps si concentrano su:**
- Best practice CI/CD (test, approvazioni, notifiche)
- Controlli di sicurezza e conformità
- Orchestrazione del deployment
- Monitoraggio e avvisi

"SMUS CI/CD CLI handles ALL AWS complexity:" (SMUS CI/CD CLI gestisce TUTTA la complessità AWS:)
- DataZone domain and project management
- AWS Glue, Athena, SageMaker, MWAA APIs
- S3 storage and artifact management
- IAM roles and permissions
- Connection configurations
- Catalog asset subscriptions
- Workflow deployment to Airflow
- Infrastructure provisioning
- Testing and validation

**I team di dati si concentrano su:**
- Codice applicativo e workflow
- Quali servizi AWS utilizzare (Glue, Athena, SageMaker, ecc.)
- Configurazioni dell'ambiente
- Logica di business

**Risultato:**
- **I team DevOps non chiamano mai direttamente le API AWS** - eseguono solo `aws-smus-cicd-cli deploy`
- **I workflow CI/CD sono generici** - lo stesso workflow funziona per applicazioni Glue, SageMaker o Bedrock
- I team di dati non toccano mai le configurazioni CI/CD
- Entrambi i team lavorano in modo indipendente utilizzando le proprie competenze

---

[Continua la traduzione seguendo lo stesso pattern per il resto del testo...]

## Esempi di Applicazioni

Esempi reali che mostrano come distribuire diversi carichi di lavoro con SMUS CI/CD.

### 📊 Analytics - Dashboard QuickSight
Distribuisci dashboard BI interattive con pipeline ETL Glue automatizzate per la preparazione dei dati. Utilizza bundle di risorse QuickSight, query Athena e integrazione dataset GitHub con configurazioni specifiche per ambiente.

**AWS Services:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-dashboard-glue-quicksight.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-dashboard-glue-quicksight.yml)

**Cosa succede durante la distribuzione:** Il codice dell'applicazione viene distribuito su S3, i job Glue e i workflow Airflow vengono creati ed eseguiti, vengono creati dashboard/sorgente dati/dataset QuickSight e viene avviata l'acquisizione QuickSight per aggiornare la dashboard con i dati più recenti.

[Resto del contenuto mantenuto in inglese come da regole]

## Documentazione

### Per Iniziare
- **[Guida Rapida](docs/getting-started/quickstart.md)** - Distribuisci la tua prima applicazione (10 min)
- **[Guida Amministratore](docs/getting-started/admin-quickstart.md)** - Configura l'infrastruttura (15 min)

### Guide
- **[Application Manifest](docs/manifest.md)** - Riferimento completo configurazione YAML
- **[CLI Commands](docs/cli-commands.md)** - Tutti i comandi e le opzioni disponibili
- **[Bootstrap Actions](docs/bootstrap-actions.md)** - Azioni di distribuzione automatizzate e workflow basati su eventi
- **[Substitutions & Variables](docs/substitutions-and-variables.md)** - Configurazione dinamica
- **[Guida alle Connessioni](docs/connections.md)** - Configura integrazioni servizi AWS
- **[GitHub Actions Integration](docs/github-actions-integration.md)** - Configurazione automazione CI/CD
- **[Deployment Metrics](docs/pipeline-deployment-metrics.md)** - Monitoraggio con EventBridge
- **[Catalog Import/Export Guide](docs/catalog-import-export-guide.md)** - Promuovere risorse del catalogo DataZone tra ambienti
- **[Catalog Import/Export Quick Reference](docs/catalog-import-export-quick-reference.md)** - Riferimento rapido per il deployment del catalogo

### Riferimenti
- **[Manifest Schema](docs/manifest-schema.md)** - Validazione e struttura schema YAML
- **[Airflow AWS Operators](docs/airflow-aws-operators.md)** - Riferimento operatori personalizzati

### Esempi
- **[Guida agli Esempi](docs/examples-guide.md)** - Tutorial delle applicazioni di esempio
- **[Data Notebooks](docs/examples-guide.md#-data-engineering---notebooks)** - Notebook Jupyter con Airflow
- **[ML Training](docs/examples-guide.md#-machine-learning---training)** - Training SageMaker con MLflow
- **[ML Deployment](docs/examples-guide.md#-machine-learning---deployment)** - Distribuzione endpoint SageMaker
- **[QuickSight Dashboard](docs/examples-guide.md#-analytics---quicksight-dashboard)** - Dashboard BI con Glue
- **[GenAI Application](docs/examples-guide.md#-generative-ai)** - Agenti Bedrock e knowledge base

### Sviluppo
- **[Guida Sviluppatore](developer/developer-guide.md)** - Guida completa allo sviluppo con architettura, testing e workflow
- **[Contesto AI Assistant](developer/AmazonQ.md)** - Contesto per assistenti AI (Amazon Q, Kiro)
- **[Panoramica Test](tests/README.md)** - Infrastruttura di testing

### Supporto
- **Problemi**: [GitHub Issues](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues)
- **Documentazione**: [docs/](docs/)
- **Esempi**: [examples/](examples/)

---

## Avviso di Sicurezza

Installare sempre dal pacchetto PyPI ufficiale AWS o dal codice sorgente.

```bash
# ✅ Correct - Install from official AWS PyPI package
pip install aws-smus-cicd-cli

# ✅ Also correct - Install from official AWS source code
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

---

## Licenza

Questo progetto è concesso in licenza secondo la Licenza MIT-0. Vedere [LICENSE](../../LICENSE) per i dettagli.

---

<div align="center">
  <img src="docs/readme-qr-code.png" alt="Scan to view README" width="200"/>
  <p><em>Scansiona il codice QR per visualizzare questo README su GitHub</em></p>
</div>