FROM python:3.12-slim
# GHCR 패키지를 이 레포에 연결한다 (Actions의 GITHUB_TOKEN으로 push 하려면 필요)
LABEL org.opencontainers.image.source=https://github.com/sh1220/NGDS-team08
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
USER 10001
EXPOSE 8000 9000
CMD ["python", "server.py"]
