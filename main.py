import os           # Acesso a variáveis de ambiente e ao sistema de arquivos
# Deserialização das mensagens Kafka (formato JSON/Debezium CDC)
import json
import sys          # Usado para eventual encerramento forçado do processo
import weaviate     # SDK do banco de dados vetorial Weaviate
import fitz         # PyMuPDF: biblioteca para leitura e extração de texto de arquivos PDF
# Cliente Kafka para consumo de mensagens
from confluent_kafka import Consumer
# SDK da OpenAI para geração de embeddings
from openai import OpenAI
# Carrega variáveis do arquivo .env
from dotenv import load_dotenv
# Auth: autenticação; Timeout: controle de tempo de espera
from weaviate.classes.init import Auth, Timeout
# Divide textos longos em chunks menores
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ─── BLOCO 1: Inicialização do Ambiente ────────────────────────────────────────

# Carrega as variáveis definidas no arquivo .env para o ambiente do processo
# (ex: OPENAI_API_KEY)
# 1. Carregar ambiente e fatiador
load_dotenv()

# Cria o cliente da OpenAI usando a chave de API carregada do .env
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── BLOCO 2: Configuração do Fatiador de Texto (Text Splitter) ───────────────

# O "Fatiador" garante que o Moodle receba respostas precisas e não textos gigantes
# RecursiveCharacterTextSplitter divide textos grandes em pedaços (chunks) respeitando
# separadores naturais do texto (parágrafos, frases) para preservar coerência
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,    # Cada pedaço terá ~1000 caracteres
    chunk_overlap=200   # 200 caracteres de "repetição" para não perder o contexto entre pedaços
)

# --- FUNÇÃO NOVA: O MOTOR DE PDF ---

# ─── BLOCO 3: Função Principal de Processamento de PDFs ──────────────────────


def processar_pdf_em_pedacos(caminho_pdf, titulo_base, doc_id, colecao):
    """
    Abre um arquivo PDF, extrai seu texto completo, divide em chunks semânticos,
    gera embeddings via OpenAI para cada chunk e os persiste no Weaviate Cloud.

    Parâmetros:
        caminho_pdf (str): Caminho absoluto do arquivo PDF no sistema de arquivos.
        titulo_base (str): Título do documento institucional vindo do SQL Server.
        doc_id (int):      ID primário do documento no SQL Server (para rastreabilidade).
        colecao:           Objeto de coleção Weaviate onde os chunks serão inseridos.

    Retorna:
        bool: True se o processamento foi concluído com sucesso, False caso contrário.
    """
    try:
        print(f"📖 Abrindo arquivo: {caminho_pdf}")

        # Abre o arquivo PDF usando PyMuPDF (fitz)
        doc = fitz.open(caminho_pdf)

        # Itera por todas as páginas e concatena o texto extraído de cada uma
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()  # Extrai o texto bruto da página como string

        # Divide o texto total em pedaços menores (chunks) usando o fatiador configurado
        pedacos = text_splitter.split_text(texto_completo)
        print(
            f"✂️ PDF fatiado em {len(pedacos)} pedaços. Iniciando vetorização...")

        # Itera por cada chunk para gerar embedding e persistir individualmente no Weaviate
        for i, conteudo_pedaco in enumerate(pedacos):
            # Gera o embedding para cada pedaço individualmente
            # Chama a API da OpenAI para transformar o texto em vetor numérico (embedding)
            # O modelo "text-embedding-3-small" é eficiente e de baixo custo
            res = client_openai.embeddings.create(
                input=[conteudo_pedaco],
                model="text-embedding-3-small"
            )
            # Extrai o vetor numérico da resposta (lista de floats representando o espaço semântico)
            vetor = res.data[0].embedding

            # Salva no Weaviate Cloud
            # `properties` são os metadados textuais; `vector` é o embedding gerado externamente
            colecao.data.insert(
                properties={
                    # Identificador da parte do documento
                    "titulo": f"{titulo_base} - Parte {i+1}",
                    "conteudo": conteudo_pedaco,                  # Conteúdo textual bruto do chunk
                    "original_id": doc_id,                        # Rastreabilidade com o SQL Server
                    "fonte": caminho_pdf                          # Caminho original do arquivo PDF
                },
                vector=vetor  # Vetor semântico gerado pela OpenAI para busca por similaridade
            )
        return True  # Indica que o processamento foi concluído com sucesso

    except Exception as e:
        # Captura qualquer erro (falha ao abrir PDF, erro na API OpenAI, erro no insert Weaviate)
        print(f"❌ Erro ao processar PDF {caminho_pdf}: {e}")
        return False  # Indica falha — o chamador pode logar ou tentar novamente


# ─── BLOCO 4: Conexão com o Weaviate Cloud ────────────────────────────────────

