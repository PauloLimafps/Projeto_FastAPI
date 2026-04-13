# 🚀 Orquestrador RAG - Ecossistema Moodle & FastAPI

Esta plataforma estabelece uma arquitetura robusta para a implementação de assistentes virtuais inteligentes baseados em documentos institucionais. A solução integra um fluxo de Ingestão de Dados via CDC (Change Data Capture) com uma API de consulta de alto desempenho, operando de forma transparente com o Moodle.

A estrutura foi desenvolvida para garantir escalabilidade e segurança, utilizando tecnologias como Kafka para mensageria, Weaviate para armazenamento vetorial e Docker para orquestração de serviços.

---

## 🏗️ Arquitetura e Fluxo de Dados

O ecossistema é dividido em dois pilares fundamentais:

### 1. Fluxo de Ingestão (Data Pipeline)
Responsável por transformar informação bruta em conhecimento semântico:
- **Camada de Dados**: Monitoramento direto do banco SQL Server através de CDC.
- **Captura e Mensageria**: Utilização de Debezium e Kafka para a propagação de eventos de novos documentos em tempo real.
- **Motor de Ingestão (`pdf_engine_rag`)**: 
  - Serviço autônomo encarregado do processamento de PDFs e geração de embeddings.
  - **Diferencial de Resiliência**: Implementação de lógica para compatibilidade de caminhos entre sistemas Windows e Linux, garantindo o acesso aos arquivos físicos independente do formato da referência capturada no banco de dados.

### 2. Fluxo de Consulta (API Orchestrator)
Camada de inteligência que serve às requisições do front-end:
- **Gateway (Traefik)**: Gerenciamento inteligente de tráfego com aplicação de *Rate Limiting* e proxy reverso.
- **Orquestrador (`fastapi_rag`)**: 
  - Validação de tokens JWT para segurança da API.
  - Execução de buscas híbridas no Weaviate Cloud.
  - Geração de respostas contextualizadas com suporte ao modelo GPT-4o.

---

## 🔒 Camada de Segurança
A proteção dos dados e dos endpoints é garantida através de protocolos modernos:
- **Autenticação JWT (HS256)**: Toda comunicação entre serviços exige assinatura digital, eliminando o risco de acessos não autorizados.
- **Identidade Protegida**: Extração segura de metadados (`sub`), assegurando a integridade da identidade do usuário.
- **Controle de Tráfego**: Proteção nativa no Gateway para mitigar abusos e garantir a estabilidade do orquestrador.

---

## 📋 Requisitos para Operação
- **Infraestrutura**: Docker e Docker Compose instalados.
- **Dados**: SQL Server com recurso de CDC habilitado.
- **Conectividade**: Acesso às APIs da OpenAI e instância no Weaviate Cloud.

---

## 🛠️ Procedimentos de Implantação

### 1. Variáveis de Ambiente
Configuração do arquivo `.env` com as credenciais de banco, URLs de cluster e chaves de API necessárias para a integração.

### 2. Inicialização da Stack
```bash
# Ativação de todos os serviços (Kafka, Debezium, FastAPI, PDF Engine, Traefik)
docker-compose up -d --build
```

### 3. Registro e Setup
- Registro do conector SQL via script `register_connector.py`.
- Preparação de coleções no Weaviate através do `setup_weaviate.py`.

---

## 📂 Componentes do Sistema (Containers)
- **`traefik_gateway`**: Ponto único de entrada e controle.
- **`fastapi_rag`**: Núcleo da API e lógica orquestradora.
- **`pdf_engine_rag`**: Processamento de background para documentos.
- **`kafka/zookeeper` & `debezium`**: Infraestrutura de dados e eventos.

---

## 🧩 Módulo de Interface (Plugin Moodle)
Para a completa operação deste ecossistema, o Moodle deve possuir o plugin conector instalado e configurado:
- **Repositório do Plugin**: [LMS Plugin (Moodle)](https://github.com/PauloLimafps/plugin_LMS)

---