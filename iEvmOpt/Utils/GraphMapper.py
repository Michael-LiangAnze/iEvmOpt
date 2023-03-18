class GraphMapper:
    '''
    将原图中以偏移量为节点标号的图映射到以1~N为标号的图
    '''

    def __init__(self, nodes: list, edges: dict):
        self.offsetGraphNodes = list(nodes)
        self.offsetGraphEdges = dict(edges)

        self.offsetToNewMapper = {}  # 旧节点到新节点的映射
        self.newToOffsetMapper = {}  # 新节点到旧节点的映射
        self.newGraphNodes = []
        self.newGraphEdges = {}
        self.__buildMap()

    def __buildMap(self):
        # 构建映射
        self.newGraphNodes = [i for i in range(1, self.offsetGraphNodes.__len__() + 1)]
        for i in range(self.offsetGraphNodes.__len__()):
            offsetNode = self.offsetGraphNodes[i]
            newNode = self.newGraphNodes[i]
            self.offsetToNewMapper[offsetNode] = newNode
            self.newToOffsetMapper[newNode] = offsetNode
        for _from in self.offsetGraphEdges.keys():
            _newFrom = self.offsetToNewMapper[_from]
            self.newGraphEdges[_newFrom] = []
            for _to in self.offsetGraphEdges[_from]:
                _newTo = self.offsetToNewMapper[_to]
                self.newGraphEdges[_newFrom].append(_newTo)

    def newToOffset(self, newNode: int):
        return self.newToOffsetMapper[newNode]

    def offsetToNew(self, offsetNode: int):
        return self.offsetToNewMapper[offsetNode]

    def getNewNodes(self):
        return self.newGraphNodes

    def getNewEdges(self):
        return self.newGraphEdges

    def output(self):
        print(self.newGraphNodes)
        print("offset to new:{}".format(self.offsetToNewMapper))
        print("new to offset:{}".format(self.newToOffsetMapper))
        for _from in self.newGraphEdges.keys():
            for _to in self.newGraphEdges[_from]:
                print("{}->{}".format(_from, _to))
