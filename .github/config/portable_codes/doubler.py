#!/usr/bin/env python

import sys
import numpy as np

def main():
    inp_file = sys.argv[1]
    with open(inp_file, 'rb') as fh:
        inp = fh.read()
        inp = int(inp)
    res = np.multiply(2, inp)
    print(res)

if __name__ == "__main__":
    main()