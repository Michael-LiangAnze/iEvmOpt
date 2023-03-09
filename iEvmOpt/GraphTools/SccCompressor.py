class SccCompressor:
    def __init__(self):
        self.nodes = []  # 存储所有点，格式为 [n1,n2,n3...]
        self.scc = []  # 存储scc中的点
        self.edges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = {}  # 存储入边表，格式为 to:[from1,from2...]
        self.sccId: int = -1  # scc的标号

    def setInfo(self, nodes: list, scc: list, edges: dict, inEdges: dict, sccBeginId: int):
        self.nodes = list(nodes)  # 存储所有点，格式为 [n1,n2,n3...]
        self.scc = list(scc)  # 存储scc中的点
        self.edges = dict(edges)  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = dict(inEdges)  # 存储入边表，格式为 to:[from1,from2...]
        self.sccId = int(sccBeginId)  # scc的开始标号，每使用一次，标号+1

    def compress(self):
        if len(self.scc) > 1:
            # 找到两个点以上的强连通分量
            # 将其收缩为一个点，ID为sccCnt+1
            self.nodes.append(self.sccId)
            self.edges[self.sccId] = []
            self.inEdges[self.sccId] = []
            for i in self.scc:
                # 让i的所有入边(起始点不在强连通分量内的)指向收缩的点
                for inNode in self.inEdges[i]:
                    if inNode not in self.scc:
                        self.edges[inNode] = [self.sccId if node == i else node for node in
                                              self.edges[inNode]]  # 将其替换为新的点
                        self.inEdges[self.sccId].append(inNode)
                # 添加收缩点的出边：从i指向的，不是当前scc内的点
                for outNode in self.edges[i]:
                    if outNode not in self.scc:
                        self.edges[self.sccId].append(outNode)
                        self.inEdges[outNode] = [self.sccId if node == i else node for node in
                                                 self.inEdges[outNode]]  # 将其替换为新的点
            # scc中的点全部被处理，现在直接从图结构中去除该连同分量相关的点、边
            for i in self.scc:
                self.nodes.remove(i)
                self.edges.pop(i)
                self.inEdges.pop(i)

    def getNodes(self):
        return self.nodes

    def getEdges(self):
        return self.edges

    def getInEdges(self):
        return self.inEdges
