import base64
import io
import json
import streamlit as st
import streamlit.components.v1 as components
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
"#":["01010","01010","11111","01010","11111","01010","01010"],
}

# --- Style controls: weight (stroke thickness), density (row spacing),
# width (column spacing). "Tiny" / "Dense" / "Narrow" reproduce the
# original 1px-per-cell look exactly, so the default look never changes.
#
# "weight" used to just sprinkle a couple of extra pixels around each dot
# (a thin +1px outline) -- that's why even "Bold" still looked small next
# to a tool like ableset's MIDI Typer. Now it's a real integer SCALE:
# every "on" pixel of the 5x7 font is blown up into an NxN solid block of
# grid cells (both in pitch/row and in time/col), so Bold letters end up
# both taller (more semitones tall in the piano roll) and thicker-stroked
# -- not just outlined.
WEIGHT_SCALE = {"Tiny": 1, "Regular": 2, "Bold": 4}
DENSITY_ROW_STEP = {"Dense": 1, "Loose": 2}
WIDTH_COL_STEP = {"Narrow": 1, "Medium": 2, "Wide": 3, "Very Wide": 4}


def _layout_cells_uncached(text, weight="Tiny", density="Dense", width="Narrow", gap=1):
    """Lay text out on a grid of 'on' (col, row) cells, applying the
    weight/density/width style controls. Shared by make_midi (for the
    real MIDI) and the on-screen preview, so they always match exactly."""
    row_step = DENSITY_ROW_STEP.get(density, 1)
    col_step = WIDTH_COL_STEP.get(width, 1)
    scale = WEIGHT_SCALE.get(weight, 1)
    scaled_gap = gap * scale

    cells = set()
    x = 0
    max_row = 0
    space_width = 6 * col_step * scale
    for ch in text.upper():
        if ch == " ":
            x += space_width + scaled_gap
            continue
        glyph = FONT.get(ch, FONT["-"])
        glyph_cells = set()
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                sr, sc = row * row_step * scale, col * col_step * scale
                for dr in range(scale):
                    for dc in range(scale):
                        glyph_cells.add((sr + dr, sc + dc))
        glyph_w = (max(c for _, c in glyph_cells) + 1) if glyph_cells else 5 * col_step * scale
        for sr, sc in glyph_cells:
            cells.add((x + sc, sr))
            max_row = max(max_row, sr)
        x += glyph_w + scaled_gap

    total_cols = max(x - scaled_gap, 0)
    return cells, total_cols, max_row


# Cached wrapper: layout_cells is a pure function of its arguments, and it's
# called on every single rerun (every style-button click re-renders the
# preview). Caching it means switching between a style you've already seen
# in this session is instant instead of recomputing the whole glyph grid.
@st.cache_data(show_spinner=False)
def layout_cells(text, weight="Tiny", density="Dense", width="Narrow", gap=1):
    return _layout_cells_uncached(text, weight=weight, density=density, width=width, gap=gap)


