import sys

from Cfg import *

if __name__ == '__main__':
    if len(sys.argv) < 2:
        exit(-1)

    builder = EtherSolver(sys.argv[1])
    cfg = builder.getCfg()
    # cfg.output()
