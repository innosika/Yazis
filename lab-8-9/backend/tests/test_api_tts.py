from typing import Any


def test_ready(client: Any) -> None:
    r = client.get("/api/health/ready")
    assert r.status_code == 200
    assert r.json()["tts"] == "ready"


def test_voices(client: Any) -> None:
    voices = client.get("/api/tts/voices").json()
    assert any(v["id"] == "af_heart" and v["featured"] for v in voices)
    assert {v["accent"] for v in voices} == {"us", "gb"}


def test_synthesize_maps_words_to_source(client: Any) -> None:
    text = "Sorting takes O(n log n) time [12]."
    r = client.post("/api/tts/synthesize", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spoken"] == "Sorting takes big O of n log n time."
    spans = [text[w["src_start"] : w["src_end"]] for w in body["words"]]
    # "big O of n log n" is one highlight over the whole expression
    assert spans == ["Sorting", "takes", "O(n log n)", "time"]
    starts = [w["start"] for w in body["words"]]
    assert starts == sorted(starts)
    wav = client.get(body["audio_url"])
    assert wav.status_code == 200
    assert wav.content[:4] == b"RIFF"


def test_second_request_hits_cache(client: Any) -> None:
    payload = {"text": "Caching makes the second request instant."}
    first = client.post("/api/tts/synthesize", json=payload).json()
    second = client.post("/api/tts/synthesize", json=payload).json()
    assert not first["cached"]
    assert second["cached"]
    assert second["id"] == first["id"]


def test_pitch_keeps_tempo(client: Any) -> None:
    base = client.post(
        "/api/tts/synthesize", json={"text": "Pitch should not change tempo."}
    ).json()
    high = client.post(
        "/api/tts/synthesize", json={"text": "Pitch should not change tempo.", "pitch": 3}
    ).json()
    assert base["id"] != high["id"]
    assert abs(high["duration"] - base["duration"]) / base["duration"] < 0.05


def test_speed_changes_duration(client: Any) -> None:
    slow = client.post(
        "/api/tts/synthesize", json={"text": "One two three four.", "speed": 0.5}
    ).json()
    fast = client.post(
        "/api/tts/synthesize", json={"text": "One two three four.", "speed": 2}
    ).json()
    assert slow["duration"] > fast["duration"] * 3


def test_unknown_voice_is_422(client: Any) -> None:
    r = client.post("/api/tts/synthesize", json={"text": "Hi.", "voice": {"id": "zz_nobody"}})
    assert r.status_code == 422


def test_heading_kind(client: Any) -> None:
    r = client.post("/api/tts/synthesize", json={"text": "3.2 Related Work", "kind": "heading"})
    assert r.json()["spoken"] == "Section 3 point 2. Related Work."


def test_normalize_endpoint(client: Any) -> None:
    r = client.post("/api/tts/normalize", json={"texts": ["Use SQL.", "O(1) lookups"]})
    assert r.json()["spoken"] == ["Use sequel.", "big O of 1 lookups"]


def test_segment_endpoint(client: Any) -> None:
    text = "First sentence. Second one, e.g. this.\n\nNew paragraph here."
    units = client.post("/api/tts/segment", json={"text": text}).json()["units"]
    assert [text[u["start"] : u["end"]] for u in units] == [
        "First sentence.",
        "Second one, e.g. this.",
        "New paragraph here.",
    ]
    assert [u["paragraph"] for u in units] == [0, 0, 1]


def test_lexicon_changes_audio(client: Any) -> None:
    before = client.post("/api/tts/synthesize", json={"text": "Kubernetes scales."}).json()
    r = client.post("/api/lexicon", json={"term": "Kubernetes", "say_as": "k eight s"})
    assert r.status_code == 201
    after = client.post("/api/tts/synthesize", json={"text": "Kubernetes scales."}).json()
    assert after["spoken"] == "k eight s scales."
    assert after["id"] != before["id"]
    entries = client.get("/api/lexicon").json()["entries"]
    client.delete(f"/api/lexicon/{entries[0]['id']}")
    again = client.post("/api/tts/synthesize", json={"text": "Kubernetes scales."}).json()
    assert again["spoken"] == "koober netties scales."


def test_settings_roundtrip(client: Any) -> None:
    s = client.get("/api/settings").json()
    assert s["voice"]["voice"] == "af_heart"
    s["voice"]["speed"] = 1.25
    s["listening"]["language"] = "ru"
    assert client.put("/api/settings", json=s).status_code == 200
    again = client.get("/api/settings").json()
    assert again["voice"]["speed"] == 1.25
    assert again["listening"]["language"] == "ru"
