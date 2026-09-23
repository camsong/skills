# -*- coding: utf-8 -*-
"""Resolve a disputed name: send short clips (15-25 s) to Gemini with NO term hints, 2 samples each,
and ask for every proper noun with alternatives and confidence.

Usage:
  GEMINI_KEY=... python3 asr_probe.py <WORK_DIR> <m:ss-m:ss> [<m:ss-m:ss> ...]

A name counts as resolved only when the no-hint samples agree with each other
(and ideally with a slide on screen). Otherwise leave it out of the article
rather than guessing. Apply the verdict with merge_transcript.py --override.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini_asr import generate, mp3_b64, KEY

PROMPT = ("This is a short excerpt from a talk. Step 1: transcribe it verbatim, with no assumptions about which "
          "company or product is being discussed. Step 2: for every proper noun, product, company or tool name "
          "you hear, output: HEARD=<what you wrote> | ALTERNATIVES=<1-2 other plausible hearings> | "
          "CONFIDENCE=<high/medium/low>. Base this purely on the sounds; do not normalize to a famous name "
          "unless it is clearly spoken.")


def sec(s):
    m, x = s.split(':'); return int(m) * 60 + int(x)


def main():
    if not KEY:
        sys.exit('GEMINI_KEY not set')
    wav = os.path.join(sys.argv[1], 'audio_full.wav')
    clips = [tuple(sec(x) for x in c.split('-')) for c in sys.argv[2:]]
    jobs = [(c, k) for c in clips for k in (1, 2)]

    def run(job):
        (t0, t1), k = job
        try:
            return job, generate(mp3_b64(wav, t0, t1), PROMPT, 8000)[0]
        except RuntimeError as e:
            return job, 'FAILED %s' % e

    with ThreadPoolExecutor(4) as ex:
        for ((t0, t1), k), text in ex.map(run, jobs):
            print('\n#### %d:%02d-%d:%02d sample %d\n%s' % (t0 // 60, t0 % 60, t1 // 60, t1 % 60, k, text))


if __name__ == '__main__':
    main()