def make_midi(text, base_note=48, cell_ticks=120, gap=1, velocity=100, track_name="TEXT2MIDI", lead_in_cells=4,
              weight="Tiny", density="Dense", width="Narrow"):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=track_name))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))

    cells, total_cols, max_row = layout_cells(text, weight=weight, density=density, width=width, gap=gap)

    # Group "on" cells by row (= by MIDI note), then merge horizontally
    # consecutive columns into single runs. Emitting one note per cell used
    # to retrigger the SAME pitch at every column boundary inside a stroke
    # (note_off + note_on back-to-back), which is exactly what shows up in
    # the piano roll as a row of little separate squares instead of one
    # solid bar. Merging each run into a single long note is what makes a
    # horizontal stroke render as one continuous block, matching the
    # reference tool.
    cols_by_row = {}
    for col, row in cells:
        cols_by_row.setdefault(row, set()).add(col)

    runs = []  # (start_col, end_col_inclusive, note)
    for row, cols in cols_by_row.items():
        # Row 0 is the highest pitch so the glyph is upright in piano roll.
        note = base_note + (max_row - row)
        cols_sorted = sorted(cols)
        run_start = prev = cols_sorted[0]
        for c in cols_sorted[1:]:
            if c == prev + 1:
                prev = c
                continue
            runs.append((run_start, prev, note))
            run_start = prev = c
        runs.append((run_start, prev, note))

    # Build every note_on / note_off as an ABSOLUTE-time event first, so that
    # all the notes belonging to the same column (a vertical stroke of a
    # letter) share the exact same tick instead of being serialized one
    # after another. This is what keeps the letters looking even/aligned.
    abs_events = []
    for start_col, end_col, note in runs:
        start = (lead_in_cells + start_col) * cell_ticks
        end = (lead_in_cells + end_col + 1) * cell_ticks
        abs_events.append((start, 1, note))   # note_on  (type 1)
        abs_events.append((end, 0, note))     # note_off (type 0, sorts before a note_on at the same tick)

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


NOTES = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]

# Semitone offset from C for each entry in NOTES.
NOTE_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


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


@st.cache_data(show_spinner=False)
def build_preview_grid(text, weight="Tiny", density="Dense", width="Narrow", gap=1, max_chars=40):
    """Lay the text out on the same grid used by make_midi, for an
    on-screen preview that mirrors the real piano roll exactly."""
    shown = text.upper()[:max_chars]
    truncated = len(text) > max_chars
    cell_set, total_cols, max_row = layout_cells(shown, weight=weight, density=density, width=width, gap=gap)
    cols = [set() for _ in range(int(total_cols) + 1)]  # cols[x] = set of "on" rows at that column
    for x, row in cell_set:
        while len(cols) <= x:
            cols.append(set())
        cols[x].add(row)
    return cols, truncated, max_row


@st.cache_data(show_spinner=False)
def render_piano_roll_html(text, label, weight="Tiny", density="Dense", width="Narrow", gap=1):
    cols, truncated, max_row = build_preview_grid(text, weight=weight, density=density, width=width, gap=gap)
    n_cols = max(len(cols), 1)
    n_rows = max_row + 1
    # Shrink the cell a little when Wide/Bold/Loose make the grid much bigger,
    # so the preview keeps fitting nicely instead of overflowing.
    cell = max(4, min(9, int(620 / n_cols)))  # px
    rows_html = []
    for row in range(n_rows):
        zebra = "background:rgba(255,255,255,0.032);" if row % 2 == 0 else ""
        cells = []
        for x in range(n_cols):
            on = row in cols[x]
            if on:
                cells.append(
                    f'<span style="width:{cell}px;height:{cell}px;margin:1px;display:inline-block;'
                    f'background:linear-gradient(160deg,#c9a3ff,#8b5cf6 45%,#ff4fa3 100%);border-radius:3px;'
                    f'box-shadow:0 0 7px rgba(139,92,246,.75);"></span>'
                )
            else:
                cells.append(
                    f'<span style="width:{cell}px;height:{cell}px;margin:1px;display:inline-block;'
                    f'background:rgba(255,255,255,.025);border-radius:3px;"></span>'
                )
        rows_html.append(
            f'<div style="{zebra}display:flex;line-height:0;">' + "".join(cells) + "</div>"
        )

    trunc_note = (
        '<span style="float:right;opacity:.6;font-size:10px;">preview truncado</span>'
        if truncated else ""
    )

    return f"""
    <div style="border:1px solid rgba(255,255,255,.09);border-radius:16px;overflow:hidden;
                box-shadow:0 22px 46px -22px rgba(139,92,246,.5);margin:8px 0 0 0;">
      <div style="background:linear-gradient(100deg,#8b5cf6,#ff4fa3 65%,#2be6c4 130%);
                  color:#0a0710;padding:7px 12px;font-family:'JetBrains Mono',monospace;
                  font-weight:700;font-size:12px;letter-spacing:.1em;text-transform:uppercase;">
        {label}{trunc_note}
      </div>
      <div style="position:relative;background:#0a0a0d;padding:10px;overflow-x:auto;">
        <div style="position:absolute;top:0;left:0;height:100%;width:26px;pointer-events:none;
                    background:linear-gradient(90deg,rgba(43,230,196,0),rgba(43,230,196,.16),rgba(43,230,196,0));
                    animation:t2m-scan 5.5s linear infinite;"></div>
        {''.join(rows_html)}
      </div>
    </div>
    """


