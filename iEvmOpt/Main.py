import os
import sys

from Cfg import *
from AssertionOptimizer.AssertionOptimizer import AssertionOptimizer
from Cfg.EtherSolver import EtherSolver

if __name__ == '__main__':
    """
    argv参数：
    argv[1]: 输入字节码文件
    argv[2]: 输出目录
    """

    srcPath = sys.argv[1]
    os.chdir(os.path.dirname(__file__))

    if len(sys.argv) < 3:
        exit(-1)

    # es = EtherSolver(srcPath)
    # es = EtherSolver(srcPath, genPng=True)
    es = EtherSolver(srcPath, isParseBefore=True)
    constructorCfg = es.getConstructorCfg()
    cfg = es.getCfg()
    constructorDataSegStr = es.getConstructorDataSegStr()
    dataSegStr = es.getDataSeg()

    ao = AssertionOptimizer(constructorCfg, cfg, constructorDataSegStr, dataSegStr, sys.argv[2], True)
    ao.optimize()
