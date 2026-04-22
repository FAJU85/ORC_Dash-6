---
title: ORC Research Dashboard
emoji: 🔬
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.40.0
app_file: app.py
pinned: false
license: mit
tags:
- research
- academic
- analytics
- publications
- ai-assistant
---

# ORC Research Dashboard 🔬

AI-Powered Academic Analytics Platform | Powered by Hugging Face

## Features

- 📚 Publication tracking from OpenAlex
- 🤖 AI-powered research assistant
- 📊 Interactive analytics & visualizations
- 🔐 Secure admin panel with 2FA
- 🐛 Bug reporting system
- ☁️ Hugging Face native data storage

## Setup Required

Configure the following in **Space secrets**:

| Secret | Description |
|--------|-------------|
| `HF_TOKEN` | Hugging Face API token (required) |
| `HF_REPO_ID` | Your HF dataset repo (e.g., `username/orc-publications`) |
| `AI_API_KEY` | AI service API key (optional) |

### Creating a Hugging Face Dataset

1. Go to https://huggingface.co/new-dataset
2. Create a new dataset (e.g., `orc-publications`)
3. Copy the repo ID (e.g., `yourusername/orc-publications`)
4. Add it to Space secrets as `HF_REPO_ID`

## Quick Start

1. Clone this repo to a new Hugging Face Space
2. Add `HF_TOKEN` and `HF_REPO_ID` to Space secrets
3. The app will automatically create the dataset on first sync
4. Go to Publications page and enter your ORCID to sync
5. Use AI Assistant to analyze papers

---
Powered by [Fahad Al-Jubalie](https://www.linkedin.com/in/fahad-al-jubalie-55973926/)