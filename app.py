import os
import time
from typing import List, Dict, Tuple, Optional

import streamlit as st
from videodb import SearchType, IndexType
import videodb

# read only from secrets or env for deployment
VIDEODB_API_KEY = st.secrets.get("VIDEODB_API_KEY", os.getenv("VIDEODB_API_KEY", ""))
GEMINI_API_KEY  = st.secrets.get("GEMINI_API_KEY",  os.getenv("GEMINI_API_KEY",  ""))
OPENAI_API_KEY  = st.secrets.get("OPENAI_API_KEY",  os.getenv("OPENAI_API_KEY",  ""))
GROQ_API_KEY    = st.secrets.get("GROQ_API_KEY",    os.getenv("GROQ_API_KEY",    ""))

AI_PROVIDER = st.sidebar.selectbox("AI provider", ["gemini", "none"], index=0)
st.sidebar.caption("Keys are loaded from Streamlit secrets.")

from videorag import VideoRAG
from videodb_utils import (
    connect_videodb,
    ensure_collection,
    upload_video_any,
    ensure_index_spoken,
    get_transcript_text_safe,
    build_embed_player,
    shots_table_html,
)
from ai_providers import setup_ai, ai_answer


# --------------- App config ---------------
st.set_page_config(page_title="VideoRAG by ibrahim", page_icon="🎬", layout="wide")

if "session" not in st.session_state:
    st.session_state.session = {}


# --------------- Sidebar: keys and settings ---------------
st.sidebar.title("Settings")

# Prefer secrets when deployed on Streamlit Cloud. Otherwise .env or hard-coded.
VIDEODB_API_KEY = st.sidebar.text_input(
    "VideoDB API key",
    value=st.secrets.get("VIDEODB_API_KEY", os.getenv("VIDEODB_API_KEY", "")),
    type="password",
)

AI_PROVIDER = st.sidebar.selectbox(
    "AI provider",
    ["gemini", "openai", "groq", "none"],
    index=0,
)

GEMINI_API_KEY = st.sidebar.text_input(
    "Gemini key",
    value=st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")),
    type="password",
)

OPENAI_API_KEY = st.sidebar.text_input(
    "OpenAI key",
    value=st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
    type="password",
)

GROQ_API_KEY = st.sidebar.text_input(
    "Groq key",
    value=st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", "")),
    type="password",
)

COLLECTION_NAME = st.sidebar.text_input("Collection name", value="educational_videos")
TOP_K = st.sidebar.slider("Results per query", 1, 10, 5)
MAX_SEGMENT_PREVIEW = st.sidebar.slider("Preview chars", 80, 400, 220, 20)

st.sidebar.markdown("---")
st.sidebar.caption("Tip: if AI keys are empty, the app still works with VideoDB only.")


# --------------- Header ---------------
st.title("VideoRAG - Conversational Video Learning")
st.caption("Upload or link a video. Index transcript. Ask questions. Get exact moments, quizzes, and highlight reels.")

# --------------- Connect to VideoDB ---------------
if not VIDEODB_API_KEY:
    st.warning("Add your VideoDB API key in the sidebar to begin.")
    st.stop()

try:
    conn = connect_videodb(VIDEODB_API_KEY)
    coll = ensure_collection(conn, COLLECTION_NAME)
except Exception as e:
    st.error(f"VideoDB connection error: {e}")
    st.stop()

# --------------- Tabs ---------------
tab_upload, tab_search, tab_quiz, tab_reel, tab_transcript = st.tabs(
    ["Upload or Link", "Ask & Search", "Quiz", "Highlight Reel", "Transcript"]
)


# --------------- Upload or Link ---------------
with tab_upload:
    st.subheader("Add video")
    source_type = st.radio("Choose source", ["YouTube URL", "Local upload"], horizontal=True)

    chosen_url = None
    uploaded_file = None

    if source_type == "YouTube URL":
        chosen_url = st.text_input("Paste a YouTube link")
        st.caption("Example: https://www.youtube.com/watch?v=fNk_zzaMoSs")
    else:
        uploaded_file = st.file_uploader("Upload a video file", type=["mp4", "mov", "mkv", "webm"])

    if st.button("Ingest and index", type="primary"):
        with st.spinner("Uploading and indexing..."):
            try:
                video, working_url = upload_video_any(
                    coll, url=chosen_url, file=uploaded_file
                )
                if not video:
                    st.error("Upload failed. Try another URL or file.")
                    st.stop()
                st.session_state["video_id"] = video.id
                st.session_state["video_url"] = working_url
                ensure_index_spoken(video)
                st.success("Indexed spoken words. Ready for search.")
            except Exception as e:
                st.error(f"Error: {e}")

    if "video_id" in st.session_state:
        st.info(f"Active video id: {st.session_state['video_id']}")
        st.components.v1.html(
            build_embed_player(st.session_state.get("video_url"), start=0),
            height=380,
        )

# Helper to get current Video object
def get_current_video():
    vid_id = st.session_state.get("video_id")
    if not vid_id:
        return None
    try:
        return coll.get_video(vid_id)
    except Exception:
        return None


