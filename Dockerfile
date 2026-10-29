FROM python:3.12-slim
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
USER 10001
EXPOSE 8000 9000
CMD ["python", "server.py"]
