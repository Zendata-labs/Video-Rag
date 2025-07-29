# VideoRAG - Conversational Video Learning

Streamlit app for the AI Demos x VideoDB hackathon.

## Features
- Paste a YouTube URL or upload a local video
- Auto index spoken words and generate transcript
- Ask questions and jump to exact moments
- See top matches with timestamps and previews
- Generate a small quiz
- Build a highlight reel from topics

## Setup

### Local
1. `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill keys.
4. `streamlit run app.py`

### Streamlit Cloud
1. Push this folder to GitHub.
2. Create new Streamlit app from repo.
3. In app settings, add Secrets:
