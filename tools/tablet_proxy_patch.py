from pathlib import Path
p = Path('/opt/fisia/reverse_proxy.py')
s = p.read_text()
needle = '    if clean_path in {"/abel", "/abel.html"} or clean_path.startswith("/abel/"):\n'
insert = needle + '    if clean_path in {"/abel-front", "/abel-front/"} or clean_path.startswith("/abel-front/"):\n        return "http://127.0.0.1:8050"\n'
if '"/abel-front"' not in s:
    assert needle in s
    p.write_text(s.replace(needle, insert, 1))
