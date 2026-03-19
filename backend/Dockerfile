FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install large packages first with extended timeout to avoid network drops
RUN pip install --no-cache-dir --timeout=300 xgboost==2.0.3 scipy
RUN pip install --no-cache-dir --timeout=300 -r requirements.txt

COPY . .

RUN mkdir -p saved_models

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
