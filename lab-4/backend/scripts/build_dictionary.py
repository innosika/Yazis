"""Regenerate the committed dictionary seed from FreeDict.

    python -m scripts.build_dictionary            # latest release
    python -m scripts.build_dictionary --version 2025.11.23

Writes `data/dictionary/eng-rus.jsonl.gz`: one JSON object per headword, streamed, so a
36 MB TEI file never has to fit in memory as a tree.

The output is committed to the repository. `make up` therefore needs no network and always
seeds byte-identical data, while `make dict-rebuild` refreshes it when a new FreeDict
release appears.
"""

import argparse
import gzip
import json
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import settings
from app.mt.textnorm import clean_translation

TEI = "{http://www.tei-c.org/ns/1.0}"
RELEASE_URL = (
    "https://download.freedict.org/dictionaries/eng-rus/{version}/"
    "freedict-eng-rus-{version}.src.tar.xz"
)
DATABASE_URL = "https://freedict.org/freedict-database.json"
USER_AGENT = settings.wiktionary_user_agent


def latest_version() -> str:
    request = urllib.request.Request(DATABASE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        catalogue = json.load(response)
    for dictionary in catalogue:
        if dictionary.get("name") == "eng-rus":
            releases = dictionary.get("releases", [])
            versions = sorted({r["version"] for r in releases if r.get("version")})
            if versions:
                return versions[-1]
    raise SystemExit("eng-rus not found in the FreeDict catalogue")


def download_tei(version: str, into: Path) -> Path:
    url = RELEASE_URL.format(version=version)
    archive = into / "eng-rus.src.tar.xz"
    print(f"downloading {url}", file=sys.stderr)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive.write_bytes(response.read())
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith(".tei"))
        tar.extract(member, path=into, filter="data")
        return into / member.name


def unaccent(form: str) -> str:
    """Drop the combining stress marks the source uses: «се́ть» -> «сеть»."""
    return form.replace("́", "").replace("̀", "")


def convert(tei_path: Path, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as out:
        for _, element in ET.iterparse(tei_path, events=("end",)):
            if element.tag != f"{TEI}entry":
                continue
            record = _entry_to_record(element)
            if record is not None:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
            element.clear()
    return written


def _entry_to_record(element: ET.Element) -> dict | None:
    orth = element.find(f"{TEI}form/{TEI}orth")
    if orth is None or not (orth.text or "").strip():
        return None

    senses = []
    for sense in element.findall(f"{TEI}sense"):
        translations = [
            q.text.strip()
            for q in sense.findall(f'.//{TEI}cit[@type="trans"]/{TEI}quote')
            if (q.text or "").strip()
        ]
        if not translations:
            continue
        definition = sense.find(f".//{TEI}sense/{TEI}def")
        cleaned = [clean_translation(t) for t in translations]
        senses.append(
            {
                "gloss": (definition.text or "").strip() if definition is not None else "",
                "tr": [{"a": t, "p": unaccent(t)} for t in cleaned if t],
            }
        )
    if not senses:
        return None

    pos = element.find(f"{TEI}gramGrp/{TEI}pos")
    pron = [p.text for p in element.findall(f"{TEI}form/{TEI}pron") if p.text]
    return {
        "hw": orth.text.strip(),
        "pos": pos.text if pos is not None else None,
        "ipa": pron[:1],
        "senses": senses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="FreeDict release; defaults to the newest")
    parser.add_argument("--out", type=Path, default=settings.dictionary_seed)
    args = parser.parse_args()

    version = args.version or latest_version()
    with tempfile.TemporaryDirectory() as tmp:
        tei = download_tei(version, Path(tmp))
        count = convert(tei, args.out)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"{count} entries -> {args.out} ({size_mb:.1f} MB), FreeDict {version}")


if __name__ == "__main__":
    main()
