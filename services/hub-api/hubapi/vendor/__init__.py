"""Files copied verbatim from components of the collection (services/vendor.json says from where;
`python3 services/vendor.py --check` refuses drift). They import each other flat, as they do in their components,
so this directory is put on the path once here."""
import os, sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
