# 📊 Relatório de Status da Arquitetura RAG

Com base no diagrama da arquitetura (as Setas do projeto), aqui está o status consolidado de nossas entregas até o momento.

### Progresso Geral: **Aproximadamente 45% Concluído**

| Etapa/Seta | Status | Descrição |
| :--- | :--- | :--- |
| **Seta 1: Segurança e Autenticação** | ✅ **100%** | Moodle assina requisições com JWT (HS256). FastAPI valida a assinatura e extrai o Payload com segurança. Fim do risco de chamadas não autorizadas. |
| **Integração (Infraestrutura Base)** | ✅ **100%** | Dockerização do FastAPI e comunicação nativa de rede via `docker-compose`. |
| **Enriquecimento de Contexto** | ⏸️ **0%** | Planejado, mas retido por barreiras de UI no frontend do Moodle (JS Compile). |
| **Seta 2: Gateway e Rate Limiting** | ⏳ **0%** | Próxima fase. Camada de controle de tráfego. |

---

# 🛣️ Seta 2: API Gateway (Roteamento e Rate Limit)

A "Seta 2" do seu diagrama se refere à introdução de um **API Gateway** — normalmente utilizando a ferramenta **Traefik** ou **NGINX** — que ficará na "linha de frente" do seu projeto, entre o Moodle e o FastAPI.

## 1. O que isso garante ao meu projeto?

> [!TIP]
> **Proteção Contra Sobrecarga e Ataques**
> Atualmente, se um aluno mal-intencionado (ou um script de erro no Moodle) disparar 5.000 mensagens no chat num intervalo de 1 minuto, a requisição baterá direta no FastAPI. O FastAPI vai mandar tudo para a OpenAI. **Resultado:** Sua conta da OpenAI será travada por "Quota Exceeded" ou você pagará uma fatura astronômica. 

O Rate Limiting garante que um usuário (ou endereço IP) possa fazer apenas `X` requisições por minuto. Se passar disso, o Gateway bloqueia e devolve um aviso: *"Muitas requisições. Tente de novo em instantes."*

## 2. Por que isso é estritamente necessário para Produção?

- **Gestão de Custos Sensível:** A OpenAI cobra por tokens. Um pico de requisições, proposital ou acidental, pode custar muito caro.
- **Prevenção de Quedas (DDoS):** Se centenas de alunos usarem na véspera da prova simultaneamente, o servidor do banco de dados (Weaviate) e do FastAPI podem congelar pela falta de memória. O Gateway organiza uma fila de chamadas saudável.
- **Roteamento HTTPS Limpo:** No momento, seu FastAPI está na porta `8000`. Um Gateway como o Traefik permite que a sua IA responda diretamente em um subdomínio bonito (ex: `https://api.suafaculdade.com/chat`), já com certificado SSL gratuito automático.

## 3. O que mudaremos no código (CASO você decida seguir)

O código Python (`orquestrador.py`) e o PHP do Moodle não sofrerão **nenhuma** alteração de lógica. Toda a mudança será feita na **Arquitetura (Infraestrutura)** do servidor atual.

Abaixo estão os únicos arquivos que modificaríamos:

### 📄 `docker-compose.yml` (A Grande Mudança)
Nós adicionaremos um novo "container" chamado **Traefik** (O Gateway).
- O FastAPI não ficará mais acessível diretamente pela "porta 8000" para a internet. 
- Apenas a porta 80 e 443 do Traefik ficarão abertas.
- Vamos configurar *labels* no FastAPI para dizer ao Traefik: *"Se alguém bater na rota /chat mais de 10 vezes em 1 minuto, bloqueie"*.

### 📄 Arquivos `.env` (Pequena Mudança)
Adicionaremos variáveis para o Traefik, como o e-mail de administrador (para gerar o certificado SSL encryotado) e a URL do novo subdomínio, se existir.

### 📄 Moodle (Configurações do Plugin)
Dentro do Painel Administrativo do Moodle (no bloco OpenAI), não precisaremos programar nada, apenas acessar a tela de configuração e trocar a URL de `http://localhost:8000/chat` para a URL protegida do Gateway, ex: `https://api.suadominio.com/chat`.
