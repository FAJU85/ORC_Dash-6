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

AI-Powered Academic Analytics Platform

## Features

- 📚 Publication tracking from OpenAlex
- 🤖 AI-powered research assistant
- 📊 Interactive analytics & visualizations
- 🔐 Secure admin panel with 2FA
- 🐛 Bug reporting system

## Setup Required

Configure the following in Space secrets:

- `CLOUDFLARE_ACCOUNT_ID` - Cloudflare account ID
- `CLOUDFLARE_API_TOKEN` - Cloudflare API token  
- `CLOUDFLARE_D1_DATABASE_ID` - D1 database ID
- `AI_API_KEY` or `GROQ_API_KEY` - AI service API key

## Quick Start

1. Add your secrets to the Space settings
2. The app will automatically connect to the database
3. Go to Publications page to sync from OpenAlex
4. Use AI Assistant to analyze papers

---
Powered by [Fahad Al-Jubalie](https://www.linkedin.com/in/fahad-al-jubalie-55973926/)