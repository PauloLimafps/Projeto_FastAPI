import os                        # Acesso às variáveis de ambiente (OPENAI_API_KEY)
import weaviate                  # SDK do banco de dados vetorial Weaviate
from fastapi import FastAPI, HTTPException, Depends   # FastAPI: framework web; HTTPException: erros HTTP padronizados; Depends: injeção de dependência
from auth import validate_jwt                     # Middleware de segurança JWT
from pydantic import BaseModel, ConfigDict  # BaseModel: schema de request; ConfigDict: configuração Pydantic V2
from openai import OpenAI                    # SDK da OpenAI para geração de embeddings
from dotenv import load_dotenv               # Carrega variáveis do arquivo .env para o ambiente do processo
from weaviate.classes.init import Auth       # Auth: autenticação por chave de API no Weaviate Cloud
from contextlib import asynccontextmanager   # Para definir ciclo de vida assíncrono (startup/shutdown) da API
from nemoguardrails import LLMRails, RailsConfig # Para a camada de segurança do LLM

# Carrega as variáveis do arquivo .env para o ambiente do processo Python
load_dotenv()


# ─── BLOCO 1: Ciclo de Vida da Aplicação (Lifespan) ──────────────────────────

# Placeholder global — a conexão será criada no startup do FastAPI (dentro do lifespan)
client_weaviate = None
rails_app = None

# --- Gerenciador de Conexão (Resolve o ResourceWarning) ---
# @asynccontextmanager transforma a função coroutine em um gerenciador de contexto assíncrono
# O FastAPI usa o parâmetro `lifespan` para executar código de inicialização e encerramento
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Código ANTES do `yield` roda no STARTUP da aplicação (antes de aceitar requisições)
    # O que acontece quando o app inicia
    global client_weaviate
    # Cria a conexão autenticada com o Weaviate Cloud durante o startup gerenciado pelo FastAPI
    client_weaviate = weaviate.connect_to_weaviate_cloud(
        cluster_url=os.getenv("WCD_URL"),
        auth_credentials=Auth.api_key(os.getenv("WCD_API_KEY")),
        headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")},  # Permite vetorização interna do Weaviate
        skip_init_checks=True # Pula o check de saúde que estava travando o startup
    )
    
    # Inicializa o NeMo Guardrails
    global rails_app
    print("🛡️ Inicializando NeMo Guardrails...")
    rails_config = RailsConfig.from_path("./config")
    rails_app = LLMRails(rails_config)
    print("✅ NeMo Guardrails ativo!")
    
    yield  # A aplicação fica "viva" aqui, processando requisições HTTP normalmente

    # Código APÓS o `yield` roda no SHUTDOWN da aplicação (após parar de aceitar requisições)
    # O que acontece quando o app desliga
    if client_weaviate.is_connected():
        client_weaviate.close()  # Fecha a conexão TCP com o Weaviate para evitar ResourceWarning
        print("🔌 Conexão Weaviate fechada com segurança.")

# ─── BLOCO 2: Instâncias Globais da Aplicação ─────────────────────────────────

# Cria a instância da aplicação FastAPI com título descritivo e gerenciador de ciclo de vida
app = FastAPI(title="Orquestrador RAG - CorporativoIA", lifespan=lifespan)

# Cria o cliente da OpenAI — será verwendet para gerar embeddings
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ─── BLOCO 3: Schema de Dados do Request (Pydantic) ───────────────────────────

# --- Modelo de Dados (Resolve o Pydantic Deprecated) ---
# Define a estrutura e os tipos esperados no corpo JSON da requisição POST /chat
# O Pydantic valida automaticamente os campos e tipos ao receber a requisição
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='allow') # Novo padrão do Pydantic V2
    # ConfigDict substitui a antiga classe Meta/Config do Pydantic V1
    # `extra='allow'` permite que o Moodle envie campos adicionais sem gerar erro de validação
    
    # A pergunta enviada pelo aluno — campo obrigatório
    message: str
    # Dados do usuário logado no Moodle (id, nome, email, curso, etc.)
    user: dict
    # Contexto da página acessada no Moodle (nome do curso, seção, atividade, etc.)
    page_context: dict
    # Lista de matrículas/cursos em que o aluno está inscrito
    student_enrollments: list
    # Histórico da conversa enviado pelo Moodle (JSON array de user/message)
    history: list = []

# ─── BLOCO 4: Referência ao Weaviate Cloud — conexão criada no lifespan ────────
# (não há conexão aqui — ela é iniciada no startup do FastAPI acima)

