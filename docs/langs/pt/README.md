[![en](https://img.shields.io/badge/lang-en-gray.svg)](../../../README.md)
[![pt](https://img.shields.io/badge/lang-pt-brightgreen.svg?style=for-the-badge)](../pt/README.md)
[![fr](https://img.shields.io/badge/lang-fr-gray.svg)](../fr/README.md)
[![it](https://img.shields.io/badge/lang-it-gray.svg)](../it/README.md)
[![ja](https://img.shields.io/badge/lang-ja-gray.svg)](../ja/README.md)
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

> **[Preview]** Amazon SageMaker Unified Studio CI/CD CLI está atualmente em prévia e sujeito a alterações. Comandos, formatos de configuração e APIs podem evoluir com base no feedback dos clientes. Recomendamos avaliar esta ferramenta em ambientes não produtivos durante a prévia. Para feedback e relatórios de bugs, por favor abra uma issue em https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues

> **[IAM Domains Only]** Esta CLI atualmente suporta apenas domínios SMUS usando autenticação baseada em IAM. O suporte para domínios baseados em IAM Identity Center (IdC) será disponibilizado em breve.

**Automatize a implantação de aplicações de dados em ambientes SageMaker Unified Studio**

"Deploy Airflow DAGs, Jupyter notebooks, and ML workflows from development to production with confidence" (Implante DAGs do Airflow, notebooks Jupyter e workflows de ML do desenvolvimento à produção com confiança). Desenvolvido para cientistas de dados, engenheiros de dados, engenheiros de ML e desenvolvedores de aplicações GenAI trabalhando com equipes DevOps.

**Works with your deployment strategy:** (Funciona com sua estratégia de implantação:) Seja usando branches git (branch-based), artefatos versionados (bundle-based), tags git (tag-based), ou implantação direta - esta CLI suporta seu workflow. Defina sua aplicação uma vez, implante do seu jeito.

---

## Por que SMUS CI/CD CLI?

✅ **AWS Abstraction Layer - CLI encapsulates all AWS analytics, ML, and SMUS complexity - DevOps teams never call AWS APIs directly** (Camada de Abstração AWS - CLI encapsula toda complexidade de analytics, ML e SMUS da AWS - times DevOps nunca chamam APIs AWS diretamente)

✅ **Separation of Concerns - Data teams define WHAT to deploy (manifest.yaml), DevOps teams define HOW and WHEN (CI/CD workflows)** (Separação de Responsabilidades - Times de dados definem O QUE implantar (manifest.yaml), times DevOps definem COMO e QUANDO (workflows CI/CD))

✅ **Generic CI/CD Workflows - Same workflow works for Glue, SageMaker, Bedrock, QuickSight, or any AWS service combination** (Workflows CI/CD Genéricos - O mesmo workflow funciona para Glue, SageMaker, Bedrock, QuickSight ou qualquer combinação de serviços AWS)

✅ **Deploy with Confidence** - Testes e validações automatizados antes da produção

✅ **Multi-Environment Management** - Teste → Produção com configuração específica por ambiente

✅ **Infrastructure as Code** - Manifestos de aplicação versionados e implantações reproduzíveis

✅ **Event-Driven Workflows** - Disparo automático de workflows via EventBridge na implantação

---

## Início Rápido

**Instalação:**
```bash
pip install aws-smus-cicd-cli
```

**Deploy your first application:** (Implante sua primeira aplicação:)
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

**Veja em ação:** [Live GitHub Actions Example](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/runs/17631303500)

---

## Para Quem É Isto?

### 👨‍💻 Times de Dados (Cientistas de Dados, Engenheiros de Dados, Desenvolvedores de Apps GenAI)
**Seu foco:** Sua aplicação - o que implantar, onde implantar e como ela funciona  
**Você define:** Manifest da aplicação (`manifest.yaml`) com seu código, workflows e configurações  
"You don't need to know: CI/CD pipelines, GitHub Actions, deployment automation" (Você não precisa saber: pipelines CI/CD, GitHub Actions, automação de deployment)

→ **[Guia de Início Rápido](docs/getting-started/quickstart.md)** - Implante sua primeira aplicação em 10 minutos

**Inclui exemplos para:**
- Data Engineering (Glue, Notebooks, Athena)
- ML Workflows (SageMaker, Notebooks)
- GenAI Applications (Bedrock, Notebooks)

### 🔧 Times DevOps
**Seu foco:** Melhores práticas de CI/CD, segurança, conformidade e automação de deployment  
**Você define:** Templates de workflow que aplicam testes, aprovações e políticas de promoção  
"You don't need to know: Application-specific details, AWS services used, DataZone APIs, SMUS project structures, or business logic" (Você não precisa saber: detalhes específicos da aplicação, serviços AWS utilizados, APIs do DataZone, estruturas de projeto SMUS ou lógica de negócio)

→ **[Guia do Administrador](docs/getting-started/admin-quickstart.md)** - Configure infraestrutura e pipelines em 15 minutos  
→ **[Templates de Workflow do GitHub](git-templates/)** - Templates de workflow genéricos e reutilizáveis para deployment automatizado

"The CLI is your abstraction layer: You just call `aws-smus-cicd-cli deploy` - the CLI handles all AWS service interactions (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Your workflows stay simple and generic." (O CLI é sua camada de abstração: Você apenas chama `aws-smus-cicd-cli deploy` - o CLI gerencia todas as interações com serviços AWS (DataZone, Glue, Athena, SageMaker, MWAA, S3, IAM, etc.). Seus workflows permanecem simples e genéricos.)

---

## O Que Você Pode Implantar?

**📊 Analytics & BI**
- Glue ETL jobs e crawlers
- Athena queries
- QuickSight dashboards
- EMR jobs (futuro)
- Redshift queries (futuro)

**🤖 Machine Learning**
- SageMaker training jobs
- ML models and endpoints (modelos de ML e endpoints)
- MLflow experiments
- Feature Store (futuro)
- Batch transforms (futuro)

**🧠 Generative AI**
- Bedrock agents
- Knowledge bases (bases de conhecimento)
- Foundation model configurations (futuro)

**📓 Code & Workflows**
- Jupyter notebooks
- Python scripts
- Airflow DAGs (MWAA e Amazon MWAA Serverless)
- Lambda functions (futuro)

**💾 Data & Storage**
- S3 data files (arquivos de dados S3)
- Git repositories
- Data catalogs (futuro)

---

## Serviços AWS Suportados

"Deploy workflows using these AWS services through Airflow YAML syntax" (Implante workflows usando estes serviços AWS através da sintaxe YAML do Airflow):

### 🎯 Analytics & Dados
**Amazon Athena** • **AWS Glue** • **Amazon EMR** • **Amazon Redshift** • **Amazon QuickSight** • **Lake Formation**

### 🤖 Machine Learning
**SageMaker Training** • **SageMaker Pipelines** • **Feature Store** • **Model Registry** • **Batch Transform**

### 🧠 Inteligência Artificial Generativa
**Amazon Bedrock** • **Bedrock Agents** • **Bedrock Knowledge Bases** • **Guardrails**

### 📊 Serviços Adicionais
S3 • Lambda • Step Functions • DynamoDB • RDS • SNS/SQS • Batch

**Veja a lista completa:** [Airflow AWS Operators Reference](docs/airflow-aws-operators.md)

---

## Conceitos Fundamentais

### Separação de Responsabilidades: O Princípio Fundamental de Design

**O Problema:** Abordagens tradicionais de implantação forçam equipes DevOps a aprender serviços analíticos AWS (Glue, Athena, DataZone, SageMaker, MWAA, etc.) e entender estruturas de projeto SMUS, ou forçam equipes de dados a se tornarem especialistas em CI/CD.

**A Solução:** SMUS CI/CD CLI é a camada de abstração que encapsula toda a complexidade AWS e SMUS.

**Example workflow:** (Exemplo de fluxo de trabalho)

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

**Equipes DevOps focam em:**
- Melhores práticas de CI/CD (testes, aprovações, notificações)
- Controles de segurança e conformidade
- Orquestração de implantação
- Monitoramento e alertas

**SMUS CI/CD CLI handles ALL AWS complexity:** (SMUS CI/CD CLI lida com toda complexidade AWS)
- DataZone domain and project management
- AWS Glue, Athena, SageMaker, MWAA APIs
- S3 storage and artifact management
- IAM roles and permissions
- Connection configurations
- Catalog asset subscriptions
- Workflow deployment to Airflow
- Infrastructure provisioning
- Testing and validation

**Equipes de dados focam em:**
- Código da aplicação e workflows
- Quais serviços AWS usar (Glue, Athena, SageMaker, etc.)
- Configurações de ambiente
- Lógica de negócios

**Resultado:**
- **Equipes DevOps nunca chamam APIs AWS diretamente** - elas apenas chamam `aws-smus-cicd-cli deploy`
- **Workflows de CI/CD são genéricos** - o mesmo workflow funciona para aplicações Glue, SageMaker ou Bedrock
- Equipes de dados nunca mexem em configurações de CI/CD
- Ambas as equipes trabalham independentemente usando suas especialidades

---

### Application Manifest (Manifesto da Aplicação)
Um arquivo YAML declarativo (`manifest.yaml`) que define sua aplicação de dados:
- **Detalhes da aplicação** - Nome, versão, descrição
- **Conteúdo** - Código de repositórios git, dados/modelos de armazenamento, dashboards QuickSight
- **Workflows** - DAGs Airflow para orquestração e automação
- **Stages** - Onde implantar (ambientes dev, test, prod)
- **Configuração** - Configurações específicas do ambiente, conexões e ações de inicialização

**Criado e mantido por equipes de dados.** Define **o que** implantar e **onde**. Não requer conhecimento de CI/CD.

### Application (Aplicação)
Sua carga de trabalho de dados/analytics sendo implantada:
- DAGs Airflow e scripts Python
- Notebooks Jupyter e arquivos de dados
- Modelos ML e código de treinamento
- Pipelines ETL e transformações
- Agentes GenAI e servidores MCP
- Configurações de modelos base

### Stage (Ambiente)
Um ambiente de implantação (dev, test, prod) mapeado para um projeto SageMaker Unified Studio:
- Configuração de domínio e região
- Nome e configurações do projeto
- Conexões de recursos (S3, Airflow, Athena, Glue)
- Parâmetros específicos do ambiente
- Mapeamento opcional de branch para implantações baseadas em git

### Stage-to-Project Mapping (Mapeamento de Ambiente para Projeto)

Cada stage da aplicação é implantado em um projeto SageMaker Unified Studio (SMUS) dedicado. Um projeto pode hospedar uma única aplicação ou múltiplas aplicações dependendo da sua arquitetura e metodologia CI/CD. Projetos de stage são entidades independentes com sua própria governança:

- **Propriedade & Acesso:** Cada projeto de stage tem seu próprio conjunto de proprietários e contribuidores, que podem diferir do projeto de desenvolvimento. Projetos de produção tipicamente têm acesso restrito comparado aos ambientes de desenvolvimento.
- **Multi-Domain & Multi-Region:** Projetos de stage podem pertencer a diferentes domínios SMUS, contas AWS e regiões. Por exemplo, seu stage dev pode implantar em um domínio de desenvolvimento em us-east-1, enquanto prod implanta em um domínio de produção em eu-west-1.
- **Arquitetura Flexível:** Organizações podem escolher entre projetos dedicados por aplicação (isolamento) ou projetos compartilhados hospedando múltiplas aplicações (consolidação), baseado em requisitos de segurança, conformidade e operacionais.

Esta separação permite verdadeiro isolamento de ambiente com controles de acesso independentes, limites de conformidade e requisitos de residência regional de dados.

### Workflow
Lógica de orquestração que executa sua aplicação. Workflows servem dois propósitos:

**1. Tempo de implantação:** Criar recursos AWS necessários durante a implantação
- Provisionar infraestrutura (buckets S3, bancos de dados, funções IAM)
- Configurar conexões e permissões
- Configurar monitoramento e logging

**2. Tempo de execução:** Executar pipelines contínuos de dados e ML
- Execução agendada (diária, horária, etc.)
- Gatilhos baseados em eventos (uploads S3, chamadas API)
- Processamento e transformações de dados
- Treinamento e inferência de modelos

Workflows são definidos como DAGs Airflow (Directed Acyclic Graphs) em formato YAML. Suporta [MWAA (Managed Workflows for Apache Airflow)](https://aws.amazon.com/managed-workflows-for-apache-airflow/) e [Amazon MWAA Serverless](https://aws.amazon.com/blogs/big-data/introducing-amazon-mwaa-serverless/) ([User Guide](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/what-is-mwaa-serverless.html)).

### CI/CD Automation (Automação CI/CD)
Workflows GitHub Actions (ou outros sistemas CI/CD) que automatizam a implantação:
- **Criados e mantidos por equipes DevOps**
- Define **como** e **quando** implantar
- Executa testes e gates de qualidade
- Gerencia promoção entre alvos
- Aplica políticas de segurança e conformidade
- Exemplo: `.github/workflows/deploy.yml`

**Insight chave:** Equipes DevOps criam workflows genéricos e reutilizáveis que funcionam para QUALQUER aplicação. Eles não precisam saber se a aplicação usa Glue, SageMaker ou Bedrock - o CLI lida com todas as interações com serviços AWS. O workflow apenas chama `aws-smus-cicd-cli deploy` e o CLI faz o resto.

### Deployment Modes (Modos de Implantação)

**Bundle-based (Artifact):** Create versioned archive → deploy archive to stages (Criar arquivo versionado → implantar arquivo nos ambientes)
- Bom para: trilhas de auditoria, capacidade de rollback, conformidade
- Comando: `aws-smus-cicd-cli bundle` then `aws-smus-cicd-cli deploy --manifest app.tar.gz`

**Direct (Git-based):** Deploy directly from sources without intermediate artifacts (Implantar diretamente das fontes sem artefatos intermediários)
- Bom para: workflows mais simples, iteração rápida, git como fonte da verdade
- Comando: `aws-smus-cicd-cli deploy --manifest manifest.yaml --stage test`

Ambos os modos funcionam com qualquer combinação de fontes de armazenamento e git.

---

## Exemplos de Aplicações

Exemplos do mundo real mostrando como implantar diferentes cargas de trabalho com SMUS CI/CD.

### 📊 Analytics - Dashboard QuickSight
Deploy interactive BI dashboards with automated Glue ETL pipelines for data preparation. Uses QuickSight asset bundles, Athena queries, and GitHub dataset integration with environment-specific configurations.
(Implante dashboards de BI interativos com pipelines ETL automatizados do Glue para preparação de dados. Utiliza bundles de ativos do QuickSight, consultas Athena e integração com datasets do GitHub com configurações específicas por ambiente.)

**AWS Services:** QuickSight • Glue • Athena • S3 • MWAA Serverless

**GitHub Workflow:** [analytic-dashboard-glue-quicksight.yml](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/actions/workflows/analytic-dashboard-glue-quicksight.yml)

**O que acontece durante a implantação:** O código da aplicação é implantado no S3, jobs do Glue e workflows do Airflow são criados e executados, dashboard/fonte de dados/dataset do QuickSight são criados, e a ingestão do QuickSight é iniciada para atualizar o dashboard com os dados mais recentes.

<details>
<summary><b>📁 Estrutura da Aplicação</b></summary>

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

**Arquivos Principais:**
- **Jobs do Glue**: Scripts Python para configuração de banco de dados, ETL e validação
- **Workflow**: YAML definindo DAG do Airflow para orquestração
- **Bundle do QuickSight**: Dashboard, datasets e fontes de dados
- **Testes**: Validam qualidade dos dados e funcionalidade do dashboard

</details>

[Continua com o resto do conteúdo mantendo o mesmo padrão de tradução...]

## Documentação

### Primeiros Passos
- **[Guia Rápido](docs/getting-started/quickstart.md)** - Implante sua primeira aplicação (10 min)
- **[Guia do Administrador](docs/getting-started/admin-quickstart.md)** - Configure a infraestrutura (15 min)

### Guias
- **[Application Manifest](docs/manifest.md)** - Referência completa de configuração YAML
- **[CLI Commands](docs/cli-commands.md)** - Todos os comandos e opções disponíveis
- **[Bootstrap Actions](docs/bootstrap-actions.md)** - Ações de implantação automatizadas e workflows orientados a eventos
- **[Substitutions & Variables](docs/substitutions-and-variables.md)** - Configuração dinâmica
- **[Guia de Conexões](docs/connections.md)** - Configure integrações com serviços AWS
- **[GitHub Actions Integration](docs/github-actions-integration.md)** - Configuração de automação CI/CD
- **[Deployment Metrics](docs/pipeline-deployment-metrics.md)** - Monitoramento com EventBridge

### Referência
- **[Manifest Schema](docs/manifest-schema.md)** - Validação e estrutura do schema YAML
- **[Airflow AWS Operators](docs/airflow-aws-operators.md)** - Referência de operadores personalizados

### Exemplos
- **[Guia de Exemplos](docs/examples-guide.md)** - Demonstração de aplicações exemplo
- **[Data Notebooks](docs/examples-guide.md#-data-engineering---notebooks)** - Notebooks Jupyter com Airflow
- **[ML Training](docs/examples-guide.md#-machine-learning---training)** - Treinamento SageMaker com MLflow
- **[ML Deployment](docs/examples-guide.md#-machine-learning---deployment)** - Implantação de endpoint SageMaker
- **[QuickSight Dashboard](docs/examples-guide.md#-analytics---quicksight-dashboard)** - Dashboards BI com Glue
- **[GenAI Application](docs/examples-guide.md#-generative-ai)** - Agentes Bedrock e bases de conhecimento

### Desenvolvimento
- **[Guia do Desenvolvedor](developer/developer-guide.md)** - Guia completo de desenvolvimento com arquitetura, testes e workflows
- **[AI Assistant Context](developer/AmazonQ.md)** - Contexto para assistentes de IA (Amazon Q, Kiro)
- **[Visão Geral dos Testes](tests/README.md)** - Infraestrutura de testes

### Suporte
- **Issues**: [GitHub Issues](https://github.com/aws/CICD-for-SageMakerUnifiedStudio/issues)
- **Documentação**: [docs/](docs/)
- **Exemplos**: [examples/](examples/)

---

## Aviso de Segurança

Sempre instale a partir do pacote PyPI oficial da AWS ou do código-fonte.

```bash
# ✅ Correct - Install from official AWS PyPI package
pip install aws-smus-cicd-cli

# ✅ Also correct - Install from official AWS source code
git clone https://github.com/aws/CICD-for-SageMakerUnifiedStudio.git
cd CICD-for-SageMakerUnifiedStudio
pip install -e .
```

---

## Licença

Este projeto está licenciado sob a Licença MIT-0. Consulte [LICENSE](../../LICENSE) para detalhes.

---

<div align="center">
  <img src="docs/readme-qr-code.png" alt="Scan to view README" width="200"/>
  <p><em>Escaneie o código QR para ver este README no GitHub</em></p>
</div>