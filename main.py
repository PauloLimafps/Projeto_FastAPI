import os
import json
import sys
import weaviate
import fitz  # PyMuPDF
from confluent_kafka import Consumer
from openai import OpenAI
from dotenv import load_dotenv
from weaviate.classes.init import Auth, Timeout
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Carregar ambiente e fatiador
load_dotenv()
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# O "Fatiador" garante que o Moodle receba respostas precisas e não textos gigantes
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,    # Cada pedaço terá ~1000 caracteres
    chunk_overlap=200   # 200 caracteres de "repetição" para não perder o contexto entre pedaços
)

# --- FUNÇÃO NOVA: O MOTOR DE PDF ---


def processar_pdf_em_pedacos(caminho_pdf, titulo_base, doc_id, colecao):
    try:
        print(f"📖 Abrindo arquivo: {caminho_pdf}")
        doc = fitz.open(caminho_pdf)
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()

        # Divide o texto do PDF em pedaços menores (Chunks)
        pedacos = text_splitter.split_text(texto_completo)
        print(
            f"✂️ PDF fatiado em {len(pedacos)} pedaços. Iniciando vetorização...")

        for i, conteudo_pedaco in enumerate(pedacos):
            # Gera o embedding para cada pedaço individualmente
            res = client_openai.embeddings.create(
                input=[conteudo_pedaco],
                model="text-embedding-3-small"
            )
            vetor = res.data[0].embedding

            # Salva no Weaviate Cloud
            colecao.data.insert(
                properties={
                    "titulo": f"{titulo_base} - Parte {i+1}",
                    "conteudo": conteudo_pedaco,
                    "original_id": doc_id,
                    "fonte": caminho_pdf
                },
                vector=vetor
            )
        return True
    except Exception as e:
        print(f"❌ Erro ao processar PDF {caminho_pdf}: {e}")
        return False


# 2. Conexão Weaviate Cloud (Mesmas chaves que você já tem)
WCD_URL = "https://qqfm6jt5sfcpmiv1f3ciww.c0.us-west3.gcp.weaviate.cloud"
WCD_API_KEY = "aE56eG0rbXRyODF5am4wZF9UbGIyL0UxRHo2NFlMYnlEMm5ieDhHMnRXTUtFRkw0MFZxZGp5NmNvb3NrPV92MjAw"

client_weaviate = weaviate.connect_to_weaviate_cloud(
    cluster_url=WCD_URL,
    auth_credentials=Auth.api_key(WCD_API_KEY),
    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
)

# 3. Configuração Kafka
conf = {'bootstrap.servers': 'localhost:9092',
        'group.id': 'v40-pdf-engine', 'auto.offset.reset': 'earliest'}
consumer = Consumer(conf)
consumer.subscribe(['ia_projeto.CorporativoIA.dbo.DocumentosInstitucionais'])

print("\n🚀 Orquestrador de Documentos ATIVO! Aguardando Paths do SQL Server...\n")

try:
    colecao_documentos = client_weaviate.collections.get("Documento")
    print("\nEntrando no try\n")

    while True:
        msg = consumer.poll(1.0)

        # 1. Verifica se a mensagem existe
        if msg is None:
            continue

        # 2. Verifica erros do Kafka
        if msg.error():
            print(f"Erro Kafka: {msg.error()}")
            continue

        # 3. TRAVA ESSENCIAL: Verifica se o valor é nulo (evita o erro do decode)
        if msg.value() is None:
            continue
       
        # Agora é seguro fazer o decode
        raw_data = json.loads(msg.value().decode('utf-8'))
        payload_after = raw_data.get('payload', {}).get('after')

        if payload_after:
            titulo = payload_after.get('titulo')
            # Nome da coluna que você criou no SQL
            path_pdf = payload_after.get('caminho_arquivo')
            doc_id = payload_after.get('id')

            if path_pdf and os.path.exists(path_pdf):
                sucesso = processar_pdf_em_pedacos(
                    path_pdf, titulo, doc_id, colecao_documentos)
                if sucesso:
                    print(
                        f"✨ SUCESSO TOTAL: Documento '{titulo}' agora está no Weaviate!")
            else:
                print(
                    f"⚠️ Alerta: Registro recebido, mas o arquivo não existe em: {path_pdf}")

except KeyboardInterrupt:
    print("\n🛑 Encerrando...")
finally:
    consumer.close()
    client_weaviate.close()
