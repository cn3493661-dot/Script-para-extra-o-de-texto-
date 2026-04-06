#!/usr/bin/env python3
# get_transcript_fallback.py
# Tenta várias formas de obter só o texto de um vídeo do YouTube sem baixar o vídeo.
# Uso:
# python get_transcript_fallback.py VIDEO_ID_OR_URL [--translate] [--out arquivo.txt]

import sys
import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import html
import requests
import time

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YTA = True
except Exception:
    HAS_YTA = False

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except Exception:
    HAS_TRANSLATOR = False

parser = argparse.ArgumentParser()
parser.add_argument("video", help="ID do vídeo (Oiw5z6b1zEA) ou URL")
parser.add_argument("--translate", action="store_true", help="traduz para pt (usa deep-translator)")
parser.add_argument("--out", "-o", default="transcript.txt", help="Arquivo de saída")
parser.add_argument("--sleep", type=float, default=0.3, help="Delay entre tentativas (segundos)")
args = parser.parse_args()

def extract_video_id(s):
    if "youtube.com" in s or "youtu.be" in s:
        m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", s)
        if m:
            return m.group(1)
    return s

vid = extract_video_id(args.video)
out_path = Path(args.out).resolve()
orig_path = out_path.with_name(out_path.stem + ".orig.txt")

print("Video ID:", vid)

# 1) tentar youtube_transcript_api (se disponível) - compatível com várias versões
if HAS_YTA:
    try:
        # Tentar métodos em ordem segura
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            try:
                ts_list = YouTubeTranscriptApi.list_transcripts(vid)
                # preferir pt -> en
                for lang in ["pt","pt-BR","pt-PT","en","en-US"]:
                    try:
                        transcript = ts_list.find_transcript([lang])
                        print("Achou via list_transcripts em idioma:", lang)
                        entries = transcript.fetch()
                        lines = [e["text"].strip() for e in entries if e.get("text")]
                        text = "\n".join(lines)
                        with orig_path.open("w", encoding="utf-8") as f: f.write(text)
                        print("Salvo em:", orig_path)
                        raise SystemExit(0)
                    except Exception:
                        pass
            except Exception as e:
                print("list_transcripts falhou:", e)
        # fallback para funções mais antigas
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            for lang in ["pt","pt-BR","pt-PT","en","en-US"]:
                try:
                    entries = YouTubeTranscriptApi.get_transcript(vid, languages=[lang])
                    print("Achou via get_transcript em idioma:", lang)
                    lines = [e["text"].strip() for e in entries if e.get("text")]
                    text = "\n".join(lines)
                    with orig_path.open("w", encoding="utf-8") as f: f.write(text)
                    print("Salvo em:", orig_path)
                    raise SystemExit(0)
                except Exception:
                    pass
    except Exception as e:
        print("youtube_transcript_api tentou e falhou:", e)

print("youtube_transcript_api indisponível ou não retornou. Tentando endpoints públicos do YouTube...")

# 2) tentar endpoints timedtext (XML) para vários idiomas e variantes
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})

# helpers para tentar urls
def fetch_timedtext(v, lang=None, tlang=None, kind=None, name=None, fmt="vtt"):
    # constrói parametros básicos
    base = "https://www.youtube.com/api/timedtext"
    params = {"v": v}
    if lang: params["lang"] = lang
    if tlang: params["tlang"] = tlang
    if kind: params["type"] = kind
    if name: params["name"] = name
    # prefer vtt; alguns endpoints aceitam fmt parameter (but not always)
    if fmt: params["fmt"] = fmt
    try:
        r = session.get(base, params=params, timeout=20)
        if r.status_code == 200 and r.text.strip():
            return r.text
        # às vezes a resposta vem vazia ou 204
    except Exception as e:
        pass
    return None

# tenta várias combinações de idiomas (prioriza pt, en)
attempts = []
langs_to_try = ["pt", "pt-BR", "pt-PT", "en", "en-US"]
# tentativas comuns: direct lang, translation via tlang (from en), and generic track type
for lang in langs_to_try:
    attempts.append(("lang", lang, None))
# tentar traduzir do inglês para pt caso exista traduções geradas
attempts.append(("tlang", None, "pt"))
attempts.append(("tlang", None, "pt-BR"))
# algumas vezes usar type=track e name empty funciona
attempts.append(("type_track", "en", None))
attempts.append(("type_track", "pt", None))

