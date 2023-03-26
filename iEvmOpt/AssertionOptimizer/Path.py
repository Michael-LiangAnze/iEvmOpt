class Path:
    def __init__(self, pathId: int, pathNodes: list):
        self.pathId = pathId
        self.pathNodes = pathNodes
        self.lastNode = pathNodes[pathNodes.__len__() - 1]
        self.funcCallChain = []  # 函数调用链
        self.constrains = []  # 路径上的约束

    def setFuncCallChain(self, callChain: list):
        self.funcCallChain = list(callChain)

    def getId(self):
        return self.pathId

    def getLastNode(self):
        return self.lastNode

    def setConstrain(self, constrain: list):
        self.constrains = constrain

    def printPath(self):
        print("Path'id:{}".format(self.pathId))
        print("Path'nodes:{}".format(self.pathNodes))
        print("Path'funcCallChain:{}".format(self.funcCallChain))
