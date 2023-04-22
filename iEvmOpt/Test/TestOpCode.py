import sys

from AssertionOptimizer.TagStacks.TagStackForCfgRepairKit import TagStackForCfgRepairKit
from Cfg import *
from Cfg.EtherSolver import EtherSolver

if __name__ == '__main__':
    print("****** Testing ******\n")
    if len(sys.argv) < 2:
        exit(-1)

    builder = EtherSolver(sys.argv[1], True)
    cfg = builder.getCfg()
    constructorCfg = builder.getConstructorCfg()

    # 测试符号执行
    s = TagStackForCfgRepairKit(cfg)
    path = [0, 13, 59, 70, 81, 92, 103, 451, 463, 3075, 3253]
    blocks = constructorCfg.blocks
    for n in path:
        s.setBeginBlock(n)
        while not s.allInstrsExecuted():
            s.printState(False)
            s.execNextOpCode()
