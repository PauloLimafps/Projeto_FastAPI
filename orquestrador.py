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
import cohere                                   # Para o Re-ranker de alta precisão

# Carrega as variáveis do arquivo .env para o ambiente do processo Python
load_dotenv()


# ─── BLOCO 1: Ciclo de Vida da Aplicação (Lifespan) ──────────────────────────

# Placeholder global — a conexão será criada no startup do FastAPI (dentro do lifespan)
client_weaviate = None
rails_app = None
client_cohere = None

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
    
    global rails_app
    print("🛡️ Inicializando NeMo Guardrails...")
    rails_config = RailsConfig.from_path("./config")
    rails_app = LLMRails(rails_config)
    print("✅ NeMo Guardrails ativo!")

    # Inicializa o Cohere (Re-ranker)
    global client_cohere
    client_cohere = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
    print("🎯 Re-ranker Cohere pronto!")
    
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
        # Instrução reforçada: Obriga a IA a extrair Período e Matriz para a busca
        query_para_busca = request.message
        if request.history:
            try:
                resumo_conversa = "\n".join([f"{h.get('user', 'Usuário')}: {h.get('message', '')}" for h in request.history[-3:]])
                
                reformulacao = client_openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": (
                            "Você é um especialista em extração de contexto acadêmico. "
                            "Sua tarefa é reescrever a 'Pergunta Atual' em uma busca completa para um banco de dados técnico. "
                            "DIRETRIZ CRÍTICA: Se o 'Histórico' mencionar um Período (ex: 5º período) ou Matriz (ex: 2023.1), "
                            "você deve OBRIGATORIAMENTE incluir esses termos na sua busca reformulada. "
                            "Retorne APENAS a frase de busca, sem explicações."
                        )},
                        {"role": "user", "content": f"Histórico:\n{resumo_conversa}\n\nPergunta Atual: {request.message}"}
                    ],
                    max_tokens=60,
                    temperature=0
                )
                query_para_busca = reformulacao.choices[0].message.content.strip()
                print(f"🔍 Query Contextualizada: {query_para_busca}")
            except Exception as re_err:
                print(f"⚠️ Erro ao reformular query: {re_err}")
                query_para_busca = request.message

        # ── Step 1: Busca Híbrida no Weaviate ──────────────────────────────────
        # Recupera a referência à coleção "Documento"
        colecao = client_weaviate.collections.get("Documento")

        # Gera o embedding da query reformulada (RAG de Precisão)
        # Necessário para alimentar a parte vetorial da busca híbrida
        res_embedding = client_openai.embeddings.create(
            input=[query_para_busca],
            model="text-embedding-3-small"
        )
        vetor_query = res_embedding.data[0].embedding

        # Busca Híbrida: Combina Semântica (Vetor) + Lexical (Palavra-chave)
        # alpha=0.5: equilibra 50% vetor e 50% keyword para siglas técnicas
        res_weaviate = colecao.query.hybrid(
            query=query_para_busca,   # Texto para busca por palavra-chave
            vector=vetor_query,       # Vetor para busca semântica
            limit=10,                 # Pegamos 10 candidatos para o re-ranker avaliar
            alpha=0.5
        )

        # ── Step 1.5: Re-ranking via Cohere API ───────────────────────────────
        # O re-ranker analisa os 10 candidatos e escolhe os 3 melhores reais
        candidatos = [obj.properties["conteudo"] for obj in res_weaviate.objects]
        contexto_final = ""

        if candidatos:
            rerank_res = client_cohere.rerank(
                model="rerank-multilingual-v3.0",
                query=query_para_busca,
                documents=candidatos,
                top_n=3
            )
            
            # Extrai os textos reordenados (Top 3)
            trechos_selecionados = []
            for result in rerank_res.results:
                trechos_selecionados.append(candidatos[result.index])
            
            contexto_final = "\n\n".join(trechos_selecionados)
        
        # ── Step 2: Montagem do Contexto RAG ──────────────────────────────────
        # Este contexto será injetado no system prompt para fundamentar a resposta do LLM
        contexto = contexto_final
        
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