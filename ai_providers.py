from typing import Tuple, Optional


def setup_ai(provider: str, gemini_key: str, openai_key: str, groq_key: str):
    provider = provider or "none"
    provider = provider.lower()
    if provider == "gemini":
        if not gemini_key:
            return None, "none"
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            client = genai.GenerativeModel("gemini-1.5-flash")
            return client, "gemini"
        except Exception as e:
            print(f"Gemini setup error: {e}")
            return None, "none"

    if provider == "openai":
        if not openai_key:
            return None, "none"
        try:
            import openai
            openai.api_key = openai_key
            return openai, "openai"
        except Exception as e:
            print(f"OpenAI setup error: {e}")
            return None, "none"

    if provider == "groq":
        if not groq_key:
            return None, "none"
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            return client, "groq"
        except Exception as e:
            print(f"Groq setup error: {e}")
            return None, "none"

    return None, "none"


def ai_answer(client, provider: str, prompt: str) -> Optional[str]:
    try:
        if provider == "gemini":
            resp = client.generate_content(prompt)
            return getattr(resp, "text", None)
        if provider == "openai":
            resp = client.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            return resp.choices[0].message.content
        if provider == "groq":
            resp = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="mixtral-8x7b-32768",
                temperature=0.5,
            )
            return resp.choices[0].message.content
        return None
    except Exception as e:
        print(f"AI call error: {e}")
        return None
