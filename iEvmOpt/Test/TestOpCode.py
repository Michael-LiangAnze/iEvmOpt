import sys

from AssertionOptimizer.TagStacks.TagStack import TagStack
from Cfg import *

if __name__ == '__main__':
    print("****** Testing ******\n")
    if len(sys.argv) < 2:
        exit(-1)

    builder = EtherSolver(sys.argv[1], True)
    cfg = builder.getCfg()
    constructorCfg = builder.getConstructorCfg()

    # 测试符号执行
    s = TagStack(constructorCfg)
    path = [0, 16, 74, 100, 165, 180, 183, 210, 211,228,234,243]
    blocks = constructorCfg.blocks
    for n in path:
        s.setBeginBlock(n)
        while not s.allInstrsExecuted():
            s.printState(False)
            s.execNextOpCode()
