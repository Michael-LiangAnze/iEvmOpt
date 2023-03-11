# 用于生成有向图中任意两点之间的所有路径
# 返回的格式为：[[路径1从起点到终点经过的点],[路径1从起点到终点经过的点]...]
# 需要注意，图中是没有有向环的

from Utils import Stack
from AssertionOptimizer.JumpEdge import JumpEdge


class PathGenerator:
    def __init__(self, nodes: list, edges: dict, uncondJumpEdges: list, isLoopRelated: dict):
        """初始化路径搜索需要的信息
        :param nodes:图的节点信息，格式为[n1,n2,n3]
        :param edges: 图的出边表，格式为{from:[to1,to2.....]}
        """
        self.nodes = nodes
        self.edges = edges
        self.beginN = 0  # 起始点和终结点
        self.targetN = 0
        self.uncondJumpEdges = {}  # 记录调用边信息。格式为 "[起始点的offset，终止点的offset]":边对象
        for e in uncondJumpEdges:
            key = [e.beginNode, e.targetNode].__str__()
            self.uncondJumpEdges[key] = e

        self.isLoopRelated = isLoopRelated
        self.pathRecorder = Stack()
        self.paths = []

    def genPath(self, begin: int, target: int):
        # 初始化，清除之前的信息
        self.beginN = begin
        self.targetN = target
        self.pathRecorder.clear()
        self.paths.clear()

        # dfs寻路
        self.returnAddrStack = Stack()
        self.__dfs(self.beginN)

    def __dfs(self, curNode: int):
        """
        路径记录：每访问一个新节点，则将其加入到路径栈，离开时pop一次(其实就是pop自己)
        访问控制：每访问一个新节点，则将其设置为true状态，退出时设置为false
        """
        self.pathRecorder.push(curNode)
        if curNode == self.targetN:  # 到达终点，生成一条路径，并返回
            self.paths.append(self.pathRecorder.getStack())
        else:
            for node in self.edges[curNode]:  # 查看每一个出边
                key = [curNode, node].__str__()
                if key in self.uncondJumpEdges.keys():  # 这是一条调用边或者返回边
                    e = self.uncondJumpEdges[key]
                    if e.isCallerEdge:  # 是一条调用边
                        self.returnAddrStack.push(e.tetrad[1])  # push返回地址
                        self.__dfs(node)
                    else:  # 是一条返回边
                        if not self.returnAddrStack.empty():  # 栈里还有地址
                            if e.tetrad[3] == self.returnAddrStack.getTop():  # 和之前push的返回地址相同，才能做返回
                                self.returnAddrStack.pop()
                                self.__dfs(node)
                else:  # 是其他跳转边
                    self.__dfs(node)
        self.pathRecorder.pop()

    def getPath(self):
        return list(self.paths)
