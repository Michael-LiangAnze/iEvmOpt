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
        self.returnAddrStack = Stack()
        self.paths = []

    def genPath(self, begin: int, target: int):
        # 初始化，清除之前的信息
        self.beginN = begin
        self.targetN = target
        self.pathRecorder.clear()
        self.paths.clear()
        self.returnAddrStack.clear()
        # dfs寻路

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
                        if self.isLoopRelated[node]:  # 不能是环相关的点，例如循环内调用函数，会出现无限递归的情况
                            continue
                        if self.returnAddrStack.hasItem(e.tetrad[1]):  # 不能是已经调用过的函数
                            continue
                        self.returnAddrStack.push(e.tetrad[1])  # push返回地址
                        self.__dfs(node)
                    else:  # 是一条返回边
                        if self.returnAddrStack.empty():  # 栈里必须还有地址
                            continue
                        if e.tetrad[3] != self.returnAddrStack.getTop():  # 和之前push的返回地址相同，才能做返回
                            continue
                        if self.isLoopRelated[node]:  # 不能是环相关的点
                            continue
                        retAddr = self.returnAddrStack.pop()  # 模拟返回后的效果
                        self.__dfs(node)  # 返回
                        self.returnAddrStack.push(retAddr)  # 返回后又回来，相当于没返回，最新的调用还是当前函数

                else:  # 是其他跳转边
                    if self.isLoopRelated[node]:
                        continue
                    self.__dfs(node)
        self.pathRecorder.pop()

    def getPath(self):
        return list(self.paths)
