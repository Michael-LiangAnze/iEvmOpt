class Path:
    def __init__(self, pathId:int,pathNodes: list):
        self.pathId = pathId
        self.pathNodes = pathNodes

    def printPath(self):
        print("Path'id:{}".format(self.pathId))
        print("Path'nodes:{}".format(self.pathNodes))
