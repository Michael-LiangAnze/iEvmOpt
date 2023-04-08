class Function:
    def __init__(self, id: int, firstBodyBlockOffset: int, lastBodyBlockOffset: int, funcBodyNodes: list,
                 graphEdges: dict):
        self.funcId = id
        self.firstBodyBlockOffset = firstBodyBlockOffset
        self.lastBodyBlockOffset = lastBodyBlockOffset
        self.funcBodyNodes = funcBodyNodes  # 函数体的节点的offset

        self.funcSubGraphEdges = {}  # 函数子图的出边表.注意，这个子图是加了边(调用->返回)的，并不是cfg里原来的子图
        self.__genSubGraphEdges(graphEdges)

        # 部分冗余需要用到的信息
        self.invalidNodes = []  # 记录该函数内需要优化的部分冗余的invalid
        self.removedRangeInfo = {}  # 记录需要删除的区间信息，格式为： invNode:[targetAddr,targetNode,endAddr]

    def __genSubGraphEdges(self, graphEdges: dict):
        # 生成函数子图的边
        checkSet = set(self.funcBodyNodes)
        for i in self.funcBodyNodes:
            self.funcSubGraphEdges[i] = []
        for node in self.funcBodyNodes:
            for out in graphEdges[node]:
                if out in checkSet:  # 找到一个指向内部节点的边
                    self.funcSubGraphEdges[node].append(out)

    def addInvalidNode(self, invNode: int):
        self.invalidNodes.append(invNode)

    def getInvalidNodes(self):
        return self.invalidNodes

    def addRemovedRangeInfo(self, invNode: int, info: list):
        self.removedRangeInfo[invNode] = info

    def getRemovedRangeInfo(self, invNode):
        return self.removedRangeInfo[invNode]

    def printFunc(self):
        print("Function'Id:{}".format(self.funcId))
        print("Function'firstBodyBlockOffset:{}".format(self.firstBodyBlockOffset))
        print("Function'lastBodyBlockOffset:{}".format(self.lastBodyBlockOffset))
        print("Function'funcBodyNodes:{}".format(self.funcBodyNodes))
        print("Function'subGraphEdges:{}\n".format(self.funcSubGraphEdges))
