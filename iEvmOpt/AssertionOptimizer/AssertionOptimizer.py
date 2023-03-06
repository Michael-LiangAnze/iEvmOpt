import sys

from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from GraphTools.PathGenerator import PathGenerator
from Utils import DotGraph


class AssertionOptimizer:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg

        # 用于路径搜索的有向无环图信息
        self.dagNodes = []  # 存储点，格式为 [n1,n2,n3...]
        self.dagEdges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.dagInEdges = {}  # 存储入边表，格式为 to:[from1,from2...]
        self.loopRelated = []  # 是强连通分量收缩后的点
        self.invalidCnt = 0  # 用于标记不同invalid对应的路径集合
        self.paths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidid:[[路径1中的点],[路径2中的点]]

    def optimize(self):
        # 首先做路径搜索
        self.__searchPaths()

    def __searchPaths(self):
        # 首先寻找强连通分量，使用tarjan算法
        tarjanAlg = TarjanAlgorithm(list(self.cfg.blocks.keys()), dict(self.cfg.edges))
        tarjanAlg.tarjan(self.cfg.initBlockId)
        sccList = tarjanAlg.getSccList()
        # print(sccList)

        # 然后将强连通分量收缩为一个点，这个点的id比当前cfg所有节点的id都要大
        sccCnt = self.cfg.exitBlockId
        self.dagNodes = list(self.cfg.blocks.keys())
        self.dagEdges = dict(self.cfg.edges)
        self.dagInEdges = dict(self.cfg.inEdges)

        # 测试使用
        # self.dagNodes = [1, 2, 3, 4, 5, 6]
        # self.dagEdges = {1: [2], 2: [3], 3: [1, 4], 4: [5], 5: [6], 6: [4]}
        # self.dagInEdges = {1: [3], 2: [1], 3: [2], 4: [3, 6], 5: [4], 6: [5]}
        # sccCnt = 6
        # sccList = [[1, 2, 3], [4, 5, 6]]
        # g = DotGraph(self.dagEdges, self.dagNodes)
        # g.genDotGraph(sys.argv[0], "dag_init")

        for scc in sccList:
            if len(scc) > 1:
                # 找到两个点以上的强连通分量
                # 将其收缩为一个点，ID为sccCnt+1
                sccCnt += 1
                self.dagNodes.append(sccCnt)
                self.dagEdges[sccCnt] = []
                self.dagInEdges[sccCnt] = []
                self.loopRelated.append(sccCnt)
                for i in scc:
                    # 让i的所有入边(起始点不在强连通分量内的)指向收缩的点
                    for inNode in self.dagInEdges[i]:
                        if inNode not in scc:
                            self.dagEdges[inNode] = [sccCnt if node == i else node for node in
                                                     self.dagEdges[inNode]]  # 将其替换为新的点
                            self.dagInEdges[sccCnt].append(inNode)
                    # 添加收缩点的出边：从i指向的，不是当前scc内的点
                    for outNode in self.dagEdges[i]:
                        if outNode not in scc:
                            self.dagEdges[sccCnt].append(outNode)
                            self.dagInEdges[outNode] = [sccCnt if node == i else node for node in
                                                        self.dagInEdges[outNode]]  # 将其替换为新的点
                # scc中的点全部被处理，现在直接从图结构中去除该连同分量相关的点、边
                for i in scc:
                    self.dagNodes.remove(i)
                    self.dagEdges.pop(i)
                    self.dagInEdges.pop(i)

        # 生成点图
        g = DotGraph(self.dagEdges, self.dagNodes)
        g.genDotGraph(sys.argv[0], "dag")

        # 对cfg中所有的invalid节点，搜索他们的路径
        for i in self.cfg.blocks.values():
            if i.isInvalid:  # 是invalid节点
                self.invalidCnt += 1
                pg = PathGenerator(self.dagNodes, self.dagEdges)
                pg.genPath(self.cfg.initBlockId, i.offset)
                self.paths[self.invalidCnt] = pg.getPath()
        print(self.paths)
