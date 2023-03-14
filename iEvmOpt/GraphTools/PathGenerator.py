# 用于生成有向图中任意两点之间的所有路径
# 返回的格式为：[[路径1从起点到终点经过的点],[路径1从起点到终点经过的点]...]
# 需要注意，图中是没有有向环的

from Utils import Stack
from AssertionOptimizer.JumpEdge import JumpEdge
from Utils.Logger import Logger


class PathGenerator:
    def __init__(self, nodes: list, edges: dict, uncondJumpEdges: list, isLoopRelated: dict, node2FuncId: dict,
                 funcBodyDict: dict):
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
        self.node2FuncId = node2FuncId  # 用于检测递归调用
        self.funcBodyDict = funcBodyDict  # 用于检测递归调用
        self.isFuncCallLoopRelated = dict(
            zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 记录节点是否为环形函数调用链相关
        self.sccVisiting = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 记录某个函数内scc是否正在被访问
        self.callLoopVisiting = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 记录函数调用链构成的环是否正在被访问

        self.pathRecorder = Stack()
        self.returnAddrStack = Stack()
        self.paths = []

        self.log = Logger()

    def genPath(self, begin: int, target: int):
        '''
        生成从begin到target的所有路径，这些路径符合函数的调用关系
        :param begin:路径搜索的起始节点
        :param target:路径搜索的终止节点
        :return:[路径1的点组成的list，路径2的点组成的list....]
        '''
        # 初始化，清除之前的信息
        self.beginN = begin
        self.targetN = target
        self.pathRecorder.clear()
        self.paths.clear()
        self.returnAddrStack.clear()
        # dfs寻路

        self.__dfs(self.beginN)
        # print(self.isFuncCallLoopRelated)

    def __dfs(self, curNode: int):
        """
        路径记录：每访问一个新节点，则将其加入到路径栈，离开时pop一次(其实就是pop自己)
        访问控制：每访问一个新节点，则将其设置为true状态，退出时设置为false
        """
        self.pathRecorder.push(curNode)
        if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
            self.sccVisiting[curNode] = True
        if self.isFuncCallLoopRelated[curNode]:  # 当前访问的是函数调用环上的一个点
            self.callLoopVisiting[curNode] = True

        if curNode == self.targetN:  # 到达终点，生成一条路径，并返回1
            self.paths.append(self.pathRecorder.getStack())
        else:
            for node in self.edges[curNode]:  # 查看每一个出边
                if self.sccVisiting[node]:  # 防止循环内调用函数造成死循环
                    continue
                if self.callLoopVisiting[node]:  # 出边指向的点是某个调用环上的点，而且已有的路径经过了它，不能进行访问，否则会死循环
                    continue
                key = [curNode, node].__str__()
                if key in self.uncondJumpEdges.keys():  # 这是一条uncondjump边，但是不确定是调用边还是返回边
                    e = self.uncondJumpEdges[key]
                    if e.isCallerEdge:  # 是一条调用边
                        # 可以是环相关的点，循环内调用函数也可以
                        # if self.isLoopRelated[node]:  # 不能是环相关的点，例如循环内调用函数，会出现无限递归的情况
                        #     continue
                        if self.returnAddrStack.hasItem(
                                e.tetrad[1]):  # 如果是已经调用过的函数，则要将两次调用之间的所有函数的所有节点，标记为环形函数调用链相关
                            # 首先找出所有环相关的函数
                            callFuncId = self.node2FuncId[e.targetNode]
                            callLoopRelatedFuncId = {}  # 用字典只是为了过滤相同的函数id
                            tempPathRecorder = Stack()
                            tempPathRecorder.setStack(self.pathRecorder.getStack())
                            isStop = False
                            while not isStop:
                                n = tempPathRecorder.pop()
                                if self.node2FuncId[n] == callFuncId and self.node2FuncId[
                                    tempPathRecorder.getTop()] != callFuncId:  # 已经彻底退出环了
                                    isStop = True
                                callLoopRelatedFuncId[self.node2FuncId[n]] = None
                                self.callLoopVisiting[n] = True  # 将当前已经将走过的，和环形调用链相关的点都标出来
                            # 然后将这些函数的所有节点都标记为LoopFuncCallChain
                            for funcId in callLoopRelatedFuncId.keys():
                                for funcNode in self.funcBodyDict[funcId].funcBodyNodes:
                                    self.isFuncCallLoopRelated[funcNode] = True
                            self.log.warning(
                                "检测到环形函数调用链的情况，涉及的函数id有：{}".format([i for i in callLoopRelatedFuncId.keys()]))
                            continue  # 本次出边是不能走的，走的话一定会出现死循环
                        self.returnAddrStack.push(e.tetrad[1])  # push返回地址
                        self.__dfs(node)
                    elif e.isReturnEdge:  # 是一条返回边
                        if self.returnAddrStack.empty():  # 栈里必须还有地址
                            continue
                        if e.tetrad[3] != self.returnAddrStack.getTop():  # 和之前push的返回地址相同，才能做返回
                            continue
                        stackItems = self.returnAddrStack.getStack()  # 保存之前的栈，防止栈因为走向终止节点而被清空
                        retAddr = self.returnAddrStack.pop()  # 模拟返回后的效果
                        self.__dfs(node)  # 返回
                        if self.returnAddrStack.getTop() != retAddr:  # 先检查栈有没有走到过终点。因为如果走到过，则当前函数的返回地址以及前面函数的返回地址都没了，需要恢复
                            self.returnAddrStack.setStack(stackItems)
                    else:  # 是一条普通的uncondjump边
                        self.__dfs(node)
                else:  # 是其他跳转边
                    if self.sccVisiting[node]:
                        continue
                    self.__dfs(node)

        self.pathRecorder.pop()
        self.sccVisiting[curNode] = False
        self.callLoopVisiting[curNode] = False

    def getPath(self):
        return list(self.paths)

    def getFuncCallLoopRelated(self):
        return self.isFuncCallLoopRelated
