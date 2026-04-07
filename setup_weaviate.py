import weaviate
import weaviate.classes as wvc
from weaviate.classes.init import Timeout

# Configuração de conexão robusta para v4 + gRPC
client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
    additional_config=weaviate.classes.init.AdditionalConfig(
        timeout=Timeout(init=10) # 10 segundos de tolerância para o "handshake"
    )
)

try:
    print("⏳ Verificando/Criando coleção no Weaviate...")
    
    # Criando a coleção 'Documento'
    client.collections.create(
        name="Documento",
        description="Documentos institucionais para pesquisa RAG",
        vectorizer_config=None, # Definimos como None pois enviaremos o vetor da OpenAI manualmente
        properties=[
            wvc.config.Property(name="titulo", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="conteudo", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="original_id", data_type=wvc.config.DataType.INT),
        ]
    )
    print("✅ Coleção 'Documento' criada com sucesso no Weaviate (v4)!")

except Exception as e:
    print(f"⚠️ Nota: A coleção pode já existir ou houve um erro: {e}")

finally:
    client.close()