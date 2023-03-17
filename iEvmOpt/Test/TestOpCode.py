import sys

from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from Cfg import *

if __name__ == '__main__':
    print("****** Testing ******\n")
    if len(sys.argv) < 2:
        exit(-1)

    builder = CfgBuilder(sys.argv[1])
    cfg = builder.getCfg()

    # 测试符号执行
    s = SymbolicExecutor(cfg)
    s.setBeginBlock(0)

    for i in range(4):
        cond = s.execNextOpCode()
        s.printState(False)





