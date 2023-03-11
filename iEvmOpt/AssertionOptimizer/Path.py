class Path:
    def __init__(self, pathId: int, pathNodes: list):
        self.pathId = pathId
        self.pathNodes = pathNodes

    def printPath(self):
        print("Path'Id:{}".format(self.pathId))
        print("Path'Nodes:{}".format(self.pathNodes))