# 2. Conexão Weaviate Cloud (Mesmas chaves que você já tem)
# URL do cluster Weaviate hospedado na nuvem (GCP us-west3)
WCD_URL = os.getenv("WCD_URL")  # Lido do .env — não expor no código-fonte

# Chave de API do Weaviate Cloud — lida do .env (segurança: nunca hardcode em código)
WCD_API_KEY = os.getenv("WCD_API_KEY")

# Cria a conexão autenticada com o cluster Weaviate Cloud
# O header X-OpenAI-Api-Key permite que o Weaviate use a OpenAI para vetorização interna se necessário
client_weaviate = weaviate.connect_to_weaviate_cloud(
    cluster_url=WCD_URL,
    auth_credentials=Auth.api_key(WCD_API_KEY),
    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
)

# ─── BLOCO 5: Configuração do Consumidor Kafka ────────────────────────────────

# 3. Configuração Kafka
# Dicionário de configuração do consumidor Kafka
conf = {'bootstrap.servers': 'localhost:9092',  # Endereço do broker Kafka rodando localmente via Docker
        # ID do grupo de consumidores (controla onde o offset é salvo)
        'group.id': 'v40-pdf-engine',
        # Se não há offset salvo, lê desde o início do tópico
        'auto.offset.reset': 'earliest'}

# Instancia o consumidor com as configurações acima
consumer = Consumer(conf)

# Inscreve o consumidor no tópico gerado automaticamente pelo Debezium
# Padrão do nome do tópico: {topic.prefix}.{database}.{schema}.{table}
consumer.subscribe(['ia_projeto.CHAT_RAG.dbo.arquivos_rag'])

print("\n🚀 Orquestrador de Documentos ATIVO! Aguardando Paths do SQL Server...\n")

# ─── BLOCO 6: Loop Principal de Consumo e Processamento ──────────────────────

try:
    # Obtém a referência à coleção "Documento" já existente no Weaviate Cloud
    colecao_documentos = client_weaviate.collections.get("Documento")
    print("\nEntrando no try\n")

    # Loop infinito: fica aguardando e processando novas mensagens do Kafka indefinidamente
    while True:
        # Tenta buscar uma mensagem do Kafka com timeout de 1 segundo (non-blocking)
        msg = consumer.poll(1.0)

        # 1. Verifica se a mensagem existe
        # None = nenhuma mensagem disponível no momento — continua aguardando
        if msg is None:
            continue

        # 2. Verifica erros do Kafka
        # Pode ocorrer em rebalanceamento de partições, desconexão ou outros problemas de broker
        if msg.error():
            print(f"Erro Kafka: {msg.error()}")
            continue

        # 3. TRAVA ESSENCIAL: Verifica se o valor é nulo (evita o erro do decode)
        # Mensagens de controle/tombstone do Debezium (eventos DELETE) podem ter value() == None
        if msg.value() is None:
            continue

        # Agora é seguro fazer o decode — converte bytes UTF-8 para dict Python
        raw_data = json.loads(msg.value().decode('utf-8'))

        # Extrai o payload "after" — representa o estado do registro APÓS a operação no SQL Server
        # Estrutura do envelope Debezium: {"payload": {"before": {...}, "after": {...}, "op": "..."}}
        payload_after = raw_data.get('payload', {}).get('after')

        if payload_after:
            # Extrai os campos relevantes do evento CDC (Change Data Capture)
            titulo = payload_after.get('titulo')
            # Nome da coluna que você criou no SQL
            # Caminho físico do arquivo PDF no servidor
            path_pdf = payload_after.get('caminho_arquivo')
            # Chave primária do registro no SQL Server
            doc_id = payload_after.get('id')

            # Verifica se o caminho foi fornecido E se o arquivo realmente existe no sistema de arquivos
            if path_pdf and os.path.exists(path_pdf):
                # Chama a função principal de processamento PDF → Embedding → Weaviate
                sucesso = processar_pdf_em_pedacos(
                    path_pdf, titulo, doc_id, colecao_documentos)
                if sucesso:
                    print(
                        f"✨ SUCESSO TOTAL: Documento '{titulo}' agora está no Weaviate!")
            else:
                # Arquivo referenciado no SQL Server não encontrado no filesystem
                # Pode indicar: caminho errado, arquivo movido/deletado, ou permissão de acesso
                print(
                    f"⚠️ Alerta: Registro recebido, mas o arquivo não existe em: {path_pdf}")

except KeyboardInterrupt:
    # Usuário pressionou Ctrl+C — encerramento gracioso e esperado
    print("\n🛑 Encerrando...")
finally:
    # Bloco finally garante liberação de recursos independentemente de como o loop terminou
    # Fecha a conexão com o Kafka (comita offsets pendentes e libera o grupo)
    consumer.close()
    # Fecha a conexão TCP com o Weaviate Cloud (evita ResourceWarning)
    client_weaviate.close()
