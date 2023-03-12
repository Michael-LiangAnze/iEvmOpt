class Path:
    def __init__(self, pathId:int,pathNodes: list):
        self.pathId = pathId
        self.pathNodes = pathNodes
        self.funcCallChain = [] #函数调用链

    def setFuncCallChain(self,callChain:list):
        self.funcCallChain = list(callChain)

    def printPath(self):
        print("Path'id:{}".format(self.pathId))
        print("Path'nodes:{}".format(self.pathNodes))
        print("Path'funcCallChain:{}".format(self.funcCallChain))
