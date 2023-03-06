from Cfg.Cfg import Cfg
from GraphTools.TarjanAlgorithm import TarjanAlgorithm


class AssertionOptimizer:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg

        # 用于路径搜索的有向无环图
        self.acyclicGNodes = []  # 存储出边表，格式为 from:[to1,to2...]
        self.acyclicGEdges = {}  # 存储点，格式为 [n1,n2,n3...]

    def optimize(self):
        # 首先做路径搜索
        self.__searchPaths()

    def __searchPaths(self):
        # 首先去除有向环，使用tarjan算法
        tarjanAlg = TarjanAlgorithm(list(self.cfg.blocks.keys()), dict(self.cfg.edges))
        tarjanAlg.tarjan(self.cfg.initBlockId)
        sccList = tarjanAlg.getSccList()
        print(sccList)
