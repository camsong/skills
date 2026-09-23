# -*- coding: utf-8 -*-
"""Transcribe WORK_DIR/audio_full.wav with gemini-3.8-flash on Vertex AI, 420 s per segment, 4 in parallel.

Usage:
  GEMINI_KEY=... [GEMINI_MODEL=gemini-3.8-flash] python3 gemini_asr.py <WORK_DIR> [--terms "A, B, C"] [--only 1,3]
Without --terms the run is "noterms". Run it twice (with and without terms),
then merge both with the captions via merge_transcript.py.

Writes WORK_DIR/asr_<terms|noterms>/seg_NNN.json. Only finishReason == STOP counts
as success; anything else is a truncated stream and is retried (max 5).
Audio leaves the machine (Google public endpoint) - fine for a public YouTube video.
"""
import base64, json, os, subprocess, sys, time, urllib.error, urllib.request, wave
from concurrent.futures import ThreadPoolExecutor

KEY = os.environ.get('GEMINI_KEY', '')
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.8-flash')  # any Vertex Gemini model that takes audio
URL = 'https://aiplatform.googleapis.com/v1/publishers/google/models/%s:streamGenerateContent' % MODEL
SEG_LEN = 420  # 7 min: verified to keep timestamps accurate; 60 s segments hallucinate

CORE = ("Transcribe this talk audio verbatim. Keep exactly what is spoken, do NOT paraphrase or translate. "
        "Label speakers as [S1], [S2]... and prefix each paragraph (roughly every 20-40 seconds, or at each "
        "topic shift) with its [mm:ss] start time, measured precisely from the start of this clip. "
        "Drop stutters and filler words (um, uh, you know) but keep every content word. "
        "Spell product names, company names, and technical terms as spoken; if a name is unclear, write your "
        "best hearing followed by [?]. If a part is inaudible, write [inaudible] - never invent content.")


def segments(total):
    cuts, t = [0.0], float(SEG_LEN)
    while t < total - 90:
        cuts.append(t); t += SEG_LEN
    cuts.append(round(total, 2))
    return list(zip(cuts[:-1], cuts[1:]))


def mp3_b64(wav, t0, t1):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t0), '-t', str(t1 - t0), '-i', wav, '-ac', '1',
                        '-ar', '16000', '-c:a', 'libmp3lame', '-b:a', '48k', '-f', 'mp3', 'pipe:1'],
                       capture_output=True, check=True)
    return base64.b64encode(p.stdout).decode()


def generate(audio_b64, prompt, max_tokens=32000):
    """Return (text, usage). Raises after 5 failed attempts."""
    body = json.dumps({"contents": {"role": "user", "parts": [
        {"inlineData": {"mimeType": "audio/mp3", "data": audio_b64}}, {"text": prompt}]},
        "generationConfig": {"maxOutputTokens": max_tokens}}).encode()
    err = ''
    for attempt in range(5):
        req = urllib.request.Request(URL, data=body, headers={'Content-Type': 'application/json',
                                                              'x-goog-api-key': KEY})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                chunks = json.loads(r.read().decode())
            chunks = chunks if isinstance(chunks, list) else [chunks]
            text = ''.join(p.get('text', '') for c in chunks for cd in c.get('candidates', [])
                           for p in cd.get('content', {}).get('parts', []) if not p.get('thought'))
            usage = next((c['usageMetadata'] for c in reversed(chunks) if c.get('usageMetadata')), {})
            finish = next((cd.get('finishReason') for c in reversed(chunks)
                           for cd in c.get('candidates', []) if cd.get('finishReason')), None)
            if finish == 'STOP':
                return text, usage
            err = 'finish=%s' % finish
        except urllib.error.HTTPError as e:
            err = 'HTTP %d' % e.code
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:
            err = str(e)[:160]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(err)


def main():
    if not KEY:
        sys.exit('GEMINI_KEY not set')
    work = sys.argv[1]
    terms = sys.argv[sys.argv.index('--terms') + 1] if '--terms' in sys.argv else ''
    only = ({int(x) for x in sys.argv[sys.argv.index('--only') + 1].split(',')}
            if '--only' in sys.argv else None)
    out = os.path.join(work, 'asr_terms' if terms else 'asr_noterms')
    os.makedirs(out, exist_ok=True)
    wav = os.path.join(work, 'audio_full.wav')
    w = wave.open(wav, 'rb'); total = w.getnframes() / w.getframerate()
    segs = segments(total)
    todo = [(i, a, b) for i, (a, b) in enumerate(segs)
            if (only is not None and i in only) or (only is None and not os.path.exists('%s/seg_%03d.json' % (out, i)))]
    print('audio %.1f min | %d segments | to run %d | terms=%s' % (total / 60, len(segs), len(todo), bool(terms)))

    def run(s):
        i, t0, t1 = s
        dur = int(t1 - t0)
        prompt = CORE + ((" Possible terms (hints only - NEVER write a term unless it is clearly spoken): "
                          + terms + ".") if terms else '') + \
            " This clip is %d seconds long, so every timestamp must be between [00:00] and [%02d:%02d]." % (
                dur, dur // 60, dur % 60)
        try:
            text, usage = generate(mp3_b64(wav, t0, t1), prompt)
        except RuntimeError as e:
            return i, 'FAIL %s' % e
        json.dump({'text': text, 'usage': usage, 't0': t0, 't1': t1, 'model': MODEL},
                  open('%s/seg_%03d.json' % (out, i), 'w'), ensure_ascii=False)
        return i, 'ok out=%s' % usage.get('candidatesTokenCount')

    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, status in ex.map(run, todo):
            print('  seg %03d %s' % (i, status), flush=True)


if __name__ == '__main__':
    main()
