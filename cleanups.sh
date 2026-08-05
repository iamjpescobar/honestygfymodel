sed -i 's|actions/checkout@v4|actions/checkout@v7|g; s|actions/setup-python@v5|actions/setup-python@v7|g' .github/workflows/*.yml

python3 - <<'PY'
import pathlib
old = '''        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            tar.extractall(DEST)
'''
new = '''        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            # filter="data" refuses absolute paths, ../ traversal, symlinks
            # and device nodes. Python 3.14 makes this the default anyway.
            # Guarded because this file's contract is to never fail the
            # build: on a Python older than 3.11.4 the kwarg raises
            # TypeError, and extracting unfiltered beats losing the archive
            # and silently falling back to live Statcast pulls.
            try:
                tar.extractall(DEST, filter="data")
            except TypeError:
                tar.extractall(DEST)
'''
p = pathlib.Path("app/fetch_data.py")
s = p.read_text()
assert old in s, "ANCHOR NOT FOUND - stopping, nothing changed"
p.write_text(s.replace(old, new))
print("fetch_data.py patched")
PY

grep -rho "actions/[a-z-]*@v[0-9]*" .github/workflows/ | sort -u
python3 -m py_compile app/fetch_data.py && echo "fetch_data.py compiles"
