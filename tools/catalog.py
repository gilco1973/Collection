#!/usr/bin/env python3
"""Compatibility alias: the shelf tool was called the catalog tool. `catalog` now means what the platform
specification means by it (a consumer's signed tool catalog, §4.12); the components index is the shelf."""
import runpy, sys
sys.argv[0] = __file__.replace("catalog.py", "shelf.py")
runpy.run_path(sys.argv[0], run_name="__main__")
