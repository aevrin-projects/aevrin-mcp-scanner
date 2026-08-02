FROM node:20-slim
RUN npm install -g mcp-shield@1.0.4
ENTRYPOINT ["mcp-shield"]
