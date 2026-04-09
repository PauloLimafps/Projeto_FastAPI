import os
from jose import jwt, JWTError
from fastapi import Request, HTTPException, Depends
from dotenv import load_dotenv

# Garante que as variáveis de ambiente sejam carregadas
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "moodle-openai-chat"

def validate_jwt(request: Request) -> dict:
    """
    Extrai e valida o token Bearer JWT do header Authorization.
    Retorna o payload decodificado se válido.
    """
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Erro interno: JWT_SECRET não configurada no servidor."
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Autenticação necessária. Formato esperado: 'Authorization: Bearer <token>'"
        )

    token = auth_header.split(" ")[1]

    try:
        # O decode já valida expiração (exp) e data de emissão (iat) automaticamente
        payload = jwt.decode(
            token, 
            JWT_SECRET, 
            algorithms=[JWT_ALGORITHM]
        )
        
        # Validar o emissor para garantir que o token veio do nosso Moodle
        if payload.get("iss") != JWT_ISSUER:
            raise HTTPException(status_code=401, detail="Origem do token inválida.")
            
        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token inválido ou expirado: {str(e)}"
        )