st.set_page_config(page_title="Texto → MIDI", page_icon="🎹", layout="centered")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    :root{
      --bg:#07070a;
      --panel:rgba(255,255,255,.045);
      --panel-solid:#131318;
      --violet:#8b5cf6;
      --magenta:#ff4fa3;
      --cyan:#2be6c4;
      --glow:rgba(139,92,246,.35);
      --ink:#f3f1fb;
      --muted:#928fa3;
      --line:rgba(255,255,255,.09);
    }

    @keyframes t2m-drift{
      0%{ background-position:0% 50%; }
      50%{ background-position:100% 50%; }
      100%{ background-position:0% 50%; }
    }
    @keyframes t2m-scan{
      0%{ transform:translateX(-8%); }
      100%{ transform:translateX(108%); }
    }

    .stApp{
      background:
        radial-gradient(900px 460px at 12% -8%, rgba(139,92,246,.22), transparent 60%),
        radial-gradient(760px 420px at 100% 0%, rgba(43,230,196,.14), transparent 55%),
        radial-gradient(700px 500px at 90% 90%, rgba(255,79,163,.12), transparent 60%),
        var(--bg);
      color:var(--ink);
    }

    section.main > div.block-container{
      max-width:760px;
      padding-top:1.3rem;
      padding-bottom:1.5rem;
    }

    /* Streamlit puts a fixed ~1rem gap between every top-level widget.
       Tightening it (still generous enough to read) is what actually lets
       the whole page — including the download button at the bottom —
       fit on screen without scrolling past everything first. */
    div[data-testid="stVerticalBlock"]{
      gap:.6rem !important;
    }

    h1, h2, h3, .stMarkdown h1{
      font-family:'Space Grotesk', sans-serif !important;
      letter-spacing:-.01em;
    }

    .t2m-eyebrow{
      font-family:'JetBrains Mono', monospace;
      font-size:10px;
      letter-spacing:.28em;
      text-transform:uppercase;
      color:var(--cyan);
      margin-bottom:4px;
      display:flex;
      align-items:center;
      gap:8px;
    }
    .t2m-eyebrow::before{
      content:"";
      width:6px;height:6px;border-radius:50%;
      background:var(--magenta);
      box-shadow:0 0 10px 2px var(--magenta);
    }
    .t2m-title{
      font-family:'Space Grotesk', sans-serif;
      font-weight:800;
      font-size:1.9rem;
      background:linear-gradient(100deg,#fff 0%,var(--violet) 35%,var(--magenta) 60%,var(--cyan) 100%);
      background-size:220% 220%;
      -webkit-background-clip:text;
      background-clip:text;
      color:transparent;
      margin:0 0 4px 0;
      line-height:1.08;
      animation:t2m-drift 9s ease-in-out infinite;
    }
    .t2m-sub{
      font-family:'Inter', sans-serif;
      color:var(--muted);
      font-size:.88rem;
      margin-bottom:.6rem;
    }

    label, .stMarkdown, p, span, div{
      font-family:'Inter', sans-serif;
    }

    .stTextInput > div > div > input{
      background:var(--panel) !important;
      backdrop-filter:blur(10px);
      color:var(--ink) !important;
      border:1px solid var(--line) !important;
      border-radius:12px !important;
      font-family:'JetBrains Mono', monospace !important;
      letter-spacing:.02em;
    }
    .stTextInput > div > div > input:focus{
      border-color:var(--violet) !important;
      box-shadow:0 0 0 3px var(--glow) !important;
    }

    div[data-baseweb="select"] > div{
      background:var(--panel) !important;
      backdrop-filter:blur(10px);
      border:1px solid var(--line) !important;
      border-radius:12px !important;
      color:var(--ink) !important;
    }

    .stSlider [data-baseweb="slider"] div[role="slider"]{
      background:linear-gradient(135deg,var(--violet),var(--magenta)) !important;
      box-shadow:0 0 0 5px var(--glow) !important;
    }
    .stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"]{
      color:var(--muted) !important;
    }

    .t2m-label{
      font-family:'JetBrains Mono', monospace;
      font-size:12px;
      letter-spacing:.16em;
      text-transform:uppercase;
      background:linear-gradient(90deg,var(--violet),var(--cyan));
      -webkit-background-clip:text;
      background-clip:text;
      color:transparent;
      margin:4px 0 0 2px;
      font-weight:600;
    }

    .t2m-footer{
      text-align:center;
      margin-top:1rem;
      font-family:'Inter', sans-serif;
      font-size:12px;
      color:var(--muted);
    }
    .t2m-footer a{
      color:var(--cyan);
      text-decoration:none;
      font-weight:600;
    }
    .t2m-footer a:hover{ text-decoration:underline; }

    .stButton > button{
      background:linear-gradient(135deg,var(--violet),var(--magenta)) !important;
      color:#fff !important;
      border:none !important;
      border-radius:999px !important;
      font-family:'JetBrains Mono', monospace !important;
      font-weight:700 !important;
      letter-spacing:.08em;
      text-transform:uppercase;
      font-size:13px !important;
      padding:.5rem 1.4rem !important;
      box-shadow:0 12px 30px -10px var(--glow) !important;
      transition:transform .15s ease, box-shadow .15s ease;
    }
    .stButton > button:hover{
      transform:translateY(-2px);
      box-shadow:0 16px 34px -8px rgba(255,79,163,.45) !important;
    }

    .stDownloadButton > button{
      background:linear-gradient(135deg,var(--cyan),#7cf5db) !important;
      color:#053228 !important;
      border:none !important;
      border-radius:999px !important;
      font-family:'JetBrains Mono', monospace !important;
      font-weight:700 !important;
      letter-spacing:.08em;
      text-transform:uppercase;
      font-size:13px !important;
      padding:.5rem 1.4rem !important;
      box-shadow:0 12px 30px -10px rgba(43,230,196,.45) !important;
      transition:transform .15s ease;
    }
    .stDownloadButton > button:hover{ transform:translateY(-2px); }

    .streamlit-expanderHeader{
      font-family:'JetBrains Mono', monospace !important;
      font-size:12px !important;
      letter-spacing:.1em;
      text-transform:uppercase;
      color:var(--muted) !important;
    }
    div[data-testid="stExpander"]{
      background:var(--panel) !important;
      backdrop-filter:blur(10px);
      border:1px solid var(--line) !important;
      border-radius:14px !important;
    }

    div[data-testid="stAlert"]{
      background:rgba(43,230,196,.08) !important;
      border:1px solid rgba(43,230,196,.35) !important;
      border-radius:12px !important;
      color:var(--ink) !important;
    }

    @media (prefers-reduced-motion: reduce){
      .t2m-title{ animation:none; }
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

# --- Client-side style widget -------------------------------------------
# Grosor + Densidad + el preview en vivo viven ahora en un solo componente
# HTML/JS (un iframe) que corre 100% en el navegador: el layout de letras,
# el dibujo del grid y el resaltado de los botones no tocan el servidor en
# absoluto al cambiar de estilo, así que no hay viaje de ida y vuelta que
# esperar (eso es lo que causaba el retraso de varios segundos en
# Streamlit Cloud). La única llamada real al servidor sigue siendo, como
# antes, el botón "Generar MIDI" — porque ahí sí se necesita Python/mido
# para construir el archivo.
#
# Cómo se entera Python de qué estilo eligió el usuario en el navegador:
# el JS del widget guarda la elección en la URL (query params t2mw/t2md)
# con history.replaceState — que NO dispara un rerun por sí solo. Cuando
# el usuario finalmente hace clic en "Generar MIDI" (un st.button normal,
# eso sí dispara un rerun), Python lee esos query params ya actualizados
# desde st.query_params y los usa para generar el MIDI real.
_STYLE_WIDGET_TEMPLATE = r"""
<div id="t2m-root">
  <style>
    :root{
      --violet:#8b5cf6; --magenta:#ff4fa3; --cyan:#2be6c4;
      --glow:rgba(139,92,246,.35); --ink:#f3f1fb; --muted:#928fa3;
      --line:rgba(255,255,255,.09); --panel:rgba(255,255,255,.045);
    }
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
    html, body{ background:transparent; margin:0; padding:0; }
    #t2m-root{ font-family:'JetBrains Mono', monospace; color:var(--ink); }
    .t2m-ctrl-label{
      font-size:12px; font-weight:600; letter-spacing:.13em; text-transform:uppercase;
      text-align:center; width:100%; display:block;
      background:linear-gradient(90deg,var(--violet),var(--cyan));
      -webkit-background-clip:text; background-clip:text; color:transparent;
      margin:.3rem 0 .3rem 0;
    }
    .t2m-segbar{
      display:flex; width:fit-content; max-width:100%; margin:0 auto 14px auto;
      border:1px solid var(--line); border-radius:999px; overflow:hidden;
      background:var(--panel); backdrop-filter:blur(10px);
    }
    .t2m-segbar button{
      font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:.02em;
      padding:.5rem .95rem; white-space:nowrap; background:transparent; border:none;
      border-left:1px solid var(--line); color:var(--muted); cursor:pointer;
      transition:background .1s ease, color .1s ease;
    }
    .t2m-segbar button:first-child{ border-left:none; }
    .t2m-segbar button:hover{ color:var(--ink); }
    .t2m-segbar button:active{ background:rgba(139,92,246,.35); color:var(--ink); }
    .t2m-segbar button.active{
      background:linear-gradient(135deg,rgba(139,92,246,.55),rgba(255,79,163,.4));
      color:var(--ink); font-weight:600;
    }
    @media (max-width:480px){
      .t2m-segbar button{ font-size:10px; padding:.4rem .55rem; }
    }
    .t2m-preview-card{
      border:1px solid rgba(255,255,255,.09); border-radius:16px; overflow:hidden;
      box-shadow:0 22px 46px -22px rgba(139,92,246,.5); margin:8px 0 0 0;
    }
    .t2m-preview-header{
      background:linear-gradient(100deg,#8b5cf6,#ff4fa3 65%,#2be6c4 130%);
      color:#0a0710; padding:7px 12px; font-weight:700; font-size:12px;
      letter-spacing:.1em; text-transform:uppercase;
    }
    .t2m-preview-body{ position:relative; background:#0a0a0d; padding:10px; overflow-x:auto; }
    .t2m-row{ display:flex; line-height:0; }
    .t2m-cell{ margin:1px; display:inline-block; border-radius:3px; }
    .t2m-cell.on{
      background:linear-gradient(160deg,#c9a3ff,#8b5cf6 45%,#ff4fa3 100%);
      box-shadow:0 0 7px rgba(139,92,246,.75);
    }
    .t2m-cell.off{ background:rgba(255,255,255,.025); }
    .t2m-trunc{ float:right; opacity:.6; font-size:10px; }
  </style>

  <div class="t2m-ctrl-label">Grosor</div>
  <div class="t2m-segbar" id="t2m-weight-bar"></div>
  <div class="t2m-ctrl-label">Densidad</div>
  <div class="t2m-segbar" id="t2m-density-bar"></div>
  <div id="t2m-preview"></div>
</div>

<script>
(function(){
  const FONT = __FONT_JSON__;
  const WEIGHT_SCALE = {"Tiny": 1, "Regular": 2, "Bold": 4};
  const DENSITY_ROW_STEP = {"Dense": 1, "Loose": 2};
  const WEIGHT_OPTIONS = [["Tiny","Fino"], ["Regular","Regular"], ["Bold","Grueso"]];
  const DENSITY_OPTIONS = [["Loose","Suelto"], ["Dense","Denso"]];

  const label = __LABEL_JSON__;
  const gap = __GAP__;
  let weight = __WEIGHT_JSON__;
  let density = __DENSITY_JSON__;

  function layoutCells(text, density, gap){
    // Base (unscaled) layout: one grid cell per font pixel, spaced only by
    // density (row gaps). This intentionally does NOT explode into
    // NxN blocks per weight — that's what made the "Bold" preview render
    // ~14,000 tiny glowing DOM cells and effectively freeze/blank out.
    // Weight instead just scales how BIG each of these cells is drawn (see
    // renderPreview), so the preview stays cheap regardless of weight
    // while still looking chunkier for Bold. The real MIDI file still uses
    // true NxN note-blocks (that's server-side Python, a different code
    // path, and it merges runs into long notes so it never explodes).
    const rowStep = DENSITY_ROW_STEP[density] || 1;
    const cells = new Set();
    let x = 0, maxRow = 0;
    const spaceWidth = 6;
    const upper = text.toUpperCase();
    for (const ch of upper) {
      if (ch === " ") { x += spaceWidth + gap; continue; }
      const glyph = FONT[ch] || FONT["-"];
      const glyphCells = new Set();
      for (let row = 0; row < glyph.length; row++) {
        const bits = glyph[row];
        for (let col = 0; col < bits.length; col++) {
          if (bits[col] !== "1") continue;
          glyphCells.add((row * rowStep) + "," + col);
        }
      }
      let glyphW = 5;
      if (glyphCells.size > 0) {
        let maxC = -Infinity;
        glyphCells.forEach(function(key){
          const c = parseInt(key.split(",")[1], 10);
          if (c > maxC) maxC = c;
        });
        glyphW = maxC + 1;
      }
      glyphCells.forEach(function(key){
        const parts = key.split(",");
        const sr = parseInt(parts[0], 10), sc = parseInt(parts[1], 10);
        cells.add((x+sc) + "," + sr);
        if (sr > maxRow) maxRow = sr;
      });
      x += glyphW + gap;
    }
    return {cells: cells, totalCols: Math.max(x - gap, 0), maxRow: maxRow};
  }

  function buildGrid(text, density, gap){
    const shown = text.toUpperCase().slice(0, 40);
    const truncated = text.length > 40;
    const lay = layoutCells(shown, density, gap);
    const nCols = Math.floor(lay.totalCols) + 1;
    const cols = [];
    for (let i = 0; i < nCols; i++) cols.push(new Set());
    lay.cells.forEach(function(key){
      const parts = key.split(",");
      const cx = parseInt(parts[0], 10), row = parseInt(parts[1], 10);
      while (cols.length <= cx) cols.push(new Set());
      cols[cx].add(row);
    });
    return {cols: cols, truncated: truncated, maxRow: lay.maxRow};
  }

  function renderPreview(){
    const grid = buildGrid(label, density, gap);
    const scale = WEIGHT_SCALE[weight] || 1;
    const nCols = Math.max(grid.cols.length, 1);
    const nRows = grid.maxRow + 1;
    // Size cells to fit ~620px at BASE resolution, then blow that size up
    // by the weight scale so Bold reads as chunkier squares -- without
    // adding a single extra DOM node (see layoutCells for why that matters).
    const baseCell = Math.max(3, Math.min(9, Math.floor(620 / nCols)));
    const cell = baseCell * scale;
    let rowsHtml = "";
    for (let row = 0; row < nRows; row++) {
      const zebra = (row % 2 === 0) ? "background:rgba(255,255,255,0.032);" : "";
      let rowHtml = "";
      for (let x = 0; x < nCols; x++) {
        const on = grid.cols[x] && grid.cols[x].has(row);
        rowHtml += '<span class="t2m-cell ' + (on ? 'on' : 'off') +
          '" style="width:' + cell + 'px;height:' + cell + 'px;"></span>';
      }
      rowsHtml += '<div class="t2m-row" style="' + zebra + '">' + rowHtml + '</div>';
    }
    const truncNote = grid.truncated ? '<span class="t2m-trunc">preview truncado</span>' : '';
    document.getElementById('t2m-preview').innerHTML =
      '<div class="t2m-preview-card">' +
      '<div class="t2m-preview-header">' + label + truncNote + '</div>' +
      '<div class="t2m-preview-body">' + rowsHtml + '</div>' +
      '</div>';
    resizeFrame();
  }

  function syncToParent(){
    try {
      const url = new URL(window.parent.location.href);
      url.searchParams.set('t2mw', weight);
      url.searchParams.set('t2md', density);
      window.parent.history.replaceState(null, '', url);
    } catch (e) { /* cross-origin fallback: preview still updates locally */ }
  }

  function renderBar(containerId, options, current, onPick){
    const el = document.getElementById(containerId);
    el.innerHTML = "";
    options.forEach(function(opt){
      const internal = opt[0], lbl = opt[1];
      const btn = document.createElement('button');
      btn.textContent = lbl;
      if (internal === current) btn.classList.add('active');
      btn.addEventListener('click', function(){ onPick(internal); });
      el.appendChild(btn);
    });
  }

  function redrawBars(){
    renderBar('t2m-weight-bar', WEIGHT_OPTIONS, weight, function(v){
      weight = v; syncToParent(); redrawBars(); renderPreview();
    });
    renderBar('t2m-density-bar', DENSITY_OPTIONS, density, function(v){
      density = v; syncToParent(); redrawBars(); renderPreview();
    });
  }

  function resizeFrame(){
    try {
      const h = document.getElementById('t2m-root').scrollHeight + 16;
      window.parent.postMessage({type: "streamlit:setFrameHeight", height: h}, "*");
    } catch (e) { /* best effort */ }
  }

  redrawBars();
  renderPreview();
  window.addEventListener('resize', resizeFrame);
  // The height guess Python passes to components.html() is only a first
  // paint fallback — these extra calls correct it to the *real* content
  // height right after load (fonts/layout can still shift a few px after
  // the first paint), which is what closes the big empty gap before the
  // "Generar MIDI" button.
  window.addEventListener('load', resizeFrame);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(resizeFrame);
  }
  setTimeout(resizeFrame, 60);
  setTimeout(resizeFrame, 300);
})();
</script>
"""


def render_style_widget(label, weight, density, gap):
    html = (
        _STYLE_WIDGET_TEMPLATE
        .replace("__FONT_JSON__", json.dumps(FONT))
        .replace("__LABEL_JSON__", json.dumps(label))
        .replace("__GAP__", json.dumps(gap))
        .replace("__WEIGHT_JSON__", json.dumps(weight))
        .replace("__DENSITY_JSON__", json.dumps(density))
    )
    # height is just the first-paint guess — the JS above corrects it to
    # the real content height a moment later via postMessage, so this only
    # needs to be "close enough" to avoid a flash of wrong size.
    components.html(html, height=380, scrolling=False)


# st.fragment (st.experimental_fragment on older Streamlit) lets a block
# re-run and re-render on its own, without re-running the rest of the
# script above it (title, text input, note/scale selects...). This still
# matters for the "Ajustes avanzados" sliders and the "Generar MIDI"
# button below, which do need a real server round-trip.
_fragment_decorator = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
if _fragment_decorator is None:
    def _fragment_decorator(func):
        return func


@_fragment_decorator
def style_and_preview_section(text, root, scale, label):
    # "Ajustes avanzados" ya no es un desplegable — los 4 controles quedan
    # siempre visibles, en una sola fila.
    st.markdown(
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:12px;'
        'letter-spacing:.1em;text-transform:uppercase;color:var(--muted);'
        'margin:.2rem 0 .3rem 0;">Ajustes avanzados</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        octave = st.slider("Octava", 0, 6, 3, help="Sube o baja la nota elegida arriba una o más octavas.")
    with c2:
        # ableset's MIDI Typer holds each column for a full quarter note
        # (1 beat) — that's the real reason its letters read as "big" even
        # before you touch weight/density: each cell simply lasts much
        # longer in musical time. Our ticks_per_beat is 480, so 480 ticks =
        # 1 beat, matching that. Default is now 480 (1 beat/cell) instead
        # of the old 120 (a quarter of a beat) so the out-of-the-box result
        # is already close to ableset's; 960 is offered for an even wider,
        # slower-reading result.
        cell_ticks = st.select_slider(
            "Tamaño", options=[60, 120, 240, 480, 960], value=480,
            help="Cuánto dura (en tiempo musical) cada columna. 480 = 1 negra por celda, igual que ableset's MIDI Typer.",
        )
    with c3:
        gap = st.slider("Espacio", 0, 4, 1)
    with c4:
        lead_in = st.slider("Inicio", 0, 16, 4, help="Corre el dibujo más adelante en la línea de tiempo, para que no quede pegado al compás 1.")

    base_note = note_to_midi(root, octave)

    # Pick up the weight/density the JS widget last wrote to the URL. Falls
    # back to session_state (last known good value) and finally to the
    # original defaults, so a first-ever load or a sync hiccup never
    # crashes — it just uses "Fino"/"Denso" like before.
    qp = st.query_params
    qs_weight = qp.get("t2mw")
    qs_density = qp.get("t2md")
    if qs_weight in WEIGHT_SCALE:
        st.session_state["grosor"] = qs_weight
    if qs_density in DENSITY_ROW_STEP:
        st.session_state["densidad"] = qs_density
    ctrl_weight = st.session_state.get("grosor", "Tiny")
    ctrl_density = st.session_state.get("densidad", "Dense")
    ctrl_width = "Narrow"  # "Ancho" selector removed; width stays fixed.

    render_style_widget(label, ctrl_weight, ctrl_density, gap)

    if st.button("Generar MIDI", type="primary"):
        data = make_midi(
            label, base_note, cell_ticks, gap, track_name=label, lead_in_cells=lead_in,
            weight=ctrl_weight, density=ctrl_density, width=ctrl_width,
        )
        st.success("MIDI generado.")

        # Auto-download: trigger the save immediately instead of making the
        # user click a second "Descargar" button. Streamlit has no native
        # "download without a click" primitive, so this injects a tiny
        # invisible component that builds the file as a data: URI and
        # .click()s a hidden <a download> once on load — the standard,
        # widely-supported way to force a save from JS. The visible
        # download button stays right below as a manual fallback, in case
        # a browser's popup/download blocker stops the automatic one.
        b64 = base64.b64encode(data).decode("ascii")
        fname = safe_filename(label)
        components.html(
            f"""
            <a id="t2m-dl" href="data:audio/midi;base64,{b64}" download="{fname}" style="display:none;"></a>
            <script>document.getElementById('t2m-dl').click();</script>
            """,
            height=0,
        )

        st.download_button("⬇️ Descargar MIDI de nuevo", data=data, file_name=fname, mime="audio/midi")


style_and_preview_section(text, root, scale, label)

st.markdown(
    '<div class="t2m-footer">Creado por '
    '<a href="https://www.instagram.com/blackbaxbeats/" target="_blank">@blackbaxbeats</a>'
    '</div>',
    unsafe_allow_html=True,
)
