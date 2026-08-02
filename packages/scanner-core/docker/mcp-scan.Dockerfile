FROM python:3.12-slim
RUN pip install --no-cache-dir snyk-agent-scan==0.5.15
ENTRYPOINT ["snyk-agent-scan"]
