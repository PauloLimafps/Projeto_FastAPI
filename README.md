# 🚀 Projeto RAG CorporativoIA - Moodle & FastAPI

Bem-vindo ao repositório do **Orquestrador RAG (Retrieval-Augmented Generation)**. Este projeto estabelece uma arquitetura robusta e escalável para fornecer um assistente virtual inteligente alimentado por documentos institucionais, operando integrado a um plugin Moodle.

A solução utiliza captura de dados por eventos (CDC), mensageria Kafka, processamento semântico com OpenAI e armazenamento no Weaviate. A camada de aplicação é servida via **FastAPI** rodando em **containers Docker**.

---

## 🏗️ Arquitetura e Fluxo de Dados

O projeto é dividido em fluxos de Ingestão e Consulta:

1.  **Ingestão (Back-office)**:
    - **CDC**: O Debezium monitora o SQL Server.
    - **Kafka**: Propaga os eventos de novos documentos.
    - **Consumer (`main.py`)**: Processa PDFs, gera embeddings e alimenta o **Weaviate Cloud**.

2.  **Consulta (Front-office - Seta 1)**:
    - **Moodle**: Envia requisições assinadas via **JWT**.
    - **FastAPI (`orquestrador.py`)**: Valida o token, consulta o Weaviate e gera a resposta via GPT-4o.

---

## 🔒 Segurança (Auth JWT)

A comunicação entre Moodle e FastAPI é protegida por **JSON Web Tokens (HS256)**.
- Todas as requisições devem conter o header `Authorization: Bearer <token>`.
- O ID do usuário é extraído do payload do token validado (`sub`), impedindo a falsificação de identidade (User Spoofing).
- A chave secreta (`JWT_SECRET`) deve ser idêntica em ambos os serviços.

---

## 📋 Pré-requisitos

- **Docker e Docker Compose** (Obrigatório para a stack completa).
- **Python 3.10+** (Apenas para rodar scripts locais de ingestão/setup).
- **SQL Server** com CDC habilitado.
- Contas: OpenAI API e Weaviate Cloud.

---

## 🛠️ Passo a Passo de Implantação

### 1. Preparação da Infraestrutura Docker
O arquivo `docker-compose.yml` agora gerencia toda a stack, incluindo o Orquestrador.

```bash
# Inicie todos os serviços: Zookeeper, Kafka, Debezium e FastAPI
docker-compose up -d --build
```
> **Serviços Ativos**:
> - **Kafka**: `9092`
> - **Debezium**: `8083`
> - **FastAPI (Orquestrador)**: `8000`

### 2. Configuração do Ambiente (.env)
Crie o arquivo `.env` na raiz com as seguintes chaves mínimas:
```env
OPENAI_API_KEY=sk-...
JWT_SECRET=sua_chave_secreta_gerada
WCD_URL=...
WCD_API_KEY=...
SQLSERVER_HOST=host.docker.internal
```

### 3. Registro do Conector (SQL -> Kafka)
Instale as dependências locais no seu `.venv` e registre o conector:
```bash
pip install -r requirements.txt
python register_connector.py
```

### 4. Setup e Ingestão
Com a infraestrutura (Kafka/Weaviate) pronta, inicie a ingestão de documentos:
1. Garanta as coleções no Weaviate: `python setup_weaviate.py`
2. Inicie o processador de PDFs: `python main.py`

---

## 📂 Visão Geral dos Arquivos

- **`docker-compose.yml`**: Orquestração de containers (Kafka, Debezium, FastAPI).
- **`Dockerfile`**: Definição da imagem do Orquestrador FastAPI.
- **`auth.py`**: Lógica de validação de tokens JWT (HS256).
- **`orquestrador.py`**: API principal protegida por autenticação.
- **`main.py`**: Consumer de ingestão (Vetorização de PDFs).
- **`requirements.txt`**: Dependências Python (agora inclui `fastapi`, `uvicorn` e `python-jose`).

---

## 🔗 Integração no Moodle

Aponte o plugin Moodle para o endpoint `/chat` do container:
**URL**: `http://<IP_DO_SERVIDOR>:8000/chat`
**Método**: POST (Assinado com HS256)

O payload enviado deve seguir a estrutura rica de contexto (ID do usuário, Curso, Matrículas), mas a identificação final para logs e RAG será validada via JWT.

---
*💡 Este projeto foi atualizado para seguir padrões profissionais de segurança e containers.*
