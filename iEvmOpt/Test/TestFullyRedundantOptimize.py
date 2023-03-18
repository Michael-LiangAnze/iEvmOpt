import sys

from Cfg import *
from AssertionOptimizer.AssertionOptimizer import AssertionOptimizer

if __name__ == '__main__':
    if len(sys.argv) < 2:
        exit(-1)

    # builder = CfgBuilder(sys.argv[1])
    builder = CfgBuilder(sys.argv[1],True)
    cfg = builder.getCfg()
    # cfg.output()

    ao = AssertionOptimizer(cfg)
    ao.optimize()
