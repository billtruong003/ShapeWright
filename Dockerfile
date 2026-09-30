# Shapewright in a container: `docker build -t shapewright .`
#   docker run --rm -v "$PWD:/work" shapewright brief "a wooden barrel"
#   docker run --rm -i -v "$PWD:/work" shapewright mcp          # MCP over stdio
# /work is the project folder (run `sw init` there once). Includes Node + the Khronos glTF validator.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/shapewright
COPY . .
RUN pip install --no-cache-dir ".[mcp]" \
    && (cd tools/gltf-validator && npm install --omit=dev --no-audit --no-fund) \
    && rm -rf /root/.npm

ENV SW_GLTF_VALIDATOR=/opt/shapewright/tools/gltf-validator
WORKDIR /work
ENTRYPOINT ["sw"]
CMD ["doctor"]
