#!./run-python.sh

import dis
import sys

with open(sys.argv[1], "r") as f:
    code = f.read()
    dis.dis(code)
