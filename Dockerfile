FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pil ffmpeg mediainfo fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /app studio
WORKDIR /app
COPY *.py ./
COPY static/ static/
RUN install -d -o studio -g studio uploads outputs
USER studio
EXPOSE 9191
CMD ["python3", "app.py", "--bind", "0.0.0.0"]
