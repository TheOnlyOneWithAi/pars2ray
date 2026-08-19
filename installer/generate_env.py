from pathlib import Path
try:
    import pycountry
except ImportError:
    raise SystemExit('Install pycountry: pip install pycountry')

base = Path(__file__).resolve().parents[1] / '.env.example'
text = base.read_text(encoding='utf-8').rstrip() + '\n\n# ALL ISO 3166-1 COUNTRIES / TERRITORIES\n'
for c in sorted(pycountry.countries, key=lambda x: x.alpha_2):
    code = c.alpha_2.upper()
    if code == 'IR':
        continue  # Iran is the master in this architecture
    text += f'\n# {c.name}\n{code}_IP=\n{code}_USER=root\n{code}_PASS=\n{code}_PORT=22\n'
base.write_text(text, encoding='utf-8')
print(base)
