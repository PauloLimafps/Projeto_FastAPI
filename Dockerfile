# Usa uma imagem Python leve e estável
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala as dependências do sistema necessárias para algumas libs Python
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia primeiro apenas o requirements.txt para aproveitar o cache de camadas do Docker
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos do projeto para o container
COPY . .

# Expõe a porta que o FastAPI usará
EXPOSE 8000

# Comando para iniciar o servidor via Uvicorn
# O host 0.0.0.0 é obrigatório para ser acessível fora do container
CMD ["uvicorn", "orquestrador:app", "--host", "0.0.0.0", "--port", "8000"]