# ─── BLOCO 5: Endpoint Principal — POST /chat ─────────────────────────────────

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, token_payload: dict = Depends(validate_jwt)):
    """
    Endpoint principal da API RAG. Recebe uma pergunta do Moodle,
    executa busca semântica nos documentos institucionais (Weaviate),
    monta um prompt com o contexto recuperado e retorna a resposta do GPT-4o.
    
    Fluxo: Pergunta → Busca Semântica → Contexto → System Prompt → GPT-4o → Resposta
    """
    try:
        # Extrai o ID do usuário diretamente do payload do token validado para maior segurança
        # Isso garante que o usuário logado é realmente quem diz ser no payload do JWT
        usuario_id = str(token_payload.get("sub", "desconhecido"))
        
        # ── Step 0: Reformulação de Query (Standalone Question) ────────────────
        # Se houver histórico, pedimos ao GPT para reescrever a pergunta de forma contextualizada
        # Isso garante que "qual a fórmula?" se transforme em "qual a fórmula de HA vinculada ao THC?"
        query_para_busca = request.message
        if request.history:
            try:
                # Constrói um resumo rápido do histórico para o GPT contextualizar
                resumo_conversa = "\n".join([f"{h.get('user', 'Usuário')}: {h.get('message', '')}" for h in request.history[-3:]]) # Últimas 3 interações
                
                reformulacao = client_openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um assistente técnico. Sua tarefa é reescrever a 'Pergunta Atual' do usuário em uma única frase de busca completa e independente, usando o 'Histórico da Conversa' para prover contexto. Retorne APENAS a frase reformulada, sem comentários."},
                        {"role": "user", "content": f"Histórico:\n{resumo_conversa}\n\nPergunta Atual: {request.message}\n\nPergunta Reformulada:"}
                    ],
                    max_tokens=60,
                    temperature=0
                )
                query_para_busca = reformulacao.choices[0].message.content.strip()
                print(f"🔍 Query Reformulada: {query_para_busca}")
            except Exception as re_err:
                print(f"⚠️ Erro ao reformular query: {re_err}")
                query_para_busca = request.message # Fallback para a original

        # ── Step 1: Busca Semântica no Weaviate ────────────────────────────────
        # Recupera a referência à coleção "Documento" no Weaviate Cloud
        colecao = client_weaviate.collections.get("Documento")

        # Gera o embedding da pergunta REFORMULADA via OpenAI (RAG de Precisão)
        res_embedding = client_openai.embeddings.create(
            input=[query_para_busca],
            model="text-embedding-3-small"
        )
        vetor_query = res_embedding.data[0].embedding

        # near_vector: busca os documentos cujos vetores são mais próximos ao vetor da query
        # Não depende de vetorizador interno do Weaviate — usa o vetor gerado externamente
        response = colecao.query.near_vector(
            near_vector=vetor_query,  # Vetor semântico gerado pela OpenAI
            limit=3                   # Retorna os 3 chunks com maior similaridade semântica
        )
        
        # ── Step 2: Montagem do Contexto RAG ──────────────────────────────────
        # Concatena o conteúdo textual dos chunks retornados, separados por linha dupla
        # Este contexto será injetado no system prompt para fundamentar a resposta do LLM
        contexto = "\n\n".join([obj.properties["conteudo"] for obj in response.objects])
        
        # ── Step 4: Geração de Resposta via NeMo Guardrails ────────────────────────────
        # 1. Converte o histórico do formato Moodle (user/message) para o formato NeMo (role/content)
        mensagens_nemo = []
        for h in request.history:
            msg = h.get("message", "").strip()
            if not msg:
                continue # Pula mensagens vazias
            
            role = "user"
            # O Moodle envia o nome do usuário/assistente. 
            if h.get('user') != request.user.get('fullname'):
                role = "assistant"
            mensagens_nemo.append({"role": role, "content": msg})

        # 2. Prepara a pergunta atual
        # Injetamos o contexto de forma clara
        context_block = f"CONTEXTO DO MANUAL:\n{contexto}\n\n"
        current_msg = f"{context_block}Pergunta: {request.message}"

        # Adiciona a pergunta atual ao final do histórico
        mensagens_nemo.append({"role": "user", "content": current_msg})

        # Chama o NeMo Guardrails com o histórico COMPLETO
        res_guardrails = await rails_app.generate_async(messages=mensagens_nemo)
        
        # ── Step 5: Retorno da Resposta JSON ──────────────────────────────────
        # Extração Robusta (pode vir como objeto ou dict dependendo da situação do Rail)
        answer_text = ""
        if hasattr(res_guardrails, 'content'):
            answer_text = res_guardrails.content
        elif isinstance(res_guardrails, dict):
            answer_text = res_guardrails.get('content', '')
        else:
            answer_text = str(res_guardrails)

        return {
            "answer": answer_text,
            "id": f"fastapi_{usuario_id}"
        }

    except Exception as e:
        # Loga o erro internamente e retorna HTTP 500 com detalhes para facilitar o debug
        print(f"❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── BLOCO 6: Ponto de Entrada para Execução Direta ──────────────────────────

if __name__ == "__main__":
    import uvicorn
    # Inicia o servidor ASGI Uvicorn escutando em todas as interfaces de rede (0.0.0.0)
    # na porta 8000 — acessível tanto localmente quanto via rede interna/externa
    uvicorn.run(app, host="0.0.0.0", port=8000)