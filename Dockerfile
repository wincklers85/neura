FROM debian:bookworm-slim AS llama-build
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential libcurl4-openssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /src/llama.cpp \
 && cmake -S /src/llama.cpp -B /src/llama.cpp/build -DGGML_NATIVE=OFF -DGGML_OPENMP=ON -DLLAMA_CURL=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON \
 && cmake --build /src/llama.cpp/build --config Release -j2 --target llama-server

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/var/data HF_HOME=/var/data/huggingface LLM_BASE_URL=http://127.0.0.1:8080/v1 MODEL_NAME=neura-local LOCAL_MODEL=Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libcurl4 ca-certificates bash && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=llama-build /src/llama.cpp/build/bin/llama-server /opt/llama/bin/llama-server
COPY . .
RUN mkdir -p /var/data /var/data/huggingface && chmod +x /app/start.sh
EXPOSE 10000
CMD ["/app/start.sh"]
