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
    path = [0, 74,573,1451,1688,1459,1591,1863,1599,581,1601,1650]
    blocks = constructorCfg.blocks
    for n in path:
        s.setBeginBlock(n)
        while not s.allInstrsExecuted():
            s.printState(False)
            s.execNextOpCode()
