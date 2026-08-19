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
"#":["01010","01010","11111","01010","11111","01010","01010"],
}

# --- Style controls: weight (stroke thickness), density (row spacing),
# width (column spacing). "Tiny" / "Dense" / "Narrow" reproduce the
# original 1px-per-cell look exactly, so the default look never changes.
WEIGHT_OFFSETS = {
    "Tiny": [],
    "Regular": [(0, 1), (1, 0)],
    "Bold": [(0, 1), (1, 0), (1, 1)],
}
DENSITY_ROW_STEP = {"Dense": 1, "Loose": 2}
WIDTH_COL_STEP = {"Narrow": 1, "Medium": 2, "Wide": 3, "Very Wide": 4}


def layout_cells(text, weight="Tiny", density="Dense", width="Narrow", gap=1):
    """Lay text out on a grid of 'on' (col, row) cells, applying the
    weight/density/width style controls. Shared by make_midi (for the
    real MIDI) and the on-screen preview, so they always match exactly."""
    row_step = DENSITY_ROW_STEP.get(density, 1)
    col_step = WIDTH_COL_STEP.get(width, 1)
    dilate = WEIGHT_OFFSETS.get(weight, [])

    cells = set()
    x = 0
    max_row = 0
    space_width = 6 * col_step
    for ch in text.upper():
        if ch == " ":
            x += space_width + gap
            continue
        glyph = FONT.get(ch, FONT["-"])
        glyph_cells = set()
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                sr, sc = row * row_step, col * col_step
                glyph_cells.add((sr, sc))
                for dr, dc in dilate:
                    glyph_cells.add((sr + dr, sc + dc))
        glyph_w = (max(c for _, c in glyph_cells) + 1) if glyph_cells else 5 * col_step
        for sr, sc in glyph_cells:
            cells.add((x + sc, sr))
            max_row = max(max_row, sr)
        x += glyph_w + gap

    total_cols = max(x - gap, 0)
    return cells, total_cols, max_row


