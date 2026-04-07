import os
import weaviate
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from pydantic import BaseModel, Extra

load_dotenv()

app = FastAPI(title="Orquestrador RAG - CorporativoIA")
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Conexão com o seu Weaviate Cloud (O banco que acabamos de alimentar)
WCD_URL = "https://qqfm6jt5sfcpmiv1f3ciww.c0.us-west3.gcp.weaviate.cloud"
WCD_API_KEY = "aE56eG0rbXRyODF5am4wZF9UbGIyL0UxRHo2NFlMYnlEMm5ieDhHMnRXTUtFRkw0MFZxZGp5NmNvb3NrPV92MjAw"

client_weaviate = weaviate.connect_to_weaviate_cloud(
    cluster_url=WCD_URL,
    auth_credentials=Auth.api_key(WCD_API_KEY),
    headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
)

# Modelo de dados para o Request do Moodle (Step 1)
class ChatRequest(BaseModel):
    message: str  # O PHP envia como 'message', não como 'pergunta'
    user: dict    # Dados do aluno (id, email, etc)
    page_context: dict # Onde o aluno está
    student_enrollments: list # Cursos dele

    class Config:
        extra = Extra.allow
        
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # STEP 3: Busca Semântica no Weaviate
        colecao = client_weaviate.collections.get("Documento")
        
        # Buscamos os 3 pedaços (chunks) mais relevantes do PDF
        response = colecao.query.near_text(
            query=request.message,
            limit=3
        )
        
        # STEP 4: Montagem do Contexto Relevante
        contexto = "\n\n".join([obj.properties["conteudo"] for obj in response.objects])
        
        if not contexto:
            contexto = "Nenhuma informação institucional encontrada para esta pergunta."

        # STEP 5 & 7: Prompt + Contexto + Geração de Resposta (OpenAI)
        system_prompt = f"""
        Você é o Assistente de IA da Instituição. 
        Use APENAS o contexto abaixo para responder ao aluno. 
        Se não souber, diga que não encontrou a informação no manual.
        
        CONTEXTO:
        {contexto}
        """

        completion = client_openai.chat.completions.create(
            model="gpt-4.1-mini", # Ou o modelo da sua preferência
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message}
            ]
        )

        # STEP 10: Resposta Final (JSON Response)
        return {
            "resposta": completion.choices[0].message.content,
            "fontes": [obj.properties["titulo"] for obj in response.objects]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)