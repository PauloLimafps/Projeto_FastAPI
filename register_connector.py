import requests   # Biblioteca HTTP para realizar chamadas REST à API do Kafka Connect (Debezium)
import json       # Para serializar o dicionário de configuração do conector como string JSON
import os         # Acesso a variáveis de ambiente (importado mas não utilizado diretamente aqui)
from dotenv import load_dotenv  # Carrega variáveis definidas no arquivo .env para o ambiente do processo

# Carrega as variáveis de ambiente do arquivo .env
# (as credenciais do SQL Server são lidas com os.getenv e injetadas no connector_config)
load_dotenv()

# URL base da API REST do Kafka Connect onde o Debezium é gerenciado
# O Debezium roda como um plugin do Kafka Connect na porta 8083 (padrão)
DEBEZIUM_URL = "http://localhost:8083/connectors"

# ─── Payload de Configuração do Conector Debezium ─────────────────────────────

# Dicionário completo com a especificação do conector CDC para o SQL Server
# Este payload é enviado via HTTP POST para a API REST do Kafka Connect
connector_config = {
    "name": "sqlserver-research-connector",  # Nome único do conector no Kafka Connect
    "config": {
        # Classe Java do plugin Debezium responsável por capturar mudanças do SQL Server
        "connector.class": "io.debezium.connector.sqlserver.SqlServerConnector",

        # ── Configurações de Conexão com o SQL Server ─────────────────────────
        # "host.docker.internal" é um hostname especial do Docker que aponta para o host físico
        # usado porque o SQL Server roda no host e o Debezium roda dentro de um container
        "database.hostname": "host.docker.internal",
        "database.port": "1433",             # Porta padrão do SQL Server
        "database.user": os.getenv("SQLSERVER_USER"),        # Lido do .env — SQLSERVER_USER
        "database.password": os.getenv("SQLSERVER_PASSWORD"), # Lido do .env — SQLSERVER_PASSWORD
        "database.names": "CHAT_RAG",   # Nome do banco de dados monitorado pelo CDC

        # ── Configuração de Tópicos Kafka ──────────────────────────────────────
        # Prefixo usado na formação automática dos nomes dos tópicos pelo Debezium
        # Padrão resultante: {topic.prefix}.{database}.{schema}.{table}
        # Ex: ia_projeto.CorporativoIA.dbo.DocumentosInstitucionais
        "topic.prefix": "ia_projeto",

        # Endereço do Kafka INTERNO (rede Docker) para armazenar o histórico de schemas do banco
        # Necessário para que o Debezium entenda o DDL (CREATE/ALTER TABLE) ao longo do tempo
        "schema.history.internal.kafka.bootstrap.servers": "kafka:29092",
        "schema.history.internal.kafka.topic": "schemahistory.ia_projeto_research",

        # ── Configurações de Segurança de Conexão (TLS/SSL) ───────────────────
        # Desabilita criptografia TLS — adequado apenas para ambiente de desenvolvimento
        # Em produção deve ser "true" com certificado válido
        "database.encrypt": "false",
        # Confia no certificado do servidor sem validação de CA — adequado apenas para dev
        "database.trustServerCertificate": "true",

        # ── Modo de Snapshot ──────────────────────────────────────────────────
        # "initial": na primeira execução, captura todos os registros existentes na tabela
        # e depois monitora apenas as mudanças incrementais (INSERT/UPDATE/DELETE)
        "snapshot.mode": "initial"
    }
}

# ─── Função de Registro do Conector ────────────────────────────────────────────

def register():
    """
    Registra o conector Debezium no Kafka Connect.
    Antes de registrar, deleta o conector existente com o mesmo nome para garantir
    um estado limpo (evita conflitos de configuração entre versões).
    """
    # Remove o conector anterior, se existir — garante estado limpo a cada execução
    # Status 404 (não encontrado) é esperado e não causa problema; o código não verifica
    # Deleta se já existir para limpar o estado
    requests.delete(f"{DEBEZIUM_URL}/{connector_config['name']}")
    
    # Envia a nova configuração do conector via POST à API REST do Kafka Connect
    response = requests.post(
        DEBEZIUM_URL,
        headers={"Content-Type": "application/json"},  # Informa ao Kafka Connect que o body é JSON
        data=json.dumps(connector_config)              # Serializa o dict Python como string JSON
    )

    # Verifica o status da resposta:
    # 201 Created = conector criado com sucesso
    # 200 OK = conector atualizado (comportamento de alguns Kafka Connect versions)
    if response.status_code in [200, 201]:
        print("✅ Conector registrado!")
    else:
        # Exibe o corpo da resposta de erro para facilitar o diagnóstico
        print(f"❌ Erro: {response.text}")

# ─── Ponto de Entrada ──────────────────────────────────────────────────────────

# Garante que register() só é executado quando o script é chamado diretamente
# (ex: `python register_connector.py`), não quando é importado como módulo
if __name__ == "__main__":
    register()