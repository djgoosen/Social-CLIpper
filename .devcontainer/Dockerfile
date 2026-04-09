FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

USER root
# Full FFmpeg with subtitles/libass for real transcode + burn-in (see README).
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends ffmpeg \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# postCreate pip installs may land in ~/.local/bin; avoid devcontainer.json PATH
# substitution (${containerEnv:PATH}) which can collapse PATH on rebuild.
ENV PATH="/home/vscode/.local/bin:${PATH}"

USER vscode
# Whisper pulls PyTorch. Default PyPI `torch` on Linux (including aarch64) can drag in multi‑GB
# NVIDIA CUDA wheels; devcontainers are almost always CPU-only. Install CPU PyTorch from PyTorch’s index first.
RUN python3 -m pip install --user --no-cache-dir --upgrade pip setuptools wheel \
    && python3 -m pip install --user --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
