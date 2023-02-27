from collections import deque as stack


# 代码思路来自https://zhuanlan.zhihu.com/p/348703439

class TarjanAlgorithm:
    def __init__(self, _nodes: list, _edges: dict):
        self.nodes = _nodes  # 节点列表
        self.edges = _edges  # 存储出边表，格式为 id:[n1,n2...]
        self.timeStamp = 0
        self.dfsN = {}
        self.low = {}
        self.visited = dict(zip(self.edges.keys(), [False for i in self.edges.keys()]))
        self.s = stack()
        self.sccList = []

    def tarjan(self, n):
        self.dfsN[n] = self.low[n] = self.timeStamp
        self.visited[n] = True
        self.timeStamp += 1
        self.s.append(n)
        for to in self.edges[n]:
            if not self.visited[to]:
                self.tarjan(to)
                self.low[n] = min(self.low[n], self.low[to])
            elif to in self.s:
                self.low[n] = min(self.low[n], self.dfsN[to])

        scc = []
        if self.dfsN[n] == self.low[n]:
            while True:
                e = self.s.pop()
                scc.append(e)
                if n == e:
                    break
            self.sccList.append(scc)

    def getSccList(self):
        return self.sccList
