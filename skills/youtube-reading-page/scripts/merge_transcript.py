# -*- coding: utf-8 -*-
"""Build one high-quality transcript from three sources:

  C  YouTube captions (<id>.ts.txt)   independent, sentence-level timestamps, bad at names
  N  Gemini run without term hints    clean text and punctuation, good at names
  T  Gemini run with term hints       tends to write whatever it was hinted

Text comes from N. Every stretch where the sources differ in content words
(filler-only differences are ignored) is decided by vote:

  N == T         keep N           (both Gemini runs agree; captions misheard)
  C == T         use T            (captions agree with the hinted run; N misheard)
  N == C         keep N           (T was pulled by a hint)
  all differ     keep N + "[?]"   disputed -> resolve with asr_probe.py / slides, then --override
                                  (an override also clears the "[?]" right after the match)

Timestamps come from the captions: each Gemini word inherits the time of the
caption word it aligns to, so lines keep sentence-level accuracy.

Usage:
  python3 merge_transcript.py <WORK_DIR> <CAPTIONS.ts.txt> [--override "<wrong>=><right>" ...]

Needs WORK_DIR/asr_noterms/ (required) and WORK_DIR/asr_terms/ (optional; without it
the vote is N vs C only and every content difference is marked disputed).

The filler list is English. For other languages filler-only differences are not
filtered, so expect more (harmless) decisions in corrections.md.

Writes:
  WORK_DIR/final.ts.txt      "[m:ss] text" lines - read THIS in step 2 instead of the captions
  WORK_DIR/corrections.md    every decision: time, captions, gemini, gemini+hints, chosen, rule
"""
import difflib, glob, json, os, re, sys

FILLER = set("um uh you know like so and right i guess mean kind of sort actually really just basically the a to "
             "it that this is you we in on its it's i'm okay yeah well very obviously again also or but then for "
             "with at as are was be can do have has their our your they them there these those an not no now what "
             "which how too all you're".split())


def norm(w):
    return re.sub(r'[^a-z0-9+]', '', w.lower())


def content(words):
    parts = [p for w in words for p in re.split(r'[-\u2013\u2014]', w)]
    return ''.join(n for n in (norm(p) for p in parts) if n and n not in FILLER)


def load_gemini(d):
    words = []
    for f in sorted(glob.glob(os.path.join(d, 'seg_*.json'))):
        rec = json.load(open(f))
        t0 = rec.get('t0', rec.get('meta', {}).get('t0', 0))
        text = re.sub(r'\[S\d+\]:?', '', rec['text'].replace('**', ''))
        text = re.sub(r'\[?\d{1,2}:\d{2}\]?:?', ' ', text)
        words += text.split()
    return words


def load_captions(path):
    words, times = [], []
    for ln in open(path):
        m = re.match(r'\[(\d+):(\d{2})\] (.*)', ln.strip())
        if m:
            t = int(m.group(1)) * 60 + int(m.group(2))
            for w in m.group(3).split():
                words.append(w); times.append(t)
    return words, times


def align(a, b):
    """Map every index of a to its equal-aligned index in b (or None); also return opcodes."""
    sm = difflib.SequenceMatcher(a=[norm(w) for w in a], b=[norm(w) for w in b], autojunk=False)
    m = [None] * len(a)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            m[blk.a + k] = blk.b + k
    return m, sm.get_opcodes()


def project(m, j1, j2, n_b):
    """Span of b between the nearest aligned anchors around a[j1:j2]."""
    start = next((m[k] + 1 for k in range(j1 - 1, -1, -1) if m[k] is not None), 0)
    end = next((m[k] for k in range(j2, len(m)) if m[k] is not None), n_b)
    return start, max(start, end)


