from typing import List, Dict
from videodb import SearchType, IndexType


def rewrite_query(question: str) -> List[str]:
    q = question.lower()
    if any(k in q for k in ["main topic", "about", "overview", "summary"]):
        return ["overview", "introduction", "main idea", "summary"]
    if any(k in q for k in ["key concept", "concept", "definition"]):
        return ["key concept", "main concept", "definition", "core idea"]
    if any(k in q for k in ["example", "demo", "case"]):
        return ["example", "for example", "demonstration", "case study"]
    return [question]


def shots_to_segments(search_res, max_results: int = 5) -> List[Dict]:
    shots = []
    try:
        shots = search_res.get_shots() or []
    except Exception:
        try:
            shots = list(search_res)
        except Exception:
            shots = []

    segments = []
    for s in shots[:max_results]:
        start = getattr(s, "start", 0)
        end = getattr(s, "end", start + 30)
        text = (getattr(s, "text", "") or "").strip()
        score = getattr(s, "search_score", getattr(s, "score", 0.0))
        try:
            score = float(score)
            score = round(score * 100, 1) if score <= 1 else round(score, 1)
        except Exception:
            score = 0.0
        ts = f"{int(start//60):02d}:{int(start%60):02d}"
        segments.append(
            {
                "start_time": int(start),
                "end_time": int(end),
                "timestamp": ts,
                "text": text[:220],
                "score": score,
            }
        )
    return segments


class VideoRAG:
    def __init__(self, video, collection=None):
        self.video = video
        self.collection = collection

    def search_video_content(self, question: str, max_results: int = 5):
        expansions = rewrite_query(question)
        all_segments = []

        # semantic spoken
        for q in expansions:
            try:
                res = self.video.search(
                    query=q,
                    search_type=SearchType.semantic,
                    index_type=IndexType.spoken_word,
                    top_k=10,
                )
                all_segments += shots_to_segments(res, max_results)
            except Exception as e:
                if "No results found" not in str(e):
                    print(f"Semantic warn: {e}")

        # keyword spoken
        if not all_segments:
            for q in expansions:
                try:
                    res_kw = self.video.search(
                        query=q,
                        search_type=SearchType.keyword,
                        index_type=IndexType.spoken_word,
                        top_k=10,
                    )
                    all_segments += shots_to_segments(res_kw, max_results)
                except Exception as e:
                    if "No results found" not in str(e):
                        print(f"Keyword warn: {e}")

        # collection semantic
        if not all_segments and self.collection:
            try:
                res_coll = self.collection.search(query=question, top_k=10)
                all_segments += shots_to_segments(res_coll, max_results)
            except Exception as e:
                if "No results found" not in str(e):
                    print(f"Collection warn: {e}")

        # dedupe by start_time
        seen = set()
        unique = []
        for s in all_segments:
            key = int(s["start_time"])
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique[:max_results]
