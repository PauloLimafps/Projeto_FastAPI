# Acesso às variáveis de ambiente do .env
import os
# SDK principal do banco de dados vetorial Weaviate
import weaviate
# Atalho para as classes de configuração de coleção do Weaviate
import weaviate.classes as wvc
# Auth: autenticação; Timeout: controle de espera
from weaviate.classes.init import Auth, Timeout
# Carrega variáveis do arquivo .env
from dotenv import load_dotenv

# Carrega as variáveis do .env (WCD_URL, WCD_API_KEY, OPENAI_API_KEY)
load_dotenv()

# ─── Conexão com o Weaviate Cloud ─────────────────────────────────────────────

# Conecta ao mesmo cluster Cloud usado por main.py e orquestrador.py
# Credenciais lidas do .env — nunca hardcoded no código-fonte
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=os.getenv("WCD_URL"),
    auth_credentials=Auth.api_key(os.getenv("WCD_API_KEY")),
    # Necessário caso o Weaviate use OpenAI internamente
    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
)

# ─── Criação da Coleção (Schema) ──────────────────────────────────────────────

try:
    print("⏳ Verificando/Criando coleção no Weaviate...")

    # Criando a coleção 'Documento'
    # Cria a coleção "Documento" com seu schema de propriedades no Weaviate Cloud
    client.collections.create(
        # Nome da coleção (case-sensitive no Weaviate)
        name="Documento",
        # Descrição para documentação
        description="Documentos institucionais para pesquisa RAG",
        # Definimos como None pois enviaremos o vetor da OpenAI manualmente
        vectorizer_config=None,
        # vectorizer_config=None: o Weaviate não vai gerar vetores automaticamente
        # Os embeddings serão gerados externamente pela OpenAI (no main.py) e enviados explicitamente

        # Define as propriedades (campos) da coleção e seus respectivos tipos de dados
        properties=[
            # Título do documento ou do chunk (ex: "Manual de Avaliação - Parte 1")
            wvc.config.Property(
                name="titulo", data_type=wvc.config.DataType.TEXT),
            # Conteúdo textual do chunk do documento (o texto bruto usado na busca semântica)
            wvc.config.Property(
                name="conteudo", data_type=wvc.config.DataType.TEXT),
            # ID original do documento no SQL Server (para rastreabilidade entre sistemas)
            wvc.config.Property(name="original_id",
                                data_type=wvc.config.DataType.INT),
        ]
    )
    print("✅ Coleção 'Documento' criada com sucesso no Weaviate (v4)!")

except Exception as e:
    # O Weaviate lança exceção se a coleção já existir — esse é o caso mais comum de erro aqui
    # Idealmente deveria usar client.collections.exists() antes de criar (ver melhorias)
    print(f"⚠️ Nota: A coleção pode já existir ou houve um erro: {e}")

finally:
    # Garante que a conexão seja fechada independentemente do resultado (sucesso ou exceção)
    # Importante para liberar recursos TCP e evitar ResourceWarning
    client.close()
