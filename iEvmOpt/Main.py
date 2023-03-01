import sys

from Cfg import *

if __name__ == '__main__':
    if len(sys.argv) < 2:
        exit(-1)

    builder = CfgBuilder(sys.argv[1])
    cfg = builder.getCfg()

    # 测试计算有向环
    # tarjanAlg = TarjanAlgorithm(cfg.blocks.keys(), cfg.edges)
    # tarjanAlg.tarjan(cfg.initBlockId)
    # print(tarjanAlg.sccList)

