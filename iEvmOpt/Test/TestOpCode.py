import sys

from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
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
    s = SymbolicExecutor(cfg)
    path = [0, 13, 65, 76, 87, 98, 109, 120, 131, 142, 153, 1062, 1074, 3034, 3473, 3512, 3590, 3733, 4257]
    blocks = constructorCfg.blocks
    for n in path:
        s.setBeginBlock(n)
        while not s.allInstrsExecuted():
            s.printState(False)
            s.execNextOpCode()
