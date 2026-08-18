# Text → MIDI

Genera archivos MIDI donde las notas forman letras visibles en el piano roll.

## En Mac
```bash
cd text2midi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Se abrirá una página en el navegador. Escribe el texto, genera el MIDI y arrástralo a Ableton Live.