def main():
    work, caps = sys.argv[1], sys.argv[2]
    overrides = [a.split('=>', 1) for i, a in enumerate(sys.argv) if i and sys.argv[i - 1] == '--override']
    N = load_gemini(os.path.join(work, 'asr_noterms'))
    T = load_gemini(os.path.join(work, 'asr_terms')) if os.path.isdir(os.path.join(work, 'asr_terms')) else None
    if not N:
        sys.exit('no Gemini output in %s/asr_noterms' % work)
    C, Ct = load_captions(caps)

    mNC, _ = align(N, C)
    mNT, _ = align(N, T) if T else (None, None)
    _, ops = align(C, N)          # hunks walked in caption order: (C span, N span)

    out, log = [], []             # out: (word, time)
    for tag, i1, i2, j1, j2 in ops:
        t = Ct[min(i1, len(Ct) - 1)] if Ct else 0
        n_w = N[j1:j2]
        if tag == 'equal':
            # captions independently agree here, so Gemini's own "[?]" doubt is resolved
            out += [(N[j].replace('[?]', ''), Ct[i1 + (j - j1)]) for j in range(j1, j2)]
            continue
        c_w = C[i1:i2]
        if content(n_w) == content(c_w) and '[?]' not in ' '.join(n_w):
            out += [(w, t) for w in n_w]          # filler / punctuation only
            continue
        if T is not None:
            s, e = project(mNT, j1, j2, len(T)) if j2 > j1 else project(mNT, j1, j1, len(T))
            t_w = T[s:e]
        else:
            t_w = None
        cn, cc = content(n_w), content(c_w)
        ct = content(t_w) if t_w is not None else None
        if '[inaudible]' in ' '.join(n_w) and cc:
            chosen, rule = c_w, 'N inaudible -> captions'
        elif ct is not None and cn == ct and '[?]' not in ' '.join(n_w):
            chosen, rule = n_w, 'N=T'
        elif ct is not None and cc == ct:
            chosen, rule = t_w, 'C=T'
        elif ct is not None and cn == cc:
            chosen, rule = [w.replace('[?]', '') for w in n_w], 'N=C'
        else:
            rule = 'DISPUTED'
            raw = ' '.join(n_w)
            txt = re.sub(r'\s+\[\?\]', '[?]', raw).strip()      # keep Gemini's own marker position
            if re.sub(r'\[\?\]', '', txt).strip(' .,;:!?'):
                if '[?]' not in txt:
                    txt = re.sub(r'([.,;:!?]*)$', r'[?]\1', txt, count=1)
                chosen = txt.split()
            else:
                chosen = ['[?' + ' '.join(c_w) + ']'] if cc else []
        out += [(w, t) for w in chosen if w]
        log.append((t, ' '.join(c_w), ' '.join(n_w), ' '.join(t_w) if t_w is not None else '-',
                    ' '.join(chosen), rule))

    out = [(w, t) for w, t in out if w]
    text_words = [w for w, _ in out]
    lines, cur, cur_t = [], [], None
    for w, t in out:
        if cur_t is None:
            cur_t = t
        cur.append(w)
        if (re.search(r'[.?!]["”)]?$', w) and len(cur) >= 12) or len(cur) >= 60:
            lines.append((cur_t, ' '.join(cur))); cur, cur_t = [], None
    if cur:
        lines.append((cur_t, ' '.join(cur)))
    for old, new in overrides:
        lines = [(t, re.sub(r'(?<!\w)%s(?:\[\?\])?(?!\w)' % re.escape(old), new, s)) for t, s in lines]

    with open(os.path.join(work, 'final.ts.txt'), 'w') as fh:
        for t, s in lines:
            fh.write('[%d:%02d] %s\n' % (t // 60, t % 60, s))
    with open(os.path.join(work, 'corrections.md'), 'w') as fh:
        fh.write('| time | captions | gemini | gemini+hints | chosen | rule |\n|---|---|---|---|---|---|\n')
        for t, c, n, tt, ch, r in log:
            fh.write('| %d:%02d | %s | %s | %s | %s | %s |\n' % (t // 60, t % 60, c, n, tt, ch, r))
        for old, new in overrides:
            fh.write('| - | | | | %s => %s | OVERRIDE |\n' % (old, new))

    from collections import Counter
    c = Counter(r for *_, r in log)
    print('final.ts.txt: %d lines, %d words | decisions: %s' % (len(lines), len(text_words), dict(c)))
    # Name variants: capitalised words that look alike (case variants, sound-alike spellings).
    # Two independent sources can agree on a wrong name, so unify these against slides / probes.
    lower_words = {norm(w) for _, s_ in lines for w in s_.split() if w[:1].islower()}
    bare = lambda w: re.sub(r"'s$", '', re.sub(r"[^\w+'-]", '', w))
    names = Counter(bare(w) for _, s_ in lines for w in s_.split()
                    if w[:1].isupper() and len(norm(bare(w))) >= 4 and norm(bare(w)) not in lower_words)
    keys = sorted(names, key=lambda k: -names[k]); seen = set()
    for k in keys:
        if k in seen:
            continue
        grp = [x for x in keys if x not in seen and x.lower() != k.lower()
               and difflib.SequenceMatcher(None, k.lower(), x.lower()).ratio() >= 0.65]
        case = [x for x in keys if x != k and x.lower() == k.lower()]
        if grp or case:
            seen.update([k] + grp + case)
            print('  NAME VARIANTS: ' + ', '.join('%s x%d' % (x, names[x]) for x in [k] + case + grp))
    for t, cc, n, tt, ch, r in log:
        if r == 'DISPUTED':
            print('  DISPUTED %d:%02d  captions="%s"  gemini="%s"  hints="%s"' % (t // 60, t % 60, cc, n, tt))


if __name__ == '__main__':
    main()
