import os
import time
from typing import Optional

import streamlit as st
import videodb
from videodb import SearchType, IndexType

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

# session defaults
if "video_id" not in st.session_state:
    st.session_state["video_id"] = None
if "video_url" not in st.session_state:
    st.session_state["video_url"] = None
if "video_collection_name" not in st.session_state:
    st.session_state["video_collection_name"] = None
if "debug" not in st.session_state:
    st.session_state["debug"] = False


# --------------- Sidebar: keys and settings ---------------
st.sidebar.title("Settings")

VIDEODB_API_KEY = st.secrets.get("VIDEODB_API_KEY", os.getenv("VIDEODB_API_KEY", ""))
GEMINI_API_KEY  = st.secrets.get("GEMINI_API_KEY",  os.getenv("GEMINI_API_KEY",  ""))
OPENAI_API_KEY  = st.secrets.get("OPENAI_API_KEY",  os.getenv("OPENAI_API_KEY",  ""))
GROQ_API_KEY    = st.secrets.get("GROQ_API_KEY",    os.getenv("GROQ_API_KEY",    ""))

AI_PROVIDER = st.sidebar.selectbox("AI provider", ["gemini", "openai", "groq", "none"], index=0)
COLLECTION_NAME = st.sidebar.text_input("Collection name", value="educational_videos")
TOP_K = st.sidebar.slider("Results per query", 1, 10, 5)
MAX_SEGMENT_PREVIEW = st.sidebar.slider("Preview chars", 80, 400, 220, 20)

st.sidebar.checkbox("Show debug", value=st.session_state["debug"], key="debug")

st.sidebar.markdown("---")
st.sidebar.caption("Keys are read from Streamlit secrets. You only need VideoDB and Gemini.")


# --------------- Header ---------------
st.title("VideoRAG - Conversational Video Learning")
st.caption("Upload or link a video. Index transcript. Ask questions. Get exact moments, quizzes, and highlight reels.")

# --------------- Connect to VideoDB ---------------
if not VIDEODB_API_KEY:
    st.warning("Add your VideoDB API key to Streamlit Secrets.")
    st.stop()

try:
    conn = connect_videodb(VIDEODB_API_KEY)
    # Important: do not overwrite the collection name used at ingest time
    # We will use COLLECTION_NAME for new ingests only
    current_collection = ensure_collection(conn, COLLECTION_NAME)
except Exception as e:
    st.error(f"VideoDB connection error: {e}")
    st.stop()

if st.session_state["debug"]:
    st.sidebar.write("session_state:", {
        "video_id": st.session_state["video_id"],
        "video_url": st.session_state["video_url"],
        "video_collection_name": st.session_state["video_collection_name"],
        "sidebar_collection_name": COLLECTION_NAME,
    })


# helper to reopen the exact collection used for the active video
def get_active_collection():
    name = st.session_state.get("video_collection_name")
    if not name:
        return None
    try:
        return ensure_collection(conn, name)
    except Exception:
        return None


# helper to get current Video object
def get_current_video():
    vid_id = st.session_state.get("video_id")
    coll_name = st.session_state.get("video_collection_name")
    if not vid_id or not coll_name:
        return None
    try:
        coll = ensure_collection(conn, coll_name)
        return coll.get_video(vid_id)
    except Exception as e:
        if st.session_state["debug"]:
            st.sidebar.warning(f"get_current_video failed: {e}")
        return None


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
        if not chosen_url and not uploaded_file:
            st.warning("Paste a URL or upload a file.")
        else:
            with st.spinner("Uploading and indexing..."):
                try:
                    # Always upload into the sidebar collection name
                    video, working_url = upload_video_any(current_collection, url=chosen_url, file=uploaded_file)
                    if not video:
                        st.error("Upload failed. Try another URL or file.")
                        st.stop()

                    ensure_index_spoken(video)

                    # Persist the exact collection used for this video
                    st.session_state["video_id"] = video.id
                    st.session_state["video_url"] = working_url
                    st.session_state["video_collection_name"] = COLLECTION_NAME

                    st.success("Indexed and saved as active video.")
                except Exception as e:
                    st.error(f"Error: {e}")

    if st.session_state.get("video_id"):
        st.info(f"Active video id: {st.session_state['video_id']}")
        st.components.v1.html(
            build_embed_player(st.session_state.get("video_url"), start=0),
            height=380,
        )


# --------------- Ask & Search ---------------
with tab_search:
    st.subheader("Ask questions and jump to exact moments")
    video = get_current_video()
    if not video:
        st.warning("Add and index a video first in the Upload tab.")
        st.stop()

    ai_client, used_provider = setup_ai(AI_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY)
    if used_provider == "none":
        st.caption("AI is off. The app still returns top matching segments.")

    vr = VideoRAG(video, collection=get_active_collection())

    qcol1, qcol2 = st.columns([3, 1])
    with qcol1:
        question = st.text_input("Ask a question", "What is the main topic?")
    with qcol2:
        run_btn = st.button("Search", type="primary")

    if run_btn and question.strip():
        with st.spinner("Searching..."):
            segments = vr.search_video_content(question, max_results=TOP_K)
            if not segments:
                st.warning("No matches. Try simpler words like overview, definition, or example.")
            else:
                context = "\n".join(
                    f"{s['timestamp']}: {s['text']}" for s in segments[:3] if s.get("text")
                )
                if used_provider != "none" and ai_client is not None and context:
                    prompt = (
                        "Answer briefly using the lines with timestamps. "
                        "End with the best timestamp.\n\n"
                        f"Question: {question}\n\nContext:\n{context}\n"
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

                html = shots_table_html(st.session_state.get("video_url"), segments, title="Top matches")
                st.components.v1.html(html, height=260, scrolling=True)

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
            vr = VideoRAG(video, collection=get_active_collection())
            segments = vr.search_video_content(topic, max_results=8)
            context = "\n".join(f"{s['timestamp']}: {s['text']}" for s in segments if s.get("text"))

            ai_client, used_provider = setup_ai(AI_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY)
            if used_provider == "none" or ai_client is None or not context:
                st.warning("AI is off or context is empty. Showing basic prompts you can copy.")
                for i in range(num_q):
                    st.write(f"Q{i+1}. Based on segment {segments[i % max(1,len(segments))]['timestamp']}, write a question.")
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
            vr = VideoRAG(video, collection=get_active_collection())
            topic_list = [t.strip() for t in topics.split(",") if t.strip()]
            all_segments = []
            for t in topic_list:
                all_segments.extend(vr.search_video_content(t, max_results=3))

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
                # Try stitched stream
                stream_url = None
                try:
                    stream_url = video.generate_stream(timeline=timeline)
                except Exception:
                    pass

                if stream_url:
                    st.video(stream_url)
                else:
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
        st.download_button("Download transcript txt", data=text, file_name="transcript.txt", mime="text/plain")
        st.text_area("Preview", value=text[:5000], height=360)
