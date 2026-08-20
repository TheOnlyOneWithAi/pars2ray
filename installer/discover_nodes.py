import re
from pathlib import Path

from dotenv import dotenv_values

ENV = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
pat = re.compile(r'^([A-Z]{2})(\d*)_IP$')
found=[]
for key, ip in ENV.items():
    m=pat.match(key)
    if not m or not ip:
        continue
    prefix=m.group(1)+m.group(2)
    found.append({
        'node_key': prefix,
        'country': m.group(1),
        'ip': ip,
        'user': ENV.get(prefix+'_USER') or 'root',
        'pass': ENV.get(prefix+'_PASS') or '',
        'port': int(ENV.get(prefix+'_PORT') or 22),
    })
print(found)
