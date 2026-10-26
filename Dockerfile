# Reproducibility image: CPU-only Python env + Node for the app. Build: make docker
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends make git nodejs npm clang-format \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /dwell
COPY requirements.lock pyproject.toml ./
RUN uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.lock
COPY . .
RUN uv pip install --python .venv/bin/python -e . --no-deps
ENV PYTHONHASHSEED=0 MPLBACKEND=Agg
CMD ["make", "reproduce-quick"]
