import sys

from Cfg import *
from AssertionOptimizer.AssertionOptimizer import AssertionOptimizer

if __name__ == '__main__':
    if len(sys.argv) < 3:
        exit(-1)

    # es = EtherSolver(sys.argv[1])
    es = EtherSolver(sys.argv[1], True)
    constructorCfg = es.getConstructorCfg()
    cfg = es.getCfg()
    dataSegStr = es.getDataSeg()

    # cfg.output()

    ao = AssertionOptimizer(cfg, dataSegStr, sys.argv[1], sys.argv[2], True)
    ao.optimize()
    ao.outputNewCfgPic()  # 生成新cfg的图片
