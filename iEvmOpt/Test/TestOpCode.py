import sys

from Cfg import *

if __name__ == '__main__':
    print("****** Testing ******\n")
    if len(sys.argv) < 2:
        exit(-1)

    builder = CfgBuilder(sys.argv[1], True)
    cfg = builder.getCfg()

    # 测试符号执行
    s = SymbolicExecutor()
    s.setBeginBlock(cfg.blocks[0])

    for i in range(3):
        cond = s.execNextOpCode()
        s.printState(False)





