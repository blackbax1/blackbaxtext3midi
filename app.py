import io
import streamlit as st
import mido

# 5x7 bitmap font. Each character is a list of 7 rows, each row 5 bits.
FONT = {
"A":["01110","10001","10001","11111","10001","10001","10001"],
"B":["11110","10001","10001","11110","10001","10001","11110"],
"C":["01111","10000","10000","10000","10000","10000","01111"],
"D":["11110","10001","10001","10001","10001","10001","11110"],
"E":["11111","10000","10000","11110","10000","10000","11111"],
"F":["11111","10000","10000","11110","10000","10000","10000"],
"G":["01111","10000","10000","10111","10001","10001","01111"],
"H":["10001","10001","10001","11111","10001","10001","10001"],
"I":["11111","00100","00100","00100","00100","00100","11111"],
"J":["00111","00010","00010","00010","10010","10010","01100"],
"K":["10001","10010","10100","11000","10100","10010","10001"],
"L":["10000","10000","10000","10000","10000","10000","11111"],
"M":["10001","11011","10101","10101","10001","10001","10001"],
"N":["10001","11001","10101","10011","10001","10001","10001"],
"O":["01110","10001","10001","10001","10001","10001","01110"],
"P":["11110","10001","10001","11110","10000","10000","10000"],
"Q":["01110","10001","10001","10001","10101","10010","01101"],
"R":["11110","10001","10001","11110","10100","10010","10001"],
"S":["01111","10000","10000","01110","00001","00001","11110"],
"T":["11111","00100","00100","00100","00100","00100","00100"],
"U":["10001","10001","10001","10001","10001","10001","01110"],
"V":["10001","10001","10001","10001","10001","01010","00100"],
"W":["10001","10001","10001","10101","10101","11011","10001"],
"X":["10001","10001","01010","00100","01010","10001","10001"],
"Y":["10001","10001","01010","00100","00100","00100","00100"],
"Z":["11111","00001","00010","00100","01000","10000","11111"],
"0":["01110","10001","10011","10101","11001","10001","01110"],
"1":["00100","01100","00100","00100","00100","00100","01110"],
"2":["01110","10001","00001","00010","00100","01000","11111"],
"3":["11110","00001","00001","01110","00001","00001","11110"],
"4":["00010","00110","01010","10010","11111","00010","00010"],
"5":["11111","10000","10000","11110","00001","00001","11110"],
"6":["01110","10000","10000","11110","10001","10001","01110"],
"7":["11111","00001","00010","00100","01000","01000","01000"],
"8":["01110","10001","10001","01110","10001","10001","01110"],
"9":["01110","10001","10001","01111","00001","00001","01110"],
"!":["00100","00100","00100","00100","00100","00000","00100"],
"-":["00000","00000","00000","11111","00000","00000","00000"],
"_":["00000","00000","00000","00000","00000","00000","11111"],
}


def make_midi(text, base_note=48, cell_ticks=120, gap=1, velocity=100, track_name="TEXT2MIDI"):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=track_name))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))

    x = 0
    starts = []  # (start_tick, note)
    for ch in text.upper():
        if ch == " ":
            x += 6 + gap
            continue
        glyph = FONT.get(ch, FONT["-"])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    # Row 0 is the highest pitch so the glyph is upright in piano roll.
                    note = base_note + (6 - row)
                    start = (x + col) * cell_ticks
                    starts.append((start, note))
        x += 5 + gap

    # Build every note_on / note_off as an ABSOLUTE-time event first, so that
    # all the notes belonging to the same column (a vertical stroke of a
    # letter) share the exact same tick instead of being serialized one
    # after another. This is what keeps the letters looking even/aligned.
    abs_events = []
    for start, note in starts:
        abs_events.append((start, 1, note))               # note_on  (type 1)
        abs_events.append((start + cell_ticks, 0, note))   # note_off (type 0, sorts before a note_on at the same tick)

    abs_events.sort(key=lambda e: (e[0], e[1]))

    last_tick = 0
    for tick, kind, note in abs_events:
        delta = max(0, tick - last_tick)
        if kind == 1:
            track.append(mido.Message("note_on", note=note, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=note, velocity=0, time=delta))
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    out = io.BytesIO()
    mid.save(file=out)
    return out.getvalue()


NOTES = ["C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb", "G", "G#/Ab", "A", "A#/Bb", "B"]

# Semitone offset from C for each entry in NOTES, in the same order.
NOTE_SEMITONES = {name: i for i, name in enumerate(NOTES)}


def note_to_midi(note_name, octave):
    """Turn a note name ('C', 'F#/Gb', ...) + octave into a MIDI base note,
    using the standard convention where C4 = 60."""
    return 12 * (octave + 1) + NOTE_SEMITONES[note_name]


