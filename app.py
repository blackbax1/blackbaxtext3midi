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

    # Sort by absolute tick; at equal ticks, note_off before note_on.
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


def safe_filename(label):
    # Turn "C minor - Blackbax" into a filesystem-safe "C_minor_-_Blackbax.mid"
    keep = []
    for c in label:
        if c.isalnum() or c in " -_#":
            keep.append(c)
    cleaned = "".join(keep).strip()
    cleaned = cleaned.replace("#", "s").replace(" ", "_")
    return f"{cleaned}.mid"


st.set_page_config(page_title="Text → MIDI", page_icon="🎹")
st.title("🎹 Text → MIDI")
st.write("Escribe texto y genera un MIDI que dibuja las letras en el piano roll de Ableton.")

text = st.text_input("Texto", value="Blackbax", max_chars=80)

k1, k2 = st.columns(2)
with k1:
    root = st.selectbox("Nota", NOTES, index=0)
with k2:
    scale = st.selectbox("Escala", ["Minor", "Major"], index=0)

label = f"{root} {scale.lower()} - {text}"
st.caption(f"**{label}**")

c1, c2, c3 = st.columns(3)
with c1:
    base_note = st.slider("Nota base", 24, 84, 48)
with c2:
    cell_ticks = st.select_slider("Tamaño", options=[60, 90, 120, 180, 240], value=120)
with c3:
    gap = st.slider("Espacio", 0, 4, 1)

if st.button("Generar MIDI", type="primary"):
    data = make_midi(text, base_note, cell_ticks, gap, track_name=label)
    st.success("MIDI generado.")
    st.download_button("⬇️ Descargar MIDI", data=data, file_name=safe_filename(label), mime="audio/midi")
