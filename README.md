# 🚀 Projeto RAG CorporativoIA - Moodle & FastAPI

Bem-vindo ao repositório do **Orquestrador RAG (Retrieval-Augmented Generation)**. Este projeto estabelece uma arquitetura robusta e escalável para fornecer um assistente virtual inteligente alimentado por documentos institucionais, operando integrado a um plugin Moodle.

A solução utiliza captura de dados por eventos (CDC) diretamente de um banco SQL Server, passando por uma mensageria Kafka, processamento e vetorização com OpenAI, e armazenamento no Weaviate. A interface principal é servida através de uma API FastAPI de alta performance.

---

## 🏗️ Arquitetura e Fluxo de Dados

O projeto é dividido em processos assíncronos e síncronos:

1. **CDC (Change Data Capture)**: O **Debezium** monitora a tabela `DocumentosInstitucionais` no SQL Server. Quando um novo documento é adicionado, um evento é gerado.
2. **Mensageria**: O evento é propagado através do **Apache Kafka**.
3. **Ingestão e Vetorização (`main.py`)**: Um consumer Python escuta o Kafka, captura os metadados do documento (incluindo o caminho do arquivo), lê e "fatia" (chunking) o PDF usando `PyMuPDF`, gera *embeddings* usando a API da OpenAI e salva no banco de dados vetorial **Weaviate**.
4. **Chatbot / Orquestrador (`orquestrador.py`)**: A aplicação Moodle faz chamadas para um endpoint **FastAPI**. O FastAPI faz a busca semântica no Weaviate e utiliza os documentos encontrados como contexto para o LLM da OpenAI gerar respostas precisas aos alunos, sem alucinações.

---

## 📋 Pré-requisitos

Antes de iniciar a implantação, certifique-se de ter os seguintes recursos instalados e configurados na sua máquina ou servidor:

- **Docker e Docker Compose** (para serviços de infraestrutura: Kafka, Zookeeper, Debezium e local Weaviate).
- **Python 3.10+** (para rodar os serviços locais de ingestão e a API).
- **SQL Server** rodando com CDC (Change Data Capture) habilitado.
- Contas e chaves de acesso:
  - `OPENAI_API_KEY` (Chave de API OpenAI ativa)
  - Credenciais do Weaviate Cloud (WCD), se estiver usando.

---

## 🛠️ Passo a Passo de Implantação

Siga os passos abaixo, na ordem descrita, para montar o ambiente por completo.

### 1. Preparação da Infraestrutura Docker

O arquivo `docker-compose.yml` provê a stack base de mensageria e o node de configuração.

```bash
# Inicie todos os containers em segundo plano
docker-compose up -d
```
> **Nota:** Isso irá iniciar o Kafka (`9092`), Zookeeper (`2181`), Debezium (`8083`) e um serviço local do Weaviate (`8080`).

### 2. Configuração do Ambiente Python

Recomenda-se criar um ambiente virtual isolado para evitar conflitos de versão:

```bash
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente (Windows)
.venv\Scripts\activate
# Ativar ambiente (Linux/Mac)
# source .venv/bin/activate

# Instalar as bibliotecas necessárias
pip install -r requirements.txt
```

Crie o seu arquivo `.env` na raiz do projeto contendo as chaves necessárias (e.g.: `OPENAI_API_KEY=sk-...`).

### 3. Registro do Conector Debezium (SQL Server -> Kafka)

Esse script instrui o Debezium a escutar seu banco de dados.

```bash
python register_connector.py
```
*Se houver sucesso, você verá "✅ Conector registrado!". O serviço começará a observar o banco `CorporativoIA` via Kafka.*

### 4. Setup do Banco Vetorial (Weaviate)

Antes de gravar qualquer dado, você precisa garantir que as coleções existem no Weaviate:

```bash
python setup_weaviate.py
```
*Espera-se a mensagem "✅ Coleção 'Documento' criada com sucesso no Weaviate (v4)!".*

### 5. Iniciar o Consumer de Ingestão de PDF

Esta é a rotina em back-ground responsável por escutar o Kafka e processar os PDFs inseridos no SQL. Deixe rodando num terminal reservado.

```bash
python main.py
```
*O sistema informará 🚀 Orquestrador de Documentos ATIVO! e iniciará o "handshake" processando os PDFs da fila para o banco logico do Weaviate.*

### 6. Subir a API do Assistente (FastAPI)

Este é o endpoint `/chat` que o Moodle vai consumir. Em outro terminal (com o `.venv` ativado):

```bash
python orquestrador.py
```
*O serviço iniciará via Uvicorn na porta `8000`. Teste o acesso local abrindo `http://localhost:8000/docs` no navegador.*

---

## 📂 Visão Geral dos Arquivos

- **`docker-compose.yml`**: Configuração central do Docker com Kafka, Zookeeper, Debezium e local Weaviate.
- **`register_connector.py`**: Interage com a REST API do Debezium (`http://localhost:8083`) para criar o payload apontando pro seu banco de dados `CorporativoIA`.
- **`setup_weaviate.py`**: Contém o schema descritivo dos índices a serem criados no banco vetorial.
- **`main.py`**: O Consumer Kafka propriamente dito. Ele processa mensagens do banco, abre e processa (fatia) o PDF pelo arquivo referenciado, constrói embeddings usando a OpenAI, e alimenta o Weaviate.
- **`orquestrador.py`**: O app web (FastAPI). Recebe chamadas JSON, faz Retrieval local no Weaviate, constrói o Prompt engessado para contexto de docência, bate na LLM, e retorna a string pro site (Moodle).
- **`requirements.txt`**: Principais libs: `weaviate-client`, `confluent-kafka`, `openai`, `fastapi`, `pymupdf` (fitz).

---

## 🔗 Integração no Moodle

Com o serviço do **FastAPI (`orquestrador.py`)** rodando na sua porta de acesso externo (`8000`), aponte o seu bloco Moodle (`openai_chat` ou equivalente) para enviar via Webhook/Curl para `http://<SEU-IP>:8000/chat`. 

O payload esperado pela API segue o dicionário pydantic de `ChatRequest`, englobando os atributos fundamentais pro Tracking como id de usuário.

---
*💡 Este documento fornece uma visão panorâmica e os comandos chave do ciclo de vida da aplicação.*
