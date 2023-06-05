# 用于生成有向图中任意两点之间的所有路径
# 返回的格式为：[[路径1从起点到终点经过的点],[路径1从起点到终点经过的点]...]
# 需要注意，图中是没有有向环的
import sys

from AssertionOptimizer.Path import Path
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from AssertionOptimizer.TagStacks.SimplifiedExecutor import SimplifiedExecutor
from Cfg.Cfg import Cfg
from Utils import Stack
from Utils.Logger import Logger
from AssertionOptimizer.TagStacks.TagStack import TagStack
import time


class PathGenerator:
    def __init__(self, cfg: Cfg, uncondJumpEdges: list, isLoopRelated: dict, node2FuncId: dict,
                 funcBodyDict: dict):
        """初始化路径搜索需要的信息
        :param Cfg:cfg
        :param uncondJumpEdges: 无条件跳转边，格式为： [e1,e2]
        :param isLoopRelated:一个映射，记录节点是否为环相关
        :param node2FuncId:一个映射，记录节点对应的函数id
        :param funcBodyDict:一个映射，格式为： funcId:[函数包含的节点offset]
        """
        self.cfg = cfg
        self.blocks = cfg.blocks
        self.nodes = list(cfg.blocks.keys())
        self.edges = cfg.edges
        self.beginNode = cfg.initBlockId
        self.uncondJumpEdges = {}  # 记录调用边信息。格式为 "[起始点的offset，终止点的offset]":边对象
        for e in uncondJumpEdges:
            key = [e.beginNode, e.targetNode].__str__()
            self.uncondJumpEdges[key] = e
        self.isLoopRelated = isLoopRelated  # 函数内scc信息
        self.node2FuncId = node2FuncId  # 用于检测递归调用和scc访问控制，注意，不是函数的节点会被标成None
        self.funcBodyDict = funcBodyDict  # 用于检测递归调用
        self.isInvalidNode = dict(zip(self.nodes, [False for i in range(self.nodes.__len__())]))  # 某个节点是否是invalid
        self.sccVisiting = {}  # 基于返回地址栈的访问控制，格式： 函数调用链字符串:访问控制dict
        # 解释一下，不能使用基于函数调用链的scc访问控制，否则当出现循环内调用函数的时候，会出现死循环

        self.jumpEdgeInfo = []  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]]
        self.pathId = 0  # 路径的id
        self.paths = []  # 记录寻找到的路径，格式为路径对象

        # copdcopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]

        self.codecopyInfo = []
        self.log = Logger()

        # 控制搜索深度，增加超时/路径爆炸限制
        sys.setrecursionlimit(2000)  # 设置最大递归深度
        self.timeoutLimit = 600  # 最大搜索时间，设置为10min
        self.beginTime = None  # 开始搜索时间
        self.maxPathNum = 400000  # 40w

    def genPath(self):
        # dfs寻路
        self.beginTime = time.perf_counter()  # 记录开始时间
        self.__dfs(self.beginNode, TagStack(self.cfg), Stack(), Stack(), SimplifiedExecutor(self.cfg),
                   [-1])  # 函数调用链放个-1，防止为空，实际是从0开始的

        # 因为得到的跳转信息和codecopy信息有可能是重复的，这里需要做一个去重处理
        tempDict = {}
        for info in self.jumpEdgeInfo:
            tempDict[info.__str__()] = info
        self.jumpEdgeInfo = list(tempDict.values())
        tempDict = {}
        for info in self.codecopyInfo:
            tempDict[info.__str__()] = info
        self.codecopyInfo = list(tempDict.values())
        # 再检查一下得到的跳转边信息是否有漏缺
        infoNum = 0
        for block in self.blocks.values():
            if block.jumpType == "unconditional":  # 可能有多个出边，每一个出边都应该由一个push和一个jump来组成
                infoNum += block.jumpDest.__len__()
            elif block.jumpType == "conditional":  # 只有两个出边
                infoNum += 1  # 一次push即可
        assert infoNum == self.jumpEdgeInfo.__len__(), "{},{}".format(infoNum, self.jumpEdgeInfo.__len__())

    # 使用符号执行器进行dfs
    def __dfs(self, curNode: int, parentTagStack: TagStack, parentReturnAddrStack: Stack, parentPathRecorder: Stack,
              parentExecutor: SimplifiedExecutor, curCallChain: list):

        """
        根据简化版的符号执行器，来进行搜索
        """

        # 先检查有没有超时
        curTime = time.perf_counter()
        if curTime - self.beginTime > self.timeoutLimit:  # 超时
            self.log.fail("路径搜索超时，放弃优化")
            exit(0)

        '''
        如何对scc进行访问限制，是一个问题
        如果用函数调用链来标识访问限制，那么在循环里调用函数的时候，会出现死循环
        这就是一个错误的例子：curCallChainStr = curCallChain.__str__()
        应该使用返回地址栈来进行标识，然而这是不严谨的方法，例如
        例如：
        f(int a){
            if(a > 0){
                g();
            }
            g();
        }
        
        g(){
            while.... # 一个循环体
        }
        
        当调用f(-1)和f(1)的时候，它们在第一次进入函数体g时，使用的访问限制是相同的
        '''
        curCallChainStr = str(parentReturnAddrStack.getStack())
        if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
            if curCallChainStr not in self.sccVisiting.keys():  # 还没有建立访问限制
                self.sccVisiting[curCallChainStr] = dict(
                    zip(self.nodes, [False for i in range(0, len(self.nodes))]))
            elif self.sccVisiting[curCallChainStr][curNode]:  # 访问限制已经建立，检查当前节点是否在当前函数调用链下被调用过。如果调用过就直接返回，不访问了
                return
            # 将当前节点设置为当前函数调用链下已访问
            self.sccVisiting[curCallChainStr][curNode] = True

        # 第一步，复制父节点的状态
        curTagStack = TagStack(self.cfg)
        curTagStack.setTagStack(parentTagStack.getTagStack())
        curReturnAddrStack = Stack()
        curReturnAddrStack.setStack(parentReturnAddrStack.getStack())
        curPathRecorder = Stack()
        curPathRecorder.setStack(parentPathRecorder.getStack())
        curPathRecorder.push(curNode)
        curExecutor = SimplifiedExecutor(self.cfg)
        curExecutor.setExecutorState(parentExecutor.getExecutorState())

        # 第二步，进行符号执行和tagstack执行
        curTagStack.setBeginBlock(curNode)
        curExecutor.setBeginBlock(curNode)
        pushInfo = None  # block末尾处的push信息
        while not curExecutor.allInstrsExecuted():
            opcode = curExecutor.getOpcode()
            if opcode == 0xfe:  # invalid
                # 在记录路径信息之前，检查路径是不是爆炸了
                if len(self.paths) > self.maxPathNum:
                    self.log.fail("路径数量超出最大限制，放弃优化")
                    exit(0)
                # 记录路径信息
                path = Path(self.pathId, curPathRecorder.getStack())
                self.paths.append(path)
                self.pathId += 1
                # 不必往下走，直接返回
                if self.isLoopRelated[curNode]:
                    self.sccVisiting[curCallChainStr][curNode] = False
                return
            elif opcode == 0x39:  # codecopy
                # 不对offset和size做任何检查，检查留给优化工作去做
                tmpOffset = curTagStack.getTagStackItem(1)
                tmpSize = curTagStack.getTagStackItem(2)
                tmpOffset.extend(tmpSize)
                tmpOffset.append(curNode)
                self.codecopyInfo.append(tmpOffset)
            if curExecutor.isLastInstr() and self.blocks[curNode].jumpType not in ["terminal",
                                                                                   "fall"]:  # uncondjump/jumpi
                pushInfo = curTagStack.getTagStackTop()  # [push的值，push的字节数,push指令的地址，push指令所在的block]
                # 检查一下，两个栈的值相不相等
                stackTopInfo = curExecutor.getTagStackTop()
                assert stackTopInfo is not None  # 应该是一个确定的数
                assert pushInfo[0] in self.nodes  # 必须是一个block的offset
                assert stackTopInfo == pushInfo[0]  # 两个执行器的结果应该一致
            curExecutor.execNextOpCode()
            curTagStack.execNextOpCode()

        # 第三步，根据跳转的类型，记录跳转边的信息
        if self.blocks[curNode].jumpType in ["unconditional", "conditional"]:  # 是一条跳转边
            pushInfo.append(curNode)  # 添加一条信息，就是jump所在的block
            self.jumpEdgeInfo.append(pushInfo)
        elif self.blocks[curNode].jumpType == "terminal":  # 应当立即返回，不必再往下走
            if self.isLoopRelated[curNode]:
                self.sccVisiting[curCallChainStr][curNode] = False
            return

        # 第四步，继续进行dfs
        # 如果出边会造成环形函数调用，则直接报错
        if self.blocks[curNode].jumpType == "unconditional":
            targetNode = pushInfo[0]  # 即将跳往的目的block
            jumpEdge = self.uncondJumpEdges[[curNode, targetNode].__str__()]
            if jumpEdge.isCallerEdge:  # 是一条调用边
                if curReturnAddrStack.hasItem(jumpEdge.tetrad[1]):
                    # 如果返回地址栈中已经有了返回地址，则说明这个函数被调用过而且还没被返回，出现了环形函数调用的情况，此时需要放弃优化
                    self.log.fail("检测到环形函数调用链的情况，字节码无法被优化")
                    exit(0)
                # 栈中没有返回地址，可以调用
                curReturnAddrStack.push(jumpEdge.tetrad[1])  # push返回地址
                newCallChain = list(curCallChain)
                newCallChain.append(self.node2FuncId[jumpEdge.targetNode])  # 将新函数的函数id加入函数调用链
                self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, curExecutor, newCallChain)
                curReturnAddrStack.pop()  # 已经走完了，返回信息栈需要pop掉这一个返回信息
            elif jumpEdge.isReturnEdge:  # 是一条返回边
                # 栈里必须还有地址，而且和之前push的返回地址相同
                assert not curReturnAddrStack.empty() and targetNode == curReturnAddrStack.getTop()
                stackTop = curReturnAddrStack.getTop()  # 保存之前的返回地址，防止栈因为走向终止节点而被清空
                curReturnAddrStack.pop()  # 模拟返回后的效果
                self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, curExecutor,
                           list(curCallChain))  # 返回
                curReturnAddrStack.push(stackTop)
            else:  # 是一条普通的uncondjump边
                self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, curExecutor,
                           list(curCallChain))
        elif self.blocks[curNode].jumpType == "conditional":
            targetNode = pushInfo[0]
            # 两条边都走一次
            self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, curExecutor, list(curCallChain))
            self.__dfs(curNode + self.blocks[curNode].length, curTagStack, curReturnAddrStack, curPathRecorder,
                       curExecutor,list(curCallChain))
        elif self.blocks[curNode].jumpType == "fall":
            targetNode = curNode + self.blocks[curNode].length
            self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, curExecutor, list(curCallChain))
        else:  # terminal，前面已经返回了
            assert 0  # 返回

        # 第五步，消除访问限制并返回父节点
        if self.isLoopRelated[curNode]:
            self.sccVisiting[curCallChainStr][curNode] = False


    # def __dfs(self, curNode: int, parentTagStack: TagStack, parentReturnAddrStack: Stack, parentPathRecorder: Stack,
    #           curCallChain: list):
    #     # 按照tagStack的结果进行路径搜索
    #
    #     # 先检查有没有超时
    #     curTime = time.perf_counter()
    #     if curTime - self.beginTime > self.timeoutLimit:# 超时
    #         self.log.fail("路径搜索超时，放弃优化")
    #         exit(0)
    #
    #     curTagStack = TagStack(self.cfg)
    #     curTagStack.setTagStack(parentTagStack.getTagStack())
    #     curReturnAddrStack = Stack()
    #     curReturnAddrStack.setStack(parentReturnAddrStack.getStack())
    #     curPathRecorder = Stack()
    #     curPathRecorder.setStack(parentPathRecorder.getStack())
    #     curPathRecorder.push(curNode)
    #
    #     # 第一步，检查当前是否进入了scc，若是，则要修改访问控制
    #     curCallChainStr = curCallChain.__str__()  # 函数调用链的字符串
    #     if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
    #         if curCallChainStr not in self.sccVisiting.keys():  # 还没有建立访问控制
    #             self.sccVisiting[curCallChainStr] = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))
    #         elif self.sccVisiting[curCallChainStr][curNode]:  # 访问限制已经建立，检查当前节点是否在当前函数调用链下被调用过。如果调用过就直接返回，不访问了
    #             return
    #         # 将当前节点设置为当前函数调用链下已访问
    #         self.sccVisiting[curCallChainStr][curNode] = True
    #
    #     # 第二步，进行tagstack执行，这一步需要复制父节点的tagstack信息
    #     curTagStack.setBeginBlock(curNode)
    #     pushInfo = None
    #     while not curTagStack.allInstrsExecuted():
    #         opcode = curTagStack.getOpcode()
    #         if opcode == 0xfe:  # invalid
    #             # 在记录路径信息之前，检查路径是不是爆炸了
    #             if len(self.paths) > self.maxPathNum:
    #                 self.log.fail("路径数量超出最大限制，放弃优化")
    #                 exit(0)
    #             # 记录路径信息
    #             path = Path(self.pathId, curPathRecorder.getStack())
    #             self.paths.append(path)
    #             self.pathId += 1
    #             # 不必往下走，直接返回
    #             if self.isLoopRelated[curNode]:
    #                 self.sccVisiting[curCallChainStr][curNode] = False
    #             return
    #         elif opcode == 0x39:  # codecopy
    #             # 不对offset和size做任何检查，检查留给优化工作去做
    #             tmpOffset = curTagStack.getTagStackItem(1)
    #             tmpSize = curTagStack.getTagStackItem(2)
    #             tmpOffset.extend(tmpSize)
    #             tmpOffset.append(curNode)
    #             self.codecopyInfo.append(tmpOffset)
    #         if curTagStack.isLastInstr() and self.blocks[curNode].jumpType not in ["terminal", "fall"]:
    #             pushInfo = curTagStack.getTagStackTop()  # [push的值，push的字节数,push指令的地址，push指令所在的block]
    #         curTagStack.execNextOpCode()
    #
    #     # 第三步，根据跳转的类型，记录跳转边的信息
    #     if self.blocks[curNode].jumpType in ["unconditional", "conditional"]:  # 是一条跳转边
    #         if pushInfo[0] is None:
    #             self.log.fail(
    #                 "跳转地址经过了计算，拒绝优化，跳转信息为：{}，当前路径为:{}".format(pushInfo, curPathRecorder.getTagStack().__str__()))
    #             exit(0)
    #         assert pushInfo[0] in self.nodes and pushInfo[0] in self.edges[curNode] # 必须是一个块的offset，而且必须是当前块指向的某个块
    #         pushInfo.append(curNode)  # 添加一条信息，就是jump所在的block
    #         self.jumpEdgeInfo.append(pushInfo)
    #     elif self.blocks[curNode].jumpType == "terminal":  # 应当立即返回，不必再往下走
    #         if self.isLoopRelated[curNode]:
    #             self.sccVisiting[curCallChainStr][curNode] = False
    #         return
    #
    #     # 第四步，继续进行dfs
    #     # 如果出边会造成环形函数调用，或者是函数内scc死循环，则不走这些出边
    #     # 否则，需要进行出边遍历
    #     if self.blocks[curNode].jumpType == "unconditional":
    #         targetNode = pushInfo[0]  # 即将跳往的目的block
    #         jumpEdge = self.uncondJumpEdges[[curNode, targetNode].__str__()]
    #         if jumpEdge.isCallerEdge:  # 是一条调用边
    #             if curReturnAddrStack.hasItem(jumpEdge.tetrad[1]):
    #                 # 如果返回地址栈中已经有了返回地址，则说明这个函数被调用过而且还没被返回，出现了环形函数调用的情况，此时需要放弃优化
    #                 self.log.fail("检测到环形函数调用链的情况，字节码无法被优化")
    #                 exit(0)
    #             # 栈中没有返回地址，可以调用
    #             curReturnAddrStack.push(jumpEdge.tetrad[1])  # push返回地址
    #             newCallChain = list(curCallChain)
    #             newCallChain.append(self.node2FuncId[jumpEdge.targetNode])  # 将新函数的函数id加入函数调用链
    #             self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, newCallChain)
    #             curReturnAddrStack.pop()  # 已经走完了，返回信息栈需要pop掉这一个返回信息
    #         elif jumpEdge.isReturnEdge:  # 是一条返回边
    #             # 栈里必须还有地址，而且和之前push的返回地址相同
    #             assert not curReturnAddrStack.empty() and targetNode == curReturnAddrStack.getTop()
    #             stackTop = curReturnAddrStack.getTop()  # 保存之前的返回地址，防止栈因为走向终止节点而被清空
    #             curReturnAddrStack.pop()  # 模拟返回后的效果
    #             self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))  # 返回
    #             curReturnAddrStack.push(stackTop)
    #         else:  # 是一条普通的uncondjump边
    #             self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))
    #     elif self.blocks[curNode].jumpType == "conditional":
    #         targetNode = pushInfo[0]
    #         # 两条边都走一次
    #         self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))
    #         self.__dfs(curNode + self.blocks[curNode].length, curTagStack, curReturnAddrStack, curPathRecorder,
    #                    list(curCallChain))
    #     elif self.blocks[curNode].jumpType == "fall":
    #         targetNode = curNode + self.blocks[curNode].length
    #         self.__dfs(targetNode, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))
    #     else:  # terminal，前面已经返回了
    #         assert 0  # 返回
    #
    #     if self.isLoopRelated[curNode]:
    #         self.sccVisiting[curCallChainStr][curNode] = False

    # # 原来的dfs，会路径爆炸
    # def __dfs(self, curNode: int, parentTagStack: TagStack, parentReturnAddrStack: Stack, parentPathRecorder: Stack,
    #           curCallChain: list):
    #     """
    #     路径记录：每访问一个新节点，则将其加入到路径栈，离开时pop一次(其实就是pop自己)
    #     访问控制：每访问一个新节点，则将其设置为true状态，退出时设置为false
    #     """
    #
    #     # 先检查有没有超时
    #     curTime = time.perf_counter()
    #     if curTime - self.beginTime > self.timeoutLimit:# 超时
    #         self.log.fail("路径搜索超时，放弃优化")
    #         exit(0)
    #
    #     curTagStack = TagStack(self.cfg)
    #     curTagStack.setTagStack(parentTagStack.getTagStack())
    #     curReturnAddrStack = Stack()
    #     curReturnAddrStack.setStack(parentReturnAddrStack.getStack())
    #     curPathRecorder = Stack()
    #     curPathRecorder.setStack(parentPathRecorder.getStack())
    #     curPathRecorder.push(curNode)
    #
    #     # 第一步，检查当前是否进入了scc，若是，则要修改访问控制
    #     curCallChainStr = curCallChain.__str__()  # 函数调用链的字符串
    #     if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
    #         if curCallChainStr not in self.sccVisiting.keys():  # 还没有建立访问控制
    #             self.sccVisiting[curCallChainStr] = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))
    #         elif self.sccVisiting[curCallChainStr][curNode]:  # 访问限制已经建立，检查当前节点是否在当前函数调用链下被调用过。如果调用过就直接返回，不访问了
    #             return
    #         # 将当前节点设置为当前函数调用链下已访问
    #         self.sccVisiting[curCallChainStr][curNode] = True
    #
    #     # 第二步，进行tagstack执行，这一步需要复制父节点的tagstack信息
    #     curTagStack.setBeginBlock(curNode)
    #     pushInfo = None
    #     while not curTagStack.allInstrsExecuted():
    #         opcode = curTagStack.getOpcode()
    #         if opcode == 0xfe:  # invalid
    #             # 在记录路径信息之前，检查路径是不是爆炸了
    #             if len(self.paths) > self.maxPathNum:
    #                 self.log.fail("路径数量超出最大限制，放弃优化")
    #                 exit(0)
    #             # 记录路径信息
    #             path = Path(self.pathId, curPathRecorder.getStack())
    #             self.paths.append(path)
    #             self.pathId += 1
    #             # 不必往下走，直接返回
    #             if self.isLoopRelated[curNode]:
    #                 self.sccVisiting[curCallChainStr][curNode] = False
    #             return
    #         elif opcode == 0x39:  # codecopy
    #             # 不对offset和size做任何检查，检查留给优化工作去做
    #             tmpOffset = curTagStack.getTagStackItem(1)
    #             tmpSize = curTagStack.getTagStackItem(2)
    #             tmpOffset.extend(tmpSize)
    #             tmpOffset.append(curNode)
    #             self.codecopyInfo.append(tmpOffset)
    #         if curTagStack.isLastInstr() and self.blocks[curNode].jumpType not in ["terminal",
    #                                                                                "fall"]:  # uncondjump/jumpi
    #             pushInfo = curTagStack.getTagStackTop()  # [push的值，push的字节数,push指令的地址，push指令所在的block]
    #         curTagStack.execNextOpCode()
    #
    #     # 第三步，根据跳转的类型，记录跳转边的信息
    #     if self.blocks[curNode].jumpType in ["unconditional", "conditional"]:  # 是一条跳转边
    #         if pushInfo[0] is None:
    #             self.log.fail(
    #                 "跳转地址经过了计算，拒绝优化，跳转信息为：{}，当前路径为:{}".format(pushInfo, curPathRecorder.getTagStack().__str__()))
    #             exit(0)
    #         assert pushInfo[0] in self.nodes and pushInfo[0] in self.edges[curNode] # 必须是一个block的offset
    #         pushInfo.append(curNode)  # 添加一条信息，就是jump所在的block
    #         self.jumpEdgeInfo.append(pushInfo)
    #     elif self.blocks[curNode].jumpType == "terminal":  # 应当立即返回，不必再往下走
    #         if self.isLoopRelated[curNode]:
    #             self.sccVisiting[curCallChainStr][curNode] = False
    #         return
    #
    #     # 第四步，查看每一条出边
    #     # 如果出边会造成环形函数调用，或者是函数内scc死循环，则不走这些出边
    #     # 否则，需要进行出边遍历
    #     for node in self.edges[curNode]:  # 查看每一个出边
    #         if self.isLoopRelated[node]:  # 是一个环相关节点
    #             if curCallChainStr in self.sccVisiting.keys():
    #                 if self.sccVisiting[curCallChainStr][node]:  # 这个点已经访问过
    #                     continue
    #         key = [curNode, node].__str__()
    #         if key in self.uncondJumpEdges.keys():  # 这是一条uncondjump边，但是不确定是调用边还是返回边
    #             e = self.uncondJumpEdges[key]
    #             if e.isCallerEdge:  # 是一条调用边
    #                 if curReturnAddrStack.hasItem(e.tetrad[1]):
    #                     # 如果栈中有返回地址，则说明这个函数被调用过而且还没被返回，出现了环形函数调用的情况，此时需要放弃优化
    #                     self.log.fail("检测到环形函数调用链的情况，字节码无法被优化")
    #                     exit(0)
    #                 curReturnAddrStack.push(e.tetrad[1])  # push返回地址
    #                 newCallChain = list(curCallChain)
    #                 newCallChain.append(self.node2FuncId[e.targetNode])  # 将新函数的函数id加入函数调用链
    #                 self.__dfs(node, curTagStack, curReturnAddrStack, curPathRecorder, newCallChain)
    #                 curReturnAddrStack.pop()  # 已经走完了，返回信息栈需要pop掉这一个返回信息
    #             elif e.isReturnEdge:  # 是一条返回边
    #                 if curReturnAddrStack.empty():  # 栈里必须还有地址
    #                     continue
    #                 if e.tetrad[3] != curReturnAddrStack.getTop():  # 和之前push的返回地址相同，才能做返回
    #                     continue
    #                 stackTop = curReturnAddrStack.getTop()  # 保存之前的返回地址，防止栈因为走向终止节点而被清空
    #                 curReturnAddrStack.pop()  # 模拟返回后的效果
    #                 self.__dfs(node, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))  # 返回
    #                 curReturnAddrStack.push(stackTop)
    #             else:  # 是一条普通的uncondjump边
    #                 # 6.4新问题：之前已经获取到了pushInfo，应当按照pushInfo[0]来跳，而不是瞎跳
    #                 if node != pushInfo[0]:  # 不是tagStack执行后，应当出现的跳转边
    #                     continue
    #                 self.__dfs(node, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))
    #         else:  # 不是unconditional jump
    #             # 如果是jumpi，则随便挑一边跳
    #             # 不可能是terminal，上面遇到terminal就直接返回了
    #             self.__dfs(node, curTagStack, curReturnAddrStack, curPathRecorder, list(curCallChain))
    #
    #     if self.isLoopRelated[curNode]:
    #         self.sccVisiting[curCallChainStr][curNode] = False

    def getPath(self):
        return self.paths


    def getJumpEdgeInfo(self):
        return self.jumpEdgeInfo


    def getCodecopyInfo(self):
        return self.codecopyInfo