def make_midi(text, base_note=48, cell_ticks=120, gap=1, velocity=100, track_name="TEXT2MIDI", lead_in_cells=4,
              weight="Tiny", density="Dense", width="Narrow"):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=track_name))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))

    cells, total_cols, max_row = layout_cells(text, weight=weight, density=density, width=width, gap=gap)
    starts = []  # (start_tick, note)
    for col, row in cells:
        # Row 0 is the highest pitch so the glyph is upright in piano roll.
        note = base_note + (max_row - row)
        start = (lead_in_cells + col) * cell_ticks
        starts.append((start, note))

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
                box-shadow:0 22px 46px -22px rgba(139,92,246,.5);margin:16px 0 4px 0;">
      <div style="background:linear-gradient(100deg,#8b5cf6,#ff4fa3 65%,#2be6c4 130%);
                  color:#0a0710;padding:9px 13px;font-family:'JetBrains Mono',monospace;
                  font-weight:700;font-size:12px;letter-spacing:.1em;text-transform:uppercase;">
        {label}{trunc_note}
      </div>
      <div style="position:relative;background:#0a0a0d;padding:14px;overflow-x:auto;">
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
      padding-top:3rem;
    }

    h1, h2, h3, .stMarkdown h1{
      font-family:'Space Grotesk', sans-serif !important;
      letter-spacing:-.01em;
    }

    .t2m-eyebrow{
      font-family:'JetBrains Mono', monospace;
      font-size:11px;
      letter-spacing:.3em;
      text-transform:uppercase;
      color:var(--cyan);
      margin-bottom:6px;
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
      font-size:2.6rem;
      background:linear-gradient(100deg,#fff 0%,var(--violet) 35%,var(--magenta) 60%,var(--cyan) 100%);
      background-size:220% 220%;
      -webkit-background-clip:text;
      background-clip:text;
      color:transparent;
      margin:0 0 8px 0;
      line-height:1.08;
      animation:t2m-drift 9s ease-in-out infinite;
    }
    .t2m-sub{
      font-family:'Inter', sans-serif;
      color:var(--muted);
      font-size:.97rem;
      margin-bottom:1.8rem;
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
      margin-top:2.6rem;
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
      padding:.6rem 1.6rem !important;
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
      padding:.6rem 1.6rem !important;
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

    /* Fallback pill styling for st.radio, used when st.segmented_control
       isn't available in the installed Streamlit version. */
    div[role="radiogroup"]{
      display:flex;
      flex-wrap:wrap;
      justify-content:center;
      gap:10px;
      margin:0 auto .9rem auto;
      width:fit-content;
      max-width:100%;
    }
    div[role="radiogroup"] label{
      background:var(--panel) !important;
      border:1px solid var(--line) !important;
      border-radius:999px !important;
      padding:.5rem 1.3rem !important;
      font-size:15px !important;
      cursor:pointer;
      transition:border-color .15s ease, background .15s ease;
    }
    div[role="radiogroup"] label:has(input:checked){
      border-color:var(--violet) !important;
      background:linear-gradient(135deg,rgba(139,92,246,.35),rgba(255,79,163,.25)) !important;
    }
    div[role="radiogroup"] label > div:first-child{
      display:none !important;
    }

    /* Centered heading above each style selector (Grosor / Densidad / Ancho). */
    .t2m-ctrl-label{
      font-family:'JetBrains Mono', monospace;
      font-size:14px;
      font-weight:600;
      letter-spacing:.14em;
      text-transform:uppercase;
      text-align:center;
      width:100%;
      display:block;
      background:linear-gradient(90deg,var(--violet),var(--cyan));
      -webkit-background-clip:text;
      background-clip:text;
      color:transparent;
      margin:1.1rem 0 .5rem 0;
    }

    /* Pill-style buttons for the native segmented control. justify-content
       alone only centers the buttons INSIDE the widget's own box — it does
       nothing if that box itself is still stuck to the left. width:fit-content
       + margin:auto centers the box itself within its column. */
    div[data-testid="stSegmentedControl"]{
      width:fit-content;
      max-width:100%;
      margin:0 auto;
    }
    div[data-testid="stSegmentedControl"] button{
      font-family:'JetBrains Mono', monospace !important;
      font-size:15px !important;
      letter-spacing:.04em;
      padding:.55rem 1.3rem !important;
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

# Style controls: how chunky the strokes look. Defaults (Tiny / Dense /
# Narrow) reproduce the exact original look, so nothing changes unless
# you pick something else.
_has_segmented = hasattr(st, "segmented_control")


def style_picker(label_text, options, default_internal):
    """options: list of (internal_value, spanish_label). Shows the Spanish
    label but returns the internal value the rendering code understands."""
    labels = [lbl for _, lbl in options]
    internal_by_label = {lbl: internal for internal, lbl in options}
    default_label = next(lbl for internal, lbl in options if internal == default_internal)
    if _has_segmented:
        picked = st.segmented_control(label_text, labels, default=default_label, label_visibility="collapsed")
        picked = picked if picked else default_label
    else:
        picked = st.radio(label_text, labels, index=labels.index(default_label), horizontal=True, label_visibility="collapsed")
    return internal_by_label[picked]


def centered_style_picker(heading, label_text, options, default_internal):
    """Renders the heading + pill selector inside a real (centered) Streamlit
    column, so the row is actually centered on the page regardless of the
    installed Streamlit version's internal HTML — no CSS guesswork needed."""
    _, mid, _ = st.columns([1, 6, 1])
    with mid:
        st.markdown(f'<div class="t2m-ctrl-label">{heading}</div>', unsafe_allow_html=True)
        return style_picker(label_text, options, default_internal)


ctrl_weight = centered_style_picker(
    "Grosor", "Grosor", [("Tiny", "Fino"), ("Regular", "Regular"), ("Bold", "Grueso")], "Tiny"
)
ctrl_density = centered_style_picker(
    "Densidad", "Densidad", [("Loose", "Suelto"), ("Dense", "Denso")], "Dense"
)
ctrl_width = centered_style_picker(
    "Ancho",
    "Ancho",
    [("Narrow", "Angosto"), ("Medium", "Medio"), ("Wide", "Ancho"), ("Very Wide", "Muy ancho")],
    "Narrow",
)

with st.expander("Ajustes avanzados"):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        octave = st.slider("Octava", 0, 6, 3, help="Sube o baja la nota elegida arriba una o más octavas.")
    with c2:
        cell_ticks = st.select_slider("Tamaño", options=[60, 90, 120, 180, 240], value=120)
    with c3:
        gap = st.slider("Espacio", 0, 4, 1)
    with c4:
        lead_in = st.slider("Inicio", 0, 16, 4, help="Corre el dibujo más adelante en la línea de tiempo, para que no quede pegado al compás 1.")

base_note = note_to_midi(root, octave)

st.markdown(
    render_piano_roll_html(label, label, weight=ctrl_weight, density=ctrl_density, width=ctrl_width, gap=gap),
    unsafe_allow_html=True,
)

if st.button("Generar MIDI", type="primary"):
    data = make_midi(
        label, base_note, cell_ticks, gap, track_name=label, lead_in_cells=lead_in,
        weight=ctrl_weight, density=ctrl_density, width=ctrl_width,
    )
    st.success("MIDI generado.")
    st.download_button("⬇️ Descargar MIDI", data=data, file_name=safe_filename(label), mime="audio/midi")

st.markdown(
    '<div class="t2m-footer">Creado por '
    '<a href="https://www.instagram.com/blackbaxbeats/" target="_blank">@blackbaxbeats</a>'
    '</div>',
    unsafe_allow_html=True,
)
