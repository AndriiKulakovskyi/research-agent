# Stage 1: build the React UI
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .
COPY --from=ui /ui/dist frontend/dist
COPY examples/ examples/

ENV DEEP_AGENT_WORKSPACE=/data/workspace
VOLUME /data
EXPOSE 8000
CMD ["deep-harness-server"]
