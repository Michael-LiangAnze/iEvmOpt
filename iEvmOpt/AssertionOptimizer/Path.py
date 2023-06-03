class Path:
    def __init__(self, pathId: int, pathNodes: list):
        self.pathId = pathId
        self.pathNodes = pathNodes
        self.lastNode = pathNodes[pathNodes.__len__() - 1]
        self.funcCallChain = []  # 函数调用链
        self.invNode = 0  # 属于哪一个invalid
        self.isCheck = True # 是否对该路径进行可达性分析。一旦该路径的invalid，其中有了某条路径是超时的，那么它的所有路径都会被置为不分析状态

    def setFuncCallChain(self, callChain: list):
        self.funcCallChain = list(callChain)

    def getPathNodes(self):
        return self.pathNodes

    def getId(self):
        return self.pathId

    def getLastNode(self):
        return self.lastNode

    def setInvNode(self, invNode: int):
        self.invNode = invNode

    def getInvNode(self):
        return self.invNode

    def doCheck(self):
        return self.isCheck

    def setUndo(self):
        self.isCheck = False

    def printPath(self):
        print("Path'id:{}".format(self.pathId))
        print("Path'nodes:{}".format(self.pathNodes))
        print("Path'funcCallChain:{}".format(self.funcCallChain))