def safe_filename(label):
    keep = []
    for c in label:
        if c.isalnum() or c in " -_#":
            keep.append(c)
    cleaned = "".join(keep).strip()
    cleaned = cleaned.replace("#", "s").replace(" ", "_")
    return f"{cleaned}.mid"


def build_preview_grid(text, gap=1, max_chars=24):
    """Lay the text out on the same 5x7 grid used by make_midi, for an
    on-screen preview that mirrors the real piano roll exactly."""
    shown = text.upper()[:max_chars]
    truncated = len(text) > max_chars
    cols = []  # cols[x] = set of "on" rows at that column
    x = 0
    for ch in shown:
        if ch == " ":
            x += 6 + gap
            continue
        glyph = FONT.get(ch, FONT["-"])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                cx = x + col
                while len(cols) <= cx:
                    cols.append(set())
                if bit == "1":
                    cols[cx].add(row)
        x += 5 + gap
    return cols, truncated


def render_piano_roll_html(text, label, gap=1):
    cols, truncated = build_preview_grid(text, gap=gap)
    n_cols = max(len(cols), 1)
    cell = 9  # px
    rows_html = []
    for row in range(7):
        zebra = "background:rgba(255,255,255,0.028);" if row % 2 == 0 else ""
        cells = []
        for x in range(n_cols):
            on = row in cols[x]
            if on:
                cells.append(
                    f'<span style="width:{cell}px;height:{cell}px;margin:1px;display:inline-block;'
                    f'background:linear-gradient(180deg,#ffcf7a,#f2a93b);border-radius:2px;'
                    f'box-shadow:0 0 6px rgba(242,169,59,.65);"></span>'
                )
            else:
                cells.append(
                    f'<span style="width:{cell}px;height:{cell}px;margin:1px;display:inline-block;'
                    f'border-radius:2px;"></span>'
                )
        rows_html.append(
            f'<div style="{zebra}display:flex;line-height:0;">' + "".join(cells) + "</div>"
        )

    trunc_note = (
        '<span style="float:right;opacity:.55;font-size:10px;">preview truncado</span>'
        if truncated else ""
    )

    return f"""
    <div style="border:1px solid #2a2a30;border-radius:14px;overflow:hidden;
                box-shadow:0 18px 40px -20px rgba(0,0,0,.7);margin:14px 0 4px 0;">
      <div style="background:linear-gradient(135deg,#f2a93b,#e08f1f);
                  color:#1a1200;padding:8px 12px;font-family:'JetBrains Mono',monospace;
                  font-weight:700;font-size:12px;letter-spacing:.04em;">
        {label}{trunc_note}
      </div>
      <div style="background:#101013;padding:14px;overflow-x:auto;">
        {''.join(rows_html)}
      </div>
    </div>
    """