found_text = None
for mode, la, tl in attempts:
    time.sleep(args.sleep)
    if mode == "lang":
        print(f"Tentando timedtext?lang={la} ...")
        txt = fetch_timedtext(vid, lang=la, fmt="xml")
        if not txt:
            txt = fetch_timedtext(vid, lang=la, fmt="vtt")
    elif mode == "tlang":
        print(f"Tentando timedtext?lang=en&tlang={tl} (tradução automática)...")
        txt = fetch_timedtext(vid, lang="en", tlang=tl, fmt="xml")
        if not txt:
            txt = fetch_timedtext(vid, lang="en", tlang=tl, fmt="vtt")
    elif mode == "type_track":
        print(f"Tentando timedtext?type=track&lang={la} ...")
        txt = fetch_timedtext(vid, kind="track", lang=la, fmt="xml")
        if not txt:
            txt = fetch_timedtext(vid, kind="track", lang=la, fmt="vtt")
    else:
        txt = None

    if txt:
        # detecta se é VTT (começa com WEBVTT) ou XML (timedtext)
        if txt.strip().startswith("WEBVTT"):
            print("Recebeu VTT. Convertendo para texto...")
            # remove cabeçalho e timestamps (simples)
            lines = []
            for line in txt.splitlines():
                line = line.strip()
                # pular cabeçalho e timestamps e numeracao
                if not line or line.upper().startswith("WEBVTT") or re.match(r"^\d+:\d{2}:\d{2}\.\d{3}", line) or re.match(r"^\d+$", line):
                    continue
                # remove cues settings
                if "-->" in line:
                    continue
                lines.append(line)
            found_text = "\n".join(lines).strip()
        else:
            # tentar parsear XML timedtext
            try:
                root = ET.fromstring("<root>" + txt + "</root>")  # às vezes multiple <text> nodes
                lines = []
                for t in root.iter("text"):
                    text = (t.text or "").strip()
                    # YouTube timedtext pode usar html entities
                    text = html.unescape(text)
                    if text:
                        lines.append(text)
                found_text = "\n".join(lines).strip()
            except Exception:
                # fallback: pegar apenas tags text via regex
                matches = re.findall(r"<text[^>]*>(.*?)</text>", txt, flags=re.DOTALL)
                lines = [html.unescape(m).strip() for m in matches if m.strip()]
                found_text = "\n".join(lines).strip()

    if found_text:
        print("Legenda/transcrição encontrada via timedtext (modo:", mode, ").")
        with orig_path.open("w", encoding="utf-8") as f:
            f.write(found_text)
        print("Salvo em:", orig_path)
        break

if not found_text:
    print("Não foi possível obter transcrição via timedtext. Como fallback você pode transcrever localmente (Whisper/faster-whisper).")
    sys.exit(1)

# se pediu tradução e tradutor disponível
if args.translate:
    if not HAS_TRANSLATOR:
        print("deep-translator não instalado. Instale com: pip install deep-translator")
        sys.exit(1)
    print("Traduzindo para pt (em blocos)...")
    translator = GoogleTranslator(source="auto", target="pt")
    lines = [l for l in found_text.splitlines() if l.strip()]
    parts = []
    chunk = []
    for i, ln in enumerate(lines, 1):
        chunk.append(ln)
        if len(chunk) >= 8:
            block = "\n".join(chunk)
            try:
                parts.append(translator.translate(block))
            except Exception as e:
                # fallback item a item
                for item in chunk:
                    try:
                        parts.append(translator.translate(item))
                    except:
                        parts.append(item)
            chunk = []
            time.sleep(0.2)
    if chunk:
        block = "\n".join(chunk)
        try:
            parts.append(translator.translate(block))
        except:
            for item in chunk:
                try:
                    parts.append(translator.translate(item))
                except:
                    parts.append(item)
    translated = "\n".join(parts)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(translated)
    print("Transcrição traduzida salva em:", out_path)
else:
    # copiar original para output final
    with out_path.open("w", encoding="utf-8") as f:
        f.write(found_text)
    print("Transcrição salva em:", out_path)

print("Concluído.")
