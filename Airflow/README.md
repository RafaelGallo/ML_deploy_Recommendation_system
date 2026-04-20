# Airflow — Amazon Product Recommender

## DAGs disponíveis

| DAG | Agenda | Descrição |
|-----|--------|-----------|
| `amazon_recommender_retrain` | Segunda 02:00 BRT | Retreina o modelo KNN com dados do BigQuery |
| `amazon_data_quality_check` | Diário 06:00 BRT | Verifica qualidade dos dados e envia relatório |

## Subir o Airflow localmente

```bash
# Na raiz do projeto
cd ML_System_recommendation_products_amazon_products

# Criar rede Docker (compartilhada com os outros serviços)
docker network create recommender_network 2>/dev/null || true

# Subir os serviços principais primeiro
docker-compose up -d

# Inicializar e subir o Airflow
docker-compose -f Airflow/docker-compose-airflow.yml up airflow-init
docker-compose -f Airflow/docker-compose-airflow.yml up -d

# Acessar a UI do Airflow
# http://localhost:8080
# Usuário: admin | Senha: admin
```

## Estrutura

```
Airflow/
├── dags/
│   ├── retrain_dag.py         ← Pipeline de retreinamento semanal
│   └── data_quality_dag.py    ← Verificação diária de qualidade
├── logs/                      ← Logs dos DAGs (gerado automaticamente)
├── plugins/                   ← Plugins customizados (vazio)
├── config/
│   └── airflow.cfg            ← Configuração do Airflow
├── Dockerfile                 ← Imagem customizada com dependências ML
├── requirements.txt           ← Pacotes adicionais
└── docker-compose-airflow.yml ← Orquestração dos serviços Airflow
```

## Executar um DAG manualmente

```bash
# Pelo CLI do Airflow
docker exec -it recommender_network-airflow-scheduler-1 \
  airflow dags trigger amazon_recommender_retrain

# Ou pela UI: http://localhost:8080 → DAGs → amazon_recommender_retrain → Trigger DAG
```

## Variáveis de ambiente usadas

Todas lidas do `.env` da raiz do projeto:
- `GCP_PROJECT_ID` — projeto BigQuery
- `GOOGLE_APPLICATION_CREDENTIALS` — chave JSON do serviço
- `MLFLOW_TRACKING_URI` — URL do servidor MLflow
- `EMAIL_SENDER` / `EMAIL_PASSWORD` — Gmail SMTP
- `GOOGLE_CHAT_WEBHOOK_URL` — webhook do espaço Google Chat
- `EMAIL_SENDER` / `EMAIL_PASSWORD` / `EMAIL_RECIPIENTS` — Gmail SMTP
