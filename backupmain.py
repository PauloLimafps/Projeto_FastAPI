import os
import json
import sys
import weaviate
from confluent_kafka import Consumer
from openai import OpenAI
from dotenv import load_dotenv
from weaviate.classes.init import Auth, Timeout
import weaviate.classes.config as Configure

# 1. Carregar ambiente (.env)
load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    print("❌ ERRO: OPENAI_API_KEY não encontrada no .env!")
    sys.exit(1)

client_openai = OpenAI(api_key=openai_key)

# --- CONFIGURAÇÕES WEAVIATE CLOUD ---
WCD_URL = "https://qqfm6jt5sfcpmiv1f3ciww.c0.us-west3.gcp.weaviate.cloud"
WCD_API_KEY = "aE56eG0rbXRyODF5am4wZF9UbGIyL0UxRHo2NFlMYnlEMm5ieDhHMnRXTUtFRkw0MFZxZGp5NmNvb3NrPV92MjAw"

# 2. Conexão Weaviate CLOUD
print("⏳ 1/3 - Conectando ao Weaviate CLOUD...")
try:
    client_weaviate = weaviate.connect_to_weaviate_cloud(
        cluster_url=WCD_URL,
        auth_credentials=Auth.api_key(WCD_API_KEY),
        headers={
            "X-OpenAI-Api-Key": openai_key  # Para o Weaviate saber como lidar com os vetores
        },
        additional_config=weaviate.classes.init.AdditionalConfig(
            timeout=Timeout(init=30, query=30, insert=30)
        )
    )
    print("✅ Weaviate CLOUD conectado com sucesso!")

    # --- AUTO-SETUP: CRIAR COLEÇÃO SE NÃO EXISTIR ---
    if not client_weaviate.collections.exists("Documento"):
        print("🏗️ Criando coleção 'Documento' na nuvem...")
        client_weaviate.collections.create(
            name="Documento",
            vectorizer_config=Configure.Configure.Vectorizer.text2vec_openai(model="text-embedding-3-small"),
            properties=[
                Configure.Property(name="titulo", data_type=Configure.DataType.TEXT),
                Configure.Property(name="conteudo", data_type=Configure.DataType.TEXT),
                Configure.Property(name="original_id", data_type=Configure.DataType.INT),
            ]
        )
        print("✨ Coleção preparada!")

except Exception as e:
    print(f"❌ ERRO na Conexão/Setup Cloud: {e}")
    sys.exit(1)

# 3. Configuração Kafka (Continua Local no Docker)
print("⏳ 2/3 - Conectando ao Kafka Local...")
conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'v30-migracao-nuvem-final',  # ✅ ID novo para forçar o reenvio de tudo para a nuvem
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': True,
    'session.timeout.ms': 45000
}

consumer = Consumer(conf)
TOPICO = 'ia_projeto.CorporativoIA.dbo.DocumentosInstitucionais'
consumer.subscribe([TOPICO])
print(f"✅ Kafka inscrito no tópico: {TOPICO}")

def get_embedding(text):
    """Gera o vetor via OpenAI."""
    text = text.replace("\n", " ")
    response = client_openai.embeddings.create(input=[text], model="text-embedding-3-small")
    return response.data[0].embedding

print("\n🚀 3/3 - Orquestrador Híbrido Ativo! Sincronizando SQL -> CLOUD...\n")

try:
    # Referência da coleção na nuvem
    colecao_documentos = client_weaviate.collections.get("Documento")

    while True:
        msg = consumer.poll(1.0) 

        if msg is None:
            continue
        
        if msg.error():
            print(f"❌ Erro no Kafka: {msg.error()}")
            continue

        try:
            raw_data = json.loads(msg.value().decode('utf-8'))
            payload_after = raw_data.get('payload', {}).get('after')

            if payload_after:
                titulo = payload_after.get('titulo', 'Sem Título')
                conteudo = payload_after.get('conteudo', 'Sem Conteúdo')
                doc_id = payload_after.get('id')

                print(f"📥 Processando ID: {doc_id} | Título: {titulo}")
                
                # Gerar Embedding
                print(f"🧠 Gerando Vetor na OpenAI...")
                vetor = get_embedding(f"{titulo} {conteudo}")

                # Inserir no Weaviate CLOUD
                print(f"☁️ Fazendo upload para a Nuvem...")
                colecao_documentos.data.insert(
                    properties={
                        "titulo": titulo,
                        "conteudo": conteudo,
                        "original_id": doc_id
                    },
                    vector=vetor
                )
                print(f"✨ SUCESSO: Gravado na Nuvem!\n")
            
        except Exception as e:
            print(f"❌ Erro ao processar mensagem: {e}")

except KeyboardInterrupt:
    print("\n🛑 Encerrando...")
finally:
    consumer.close()
    client_weaviate.close()