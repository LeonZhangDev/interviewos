FROM python:3.12-slim
RUN useradd -m runner
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
USER runner
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
