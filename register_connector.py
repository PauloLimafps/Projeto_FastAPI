import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

DEBEZIUM_URL = "http://localhost:8083/connectors"

connector_config = {
    "name": "sqlserver-research-connector",
    "config": {
        "connector.class": "io.debezium.connector.sqlserver.SqlServerConnector",
        "database.hostname": "host.docker.internal",
        "database.port": "1433",
        "database.user": "rafael_lima",
        "database.password": "core@2025",
        "database.names": "CorporativoIA",
        "topic.prefix": "ia_projeto",
        "schema.history.internal.kafka.bootstrap.servers": "kafka:29092",
        "schema.history.internal.kafka.topic": "schemahistory.ia_projeto_research",
        "database.encrypt": "false",
        "database.trustServerCertificate": "true",
        "snapshot.mode": "initial"
    }
}

def register():
    # Deleta se já existir para limpar o estado
    requests.delete(f"{DEBEZIUM_URL}/{connector_config['name']}")
    
    response = requests.post(
        DEBEZIUM_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(connector_config)
    )
    if response.status_code in [200, 201]:
        print("✅ Conector registrado!")
    else:
        print(f"❌ Erro: {response.text}")

if __name__ == "__main__":
    register()