st.set_page_config(page_title="Texto → MIDI", page_icon="🎹", layout="centered")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

    :root{
      --bg:#0e0e11;
      --panel:#18181c;
      --amber:#f2a93b;
      --amber-glow:rgba(242,169,59,.35);
      --teal:#3fe1c0;
      --ink:#eeece7;
      --muted:#8a8a93;
      --line:#2a2a30;
    }

    .stApp{
      background:
        radial-gradient(1100px 480px at 15% -10%, rgba(242,169,59,.10), transparent 60%),
        radial-gradient(900px 420px at 100% 0%, rgba(63,225,192,.08), transparent 55%),
        var(--bg);
      color:var(--ink);
    }

    section.main > div.block-container{
      max-width:760px;
      padding-top:3rem;
    }

    h1, h2, h3, .stMarkdown h1{
      font-family:'JetBrains Mono', monospace !important;
      letter-spacing:-.01em;
    }

    .t2m-eyebrow{
      font-family:'JetBrains Mono', monospace;
      font-size:11px;
      letter-spacing:.24em;
      text-transform:uppercase;
      color:var(--teal);
      margin-bottom:2px;
    }
    .t2m-title{
      font-family:'JetBrains Mono', monospace;
      font-weight:800;
      font-size:2.1rem;
      background:linear-gradient(135deg,#fff,#f2a93b 70%);
      -webkit-background-clip:text;
      background-clip:text;
      color:transparent;
      margin:0 0 6px 0;
      line-height:1.15;
    }
    .t2m-sub{
      font-family:'Inter', sans-serif;
      color:var(--muted);
      font-size:.95rem;
      margin-bottom:1.6rem;
    }

    label, .stMarkdown, p, span, div{
      font-family:'Inter', sans-serif;
    }

    .stTextInput > div > div > input{
      background:var(--panel) !important;
      color:var(--ink) !important;
      border:1px solid var(--line) !important;
      border-radius:10px !important;
      font-family:'JetBrains Mono', monospace !important;
      letter-spacing:.02em;
    }
    .stTextInput > div > div > input:focus{
      border-color:var(--amber) !important;
      box-shadow:0 0 0 1px var(--amber) !important;
    }

    div[data-baseweb="select"] > div{
      background:var(--panel) !important;
      border:1px solid var(--line) !important;
      border-radius:10px !important;
      color:var(--ink) !important;
    }

    .stSlider [data-baseweb="slider"] div[role="slider"]{
      background-color:var(--amber) !important;
      box-shadow:0 0 0 4px var(--amber-glow) !important;
    }
    .stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"]{
      color:var(--muted) !important;
    }

    .t2m-label{
      font-family:'JetBrains Mono', monospace;
      font-size:12px;
      letter-spacing:.06em;
      color:var(--amber);
      margin:2px 0 0 2px;
    }

    .t2m-footer{
      text-align:center;
      margin-top:2.4rem;
      font-family:'Inter', sans-serif;
      font-size:12px;
      color:var(--muted);
    }
    .t2m-footer a{
      color:var(--amber);
      text-decoration:none;
    }
    .t2m-footer a:hover{ text-decoration:underline; }

    .stButton > button{
      background:linear-gradient(135deg,var(--amber),#ffcf7a) !important;
      color:#1a1200 !important;
      border:none !important;
      border-radius:999px !important;
      font-family:'JetBrains Mono', monospace !important;
      font-weight:700 !important;
      letter-spacing:.06em;
      text-transform:uppercase;
      font-size:13px !important;
      padding:.55rem 1.5rem !important;
      box-shadow:0 10px 26px -8px var(--amber-glow) !important;
      transition:transform .12s ease;
    }
    .stButton > button:hover{ transform:translateY(-1px); }

    .stDownloadButton > button{
      background:linear-gradient(135deg,var(--teal),#8ff5e3) !important;
      color:#052620 !important;
      border:none !important;
      border-radius:999px !important;
      font-family:'JetBrains Mono', monospace !important;
      font-weight:700 !important;
      letter-spacing:.06em;
      text-transform:uppercase;
      font-size:13px !important;
      padding:.55rem 1.5rem !important;
      box-shadow:0 10px 26px -8px rgba(63,225,192,.35) !important;
    }

    .streamlit-expanderHeader{
      font-family:'JetBrains Mono', monospace !important;
      font-size:12px !important;
      letter-spacing:.08em;
      text-transform:uppercase;
      color:var(--muted) !important;
    }

    div[data-testid="stAlert"]{
      background:rgba(63,225,192,.08) !important;
      border:1px solid rgba(63,225,192,.35) !important;
      border-radius:10px !important;
      color:var(--ink) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="t2m-eyebrow">Studio tool — piano roll art</div>', unsafe_allow_html=True)
st.markdown('<div class="t2m-title">Texto → MIDI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="t2m-sub">Escribe texto y genera un MIDI que dibuja las letras en el piano roll.</div>',
    unsafe_allow_html=True,
)

text = st.text_input("Texto", value="Blackbax", max_chars=80)

k1, k2 = st.columns(2)
with k1:
    root = st.selectbox("Nota", NOTES, index=0)
with k2:
    scale = st.selectbox("Escala", ["Minor", "Major"], index=0)

label = f"{root} {scale.lower()} - {text}"
st.markdown(f'<div class="t2m-label">{label}</div>', unsafe_allow_html=True)

with st.expander("Ajustes avanzados"):
    c1, c2, c3 = st.columns(3)
    with c1:
        octave = st.slider("Octava", 0, 6, 3, help="Sube o baja la nota elegida arriba una o más octavas.")
    with c2:
        cell_ticks = st.select_slider("Tamaño", options=[60, 90, 120, 180, 240], value=120)
    with c3:
        gap = st.slider("Espacio", 0, 4, 1)

base_note = note_to_midi(root, octave)

st.markdown(render_piano_roll_html(text, label, gap=gap), unsafe_allow_html=True)

if st.button("Generar MIDI", type="primary"):
    data = make_midi(text, base_note, cell_ticks, gap, track_name=label)
    st.success("MIDI generado.")
    st.download_button("⬇️ Descargar MIDI", data=data, file_name=safe_filename(label), mime="audio/midi")

st.markdown(
    '<div class="t2m-footer">Creado por '
    '<a href="https://www.instagram.com/blackbaxbeats/" target="_blank">@blackbaxbeats</a>'
    '</div>',
    unsafe_allow_html=True,
)