# --------------- Ask & Search ---------------
with tab_search:
    st.subheader("Ask questions and jump to exact moments")
    video = get_current_video()
    if not video:
        st.warning("Add and index a video first in the Upload tab.")
        st.stop()

    # AI setup
    ai_client, used_provider = setup_ai(
        AI_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY
    )
    if used_provider == "none":
        st.caption("AI is disabled. Answers will show top matching segments.")

    # Build RAG engine
    vr = VideoRAG(video, collection=coll)

    qcol1, qcol2 = st.columns([3, 1])
    with qcol1:
        question = st.text_input("Ask a question about the video", "What is the main topic?")
    with qcol2:
        run_btn = st.button("Search", type="primary")

    if run_btn and question.strip():
        with st.spinner("Searching..."):
            segments = vr.search_video_content(question, max_results=TOP_K)
            if not segments:
                # last resort: show first seconds of transcript if available
                st.warning("No matches. Try simpler keywords like overview, definition, or example.")
            else:
                # show AI or basic answer
                context = "\n".join(
                    f"{s['timestamp']}: {s['text']}" for s in segments[:3] if s.get("text")
                )
                if used_provider != "none" and ai_client is not None and context:
                    prompt = (
                        "Answer the question using the lines with timestamps. "
                        "Be concise. End by citing the best timestamp.\n\n"
                        f"Question: {question}\n\n"
                        f"Context:\n{context}\n"
                    )
                    answer = ai_answer(ai_client, used_provider, prompt)
                    if answer:
                        st.success(answer)
                    else:
                        best = segments[0]
                        st.info(f"Found at {best['timestamp']} (score {best['score']}%)\n\n{best['text']}")
                else:
                    best = segments[0]
                    st.info(f"Found at {best['timestamp']} (score {best['score']}%)\n\n{best['text']}")

                # table of segments
                html = shots_table_html(st.session_state.get("video_url"), segments, title="Top matches")
                st.components.v1.html(html, height=240, scrolling=True)

                # player at best segment
                st.components.v1.html(
                    build_embed_player(st.session_state.get("video_url"), start=int(segments[0]["start_time"])),
                    height=380,
                )


# --------------- Quiz ---------------
with tab_quiz:
    st.subheader("Generate a short quiz")
    video = get_current_video()
    if not video:
        st.warning("Add and index a video first in the Upload tab.")
        st.stop()

    topic = st.text_input("Quiz topic", "main concepts")
    num_q = st.slider("Number of questions", 3, 10, 5)
    make_quiz = st.button("Make quiz")

    if make_quiz:
        with st.spinner("Building quiz..."):
            vr = VideoRAG(video, collection=coll)
            segments = vr.search_video_content(topic, max_results=8)
            context = "\n".join(
                f"{s['timestamp']}: {s['text']}" for s in segments if s.get("text")
            )

            ai_client, used_provider = setup_ai(
                AI_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY
            )
            if used_provider == "none" or ai_client is None or not context:
                st.warning("AI is off or context is empty. Showing basic prompts you can copy.")
                for i in range(num_q):
                    st.write(f"Q{i+1}. Based on segment {segments[i % len(segments)]['timestamp']}, write a question.")
            else:
                prompt = (
                    f"Create {num_q} multiple choice questions from the context lines. "
                    "Each item should have question, 4 options A-D, correct letter, and the timestamp. "
                    "Return as markdown with headings.\n\n"
                    f"{context}"
                )
                quiz_md = ai_answer(ai_client, used_provider, prompt)
                if quiz_md:
                    st.markdown(quiz_md)
                else:
                    st.warning("AI failed. Try again or switch provider.")


# --------------- Highlight Reel ---------------
with tab_reel:
    st.subheader("Build a highlight reel")
    video = get_current_video()
    if not video:
        st.warning("Add and index a video first in the Upload tab.")
        st.stop()

    topics = st.text_input("Comma separated topics", "overview, example, key concept")
    make_reel = st.button("Create reel")

    if make_reel:
        with st.spinner("Collecting segments..."):
            vr = VideoRAG(video, collection=coll)
            topic_list = [t.strip() for t in topics.split(",") if t.strip()]
            all_segments = []
            for t in topic_list:
                segs = vr.search_video_content(t, max_results=3)
                all_segments.extend(segs)

            # dedupe and sort
            timeline = []
            seen = set()
            for s in sorted(all_segments, key=lambda x: x["start_time"]):
                key = int(s["start_time"])
                if key in seen:
                    continue
                seen.add(key)
                timeline.append((int(s["start_time"]), int(s["end_time"])))

            if not timeline:
                st.warning("No segments found for a reel. Try different topics.")
            else:
                st.write(f"Segments: {len(timeline)}")
                # Try to generate a playable stream from VideoDB
                stream_url = None
                try:
                    stream_url = video.generate_stream(timeline=timeline)
                except Exception:
                    pass

                if stream_url:
                    st.video(stream_url)
                else:
                    # fallback: play first match in YouTube player
                    st.info("Could not generate stitched stream. Showing first match instead.")
                    st.components.v1.html(
                        build_embed_player(st.session_state.get("video_url"), start=timeline[0][0]),
                        height=380,
                    )


# --------------- Transcript ---------------
with tab_transcript:
    st.subheader("Transcript")
    video = get_current_video()
    if not video:
        st.warning("Add and index a video first in the Upload tab.")
        st.stop()

    with st.spinner("Loading transcript..."):
        text = get_transcript_text_safe(video)
    if not text:
        st.warning("Transcript not available yet.")
    else:
        st.download_button(
            "Download transcript txt",
            data=text,
            file_name="transcript.txt",
            mime="text/plain",
        )
        st.text_area("Preview", value=text[:5000], height=360)
