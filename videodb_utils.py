import os
from typing import Optional, Tuple, List, Dict
import videodb

def connect_videodb(api_key: str):
    return videodb.connect(api_key=api_key)

def ensure_collection(conn, name: str):
    try:
        return conn.create_collection(name, f"Collection {name}")
    except Exception:
        return conn.get_collection(name)

def upload_video_any(collection, url: Optional[str] = None, file=None) -> Tuple[Optional[object], Optional[str]]:
    if url:
        vid = collection.upload(url=url)
        return vid, url
    if file is not None:
        tmp_path = os.path.join(os.getcwd(), f"uploaded_{file.name}")
        with open(tmp_path, "wb") as f:
            f.write(file.read())
        vid = collection.upload(path=tmp_path)
        return vid, None
    raise ValueError("Provide a YouTube URL or upload a file.")

def ensure_index_spoken(video):
    try:
        video.index_spoken_words()
    except Exception as e:
        if "already" in str(e).lower():
            return
        raise

def get_transcript_text_safe(video) -> str:
    try:
        return video.get_transcript_text()
    except Exception:
        try:
            tr = video.get_transcript()
            return getattr(tr, "text", "")
        except Exception:
            return ""

def build_embed_player(url: Optional[str], start: int = 0) -> str:
    if url and "youtube.com" in url and "v=" in url:
        vid_id = url.split("v=")[-1].split("&")[0]
        src = f"https://www.youtube.com/embed/{vid_id}?start={int(start)}&autoplay=0"
        return f'<iframe width="640" height="360" src="{src}" frameborder="0" allowfullscreen></iframe>'
    return "<p>No embeddable URL available. If this is a file upload, use Highlight Reel to generate a stream.</p>"

def shots_table_html(url: Optional[str], segments: List[Dict], title: str = "Top matches") -> str:
    if not segments:
        return "<p>No segments to show.</p>"
    vid_id = None
    if url and "v=" in url:
        vid_id = url.split("v=")[-1].split("&")[0]

    rows = []
    for i, s in enumerate(segments, 1):
        if vid_id is not None:
            ylink = f"https://www.youtube.com/watch?v={vid_id}&t={int(s['start_time'])}s"
            ts_html = f"<a href='{ylink}' target='_blank'>{s['timestamp']}</a>"
        else:
            ts_html = s["timestamp"]
        rows.append(
            f"<tr>"
            f"<td style='padding:6px'>{i}</td>"
            f"<td style='padding:6px'>{ts_html}</td>"
            f"<td style='padding:6px'>{s['score']}</td>"
            f"<td style='padding:6px'>{s['text']}</td>"
            f"</tr>"
        )

    html = (
        f"<h4>{title}</h4>"
        "<table style='border-collapse:collapse;border:1px solid #ddd;width:100%'>"
        "<tr>"
        "<th style='padding:6px;text-align:left'>#</th>"
        "<th style='padding:6px;text-align:left'>Timestamp</th>"
        "<th style='padding:6px;text-align:left'>Score</th>"
        "<th style='padding:6px;text-align:left'>Preview</th>"
        "</tr>"
        + "".join(rows)
        + "</table>"
    )
    return html

# - best effort listing helpers (some SDKs expose these, some do not)
def list_collections_safe(conn):
    try:
        return conn.list_collections()
    except Exception:
        try:
            return conn.get_collections()
        except Exception:
            return []

def list_videos_safe(collection):
    try:
        return collection.list_videos()
    except Exception:
        try:
            return collection.get_videos()
        except Exception:
            return []
