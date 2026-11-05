from pathlib import Path
p = Path('/opt/fisia/reverse_proxy.py')
s = p.read_text()
bad = '''    if clean_path in {"/abel", "/abel.html"} or clean_path.startswith("/abel/"):
    if clean_path in {"/abel-front", "/abel-front/"} or clean_path.startswith("/abel-front/"):
        return "http://127.0.0.1:8050"
        return ABEL_UPSTREAM'''
good = '''    if clean_path in {"/abel-front", "/abel-front/"} or clean_path.startswith("/abel-front/"):
        return "http://127.0.0.1:8050"
    if clean_path in {"/abel", "/abel.html"} or clean_path.startswith("/abel/"):
        return ABEL_UPSTREAM'''
assert bad in s
p.write_text(s.replace(bad, good, 1))
