import os
import weaviate
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict # Mudança aqui
from openai import OpenAI
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from contextlib import asynccontextmanager # Para fechar a conexão corretamente

load_dotenv()


# --- Gerenciador de Conexão (Resolve o ResourceWarning) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # O que acontece quando o app inicia
    yield
    # O que acontece quando o app desliga
    if client_weaviate.is_connected():
        client_weaviate.close()
        print("🔌 Conexão Weaviate fechada com segurança.")

app = FastAPI(title="Orquestrador RAG - CorporativoIA", lifespan=lifespan)
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --- Modelo de Dados (Resolve o Pydantic Deprecated) ---
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='allow') # Novo padrão do Pydantic V2
    
    message: str
    user: dict
    page_context: dict
    student_enrollments: list

# --- Conexão Weaviate ---
WCD_URL = "https://qqfm6jt5sfcpmiv1f3ciww.c0.us-west3.gcp.weaviate.cloud"
WCD_API_KEY = "aE56eG0rbXRyODF5am4wZF9UbGIyL0UxRHo2NFlMYnlEMm5ieDhHMnRXTUtFRkw0MFZxZGp5NmNvb3NrPV92MjAw"

client_weaviate = weaviate.connect_to_weaviate_cloud(
    cluster_url=WCD_URL,
    auth_credentials=Auth.api_key(WCD_API_KEY),
    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
)

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        usuario_id = str(request.user.get('id', 'desconhecido'))
        
        colecao = client_weaviate.collections.get("Documento")
        response = colecao.query.near_text(
            query=request.message,
            limit=3
        )
        
        contexto = "\n\n".join([obj.properties["conteudo"] for obj in response.objects])
        
        system_prompt = (
                            "Você é o Assistente Acadêmico do curso de Medicina. "
                            "Use o contexto fornecido para responder às dúvidas dos alunos de forma detalhada e explicativa. "
                            "\n\nREGRA CRÍTICA DE FORMATAÇÃO: "
                            "1. NÃO use símbolos LaTeX como \\frac, \\text ou \\times. "
                            "2. Escreva fórmulas matemáticas usando texto simples e legível (ex: (Lab * 6 + THC * 4) / 10). "
                            "3. Use negrito para destacar termos importantes. "
                            "4. Apresente passos de cálculo em listas numeradas. "
                            f"\n\nContexto: {contexto}"
                            )
        
        completion = client_openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message}
            ]
        )

        return {
            "answer": completion.choices[0].message.content,
            "id": f"fastapi_{usuario_id}"
        }

    except Exception as e:
        print(f"❌ Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)