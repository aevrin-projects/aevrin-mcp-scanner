FROM python:3.12-slim
RUN pip install --no-cache-dir bandit==1.8.0
ENTRYPOINT ["bandit"]
