FROM 5hojib/aeon:latest

WORKDIR /app
RUN chmod 777 /app

RUN uv venv
COPY requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["bash", "start.sh"]
