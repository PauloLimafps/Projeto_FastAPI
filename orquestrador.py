import os                        # Acesso às variáveis de ambiente (OPENAI_API_KEY)
import weaviate                  # SDK do banco de dados vetorial Weaviate
from fastapi import FastAPI, HTTPException   # FastAPI: framework web; HTTPException: erros HTTP padronizados
from pydantic import BaseModel, ConfigDict  # BaseModel: schema de request; ConfigDict: configuração Pydantic V2
from openai import OpenAI                    # SDK da OpenAI para geração de respostas via GPT-4o
from dotenv import load_dotenv               # Carrega variáveis do arquivo .env para o ambiente do processo
from weaviate.classes.init import Auth       # Auth: autenticação por chave de API no Weaviate Cloud
from contextlib import asynccontextmanager   # Para definir ciclo de vida assíncrono (startup/shutdown) da API

# Carrega as variáveis do arquivo .env para o ambiente do processo Python
load_dotenv()


# ─── BLOCO 1: Ciclo de Vida da Aplicação (Lifespan) ──────────────────────────

# Placeholder global — a conexão será criada no startup do FastAPI (dentro do lifespan)
client_weaviate = None

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
        headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}  # Permite vetorização interna do Weaviate
    )
    yield  # A aplicação fica "viva" aqui, processando requisições HTTP normalmente

    # Código APÓS o `yield` roda no SHUTDOWN da aplicação (após parar de aceitar requisições)
    # O que acontece quando o app desliga
    if client_weaviate.is_connected():
        client_weaviate.close()  # Fecha a conexão TCP com o Weaviate para evitar ResourceWarning
        print("🔌 Conexão Weaviate fechada com segurança.")

# ─── BLOCO 2: Instâncias Globais da Aplicação ─────────────────────────────────

# Cria a instância da aplicação FastAPI com título descritivo e gerenciador de ciclo de vida
app = FastAPI(title="Orquestrador RAG - CorporativoIA", lifespan=lifespan)

# Cria o cliente da OpenAI — será verwendet para gerar a resposta final via GPT-4o
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

# ─── BLOCO 4: Referência ao Weaviate Cloud — conexão criada no lifespan ────────
# (não há conexão aqui — ela é iniciada no startup do FastAPI acima)

# ─── BLOCO 5: Endpoint Principal — POST /chat ─────────────────────────────────

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint principal da API RAG. Recebe uma pergunta do Moodle,
    executa busca semântica nos documentos institucionais (Weaviate),
    monta um prompt com o contexto recuperado e retorna a resposta do GPT-4o.
    
    Fluxo: Pergunta → Busca Semântica → Contexto → System Prompt → GPT-4o → Resposta
    """
    try:
        # Extrai o ID do usuário para compor o identificador da resposta
        # Usa 'desconhecido' como fallback se o campo 'id' não estiver presente no dict
        usuario_id = str(request.user.get('id', 'desconhecido'))
        
        # ── Step 1: Busca Semântica no Weaviate ────────────────────────────────
        # Recupera a referência à coleção "Documento" no Weaviate Cloud
        colecao = client_weaviate.collections.get("Documento")

        # Gera o embedding da pergunta via OpenAI (igual ao main.py faz nos PDFs)
        # Necessário pois a coleção usa vectorizer_config=None (vetores externos)
        res_embedding = client_openai.embeddings.create(
            input=[request.message],
            model="text-embedding-3-small"  # Mesmo modelo usado na ingestão (main.py)
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
        
        # ── Step 3: Construção do System Prompt ───────────────────────────────
        # O system prompt define o persona, regras de comportamento e injeta o contexto RAG
        # As regras de formatação evitam LaTeX (não renderizável no Moodle/PHP)
        system_prompt = (
                            "Você é o Assistente Acadêmico do curso de Medicina. "
                            "Use o contexto fornecido para responder às dúvidas dos alunos de forma detalhada e explicativa. "
                            "\n\nREGRA CRÍTICA DE FORMATAÇÃO: "
                            "1. NÃO use símbolos LaTeX como \\frac, \\text ou \\times. "
                            "2. Escreva fórmulas matemáticas usando texto simples e legível (ex: (Lab * 6 + THC * 4) / 10). "
                            "3. Use negrito para destacar termos importantes. "
                            "4. Apresente passos de cálculo em listas numeradas. "
                            f"\n\nContexto: {contexto}"  # Injeta os chunks recuperados do Weaviate
                            )
        
        # ── Step 4: Geração de Resposta via GPT-4o ────────────────────────────
        # Chama a API de chat completions da OpenAI com o contexto RAG no system prompt
        completion = client_openai.chat.completions.create(
            model="gpt-4o",  # Modelo principal — mais capaz para contexto médico e acadêmico
            messages=[
                {"role": "system", "content": system_prompt},  # Define persona, regras e contexto RAG
                {"role": "user", "content": request.message}   # A pergunta real do aluno
            ]
        )

        # ── Step 5: Retorno da Resposta JSON ──────────────────────────────────
        return {
            "answer": completion.choices[0].message.content,  # Resposta gerada pelo GPT-4o
            "id": f"fastapi_{usuario_id}"                      # Identificador único da interação
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