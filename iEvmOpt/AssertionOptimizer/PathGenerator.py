# 用于生成有向图中任意两点之间的所有路径
# 返回的格式为：[[路径1从起点到终点经过的点],[路径1从起点到终点经过的点]...]
# 需要注意，图中是没有有向环的
from AssertionOptimizer.Path import Path
from Cfg.Cfg import Cfg
from Utils import Stack
from Utils.Logger import Logger
from AssertionOptimizer.TagStacks.TagStack import TagStack


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
        # self.sccVisiting = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 记录某个函数内scc是否正在被访问
        self.sccVisiting = {}  # 基于返回地址栈的访问控制，格式： 返回地址栈字符串:访问控制dict
        # 解释一下，不能使用基于函数调用链的scc访问控制，否则当出现循环内调用函数的时候，会出现死循环

        self.jumpEdgeInfo = []  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]]
        self.pathRecorder = Stack()
        self.returnAddrStack = Stack()
        self.pathId = 0  # 路径的id
        self.paths = []  # 记录寻找到的路径，格式为路径对象

        # copdcopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]

        self.codecopyInfo = []
        self.log = Logger()
        # print(self.node2FuncId)
        # print(self.isLoopRelated)

    def genPath(self):
        '''
        该函数需要做两件事：
        做一遍修改过的dfs，旨在获取所有的invalid路径，这些路径是符合函数调用关系的
        :param begin:路径搜索的起始节点
        :param target:路径搜索的终止节点
        :return:[路径1的点组成的list，路径2的点组成的list....]
        '''
        # dfs寻路

        self.__dfs(self.beginNode, TagStack(self.cfg))

        # 因为得到的跳转信息和codecopy信息有可能是重复的，这里需要做一个去重处理
        tempDict = {}
        for info in self.jumpEdgeInfo:
            tempDict[info.__str__()] = info
        self.jumpEdgeInfo = list(tempDict.values())
        tempDict = {}
        for info in self.codecopyInfo:
            tempDict[info.__str__()] = info
        self.codecopyInfo = list(tempDict.values())
        # for b in self.blocks.values():
        #     b.printBlockInfo()
        # for e in self.uncondJumpEdges.values():
        #     e.output()
        # 再检查一下得到的跳转边信息是否有漏缺
        infoNum = 0
        for block in self.blocks.values():
            # block.printBlockInfo()
            if block.jumpType == "unconditional":  # 可能有多个出边，每一个出边都应该由一个push和一个jump来组成
                infoNum += block.jumpDest.__len__()
            elif block.jumpType == "conditional":  # 只有两个出边
                infoNum += 1  # 一次push即可
        assert infoNum == self.jumpEdgeInfo.__len__(), "{},{}".format(infoNum, self.jumpEdgeInfo.__len__())

    def __dfs(self, curNode: int, parentTagStack: TagStack):
        """
        路径记录：每访问一个新节点，则将其加入到路径栈，离开时pop一次(其实就是pop自己)
        访问控制：每访问一个新节点，则将其设置为true状态，退出时设置为false
        """
        # print(curNode)
        self.pathRecorder.push(curNode)

        # 第一步，检查当前是否进入了scc，若是，则要修改访问控制
        curReturnAddrStackStr = self.returnAddrStack.getStack().__str__()  # 返回地址栈的字符串
        if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
            if curReturnAddrStackStr not in self.sccVisiting.keys():  # 还没有建立访问控制
                self.sccVisiting[curReturnAddrStackStr] = dict(
                    zip(self.nodes, [False for i in range(0, len(self.nodes))]))
            self.sccVisiting[curReturnAddrStackStr][curNode] = True

        # 第二步，进行tagstack执行，这一步需要复制父节点的tagstack信息
        curTagStack = TagStack(self.cfg)
        curTagStack.setTagStack(parentTagStack.getTagStack())
        curTagStack.setBeginBlock(curNode)
        pushInfo = None
        while not curTagStack.allInstrsExecuted():
            opcode = curTagStack.getOpcode()
            if opcode == 0xfe:  # invalid
                path = Path(self.pathId, self.pathRecorder.getStack())
                self.paths.append(path)
                self.pathId += 1
                # 不必往下走，直接返回
                self.pathRecorder.pop()
                if self.isLoopRelated[curNode]:
                    self.sccVisiting[curReturnAddrStackStr][curNode] = False
                return
            elif opcode == 0x39:  # codecopy
                tmpOffset = curTagStack.getTagStackItem(1)
                tmpSize = curTagStack.getTagStackItem(2)
                assert tmpOffset is not None, "cur PC:{},path:{}".format(curTagStack.PC, self.pathRecorder.getStack())
                assert tmpSize is not None, "cur PC:{},path:{}".format(curTagStack.PC, self.pathRecorder.getStack())
                tmpOffset.extend(tmpSize)
                tmpOffset.append(curNode)
                self.codecopyInfo.append(tmpOffset)
            if curTagStack.isLastInstr():
                pushInfo = curTagStack.getTagStackTop()  # [push的值，push指令的地址，push指令所在的block]
            curTagStack.execNextOpCode()

        # 第三步，根据跳转的类型，记录跳转边的信息
        if self.blocks[curNode].jumpType in ["unconditional", "conditional"]:  # 是一条跳转边
            if pushInfo is None:
                self.log.fail("跳转地址经过了计算，拒绝优化")
            assert pushInfo[0] in self.nodes  # 必须是一个block的offset
            pushInfo.append(curNode)  # 添加一条信息，就是jump所在的block
            self.jumpEdgeInfo.append(pushInfo)
            # if curNode == 636:
            #     print(pushInfo)

        # 第四步，查看每一条出边
        # 如果出边会造成环形函数调用，或者是函数内scc死循环，则不走这些出边
        # 否则，需要进行出边遍历
        for node in self.edges[curNode]:  # 查看每一个出边
            if self.isLoopRelated[node]:  # 是一个环相关节点
                if curReturnAddrStackStr in self.sccVisiting.keys():
                    if self.sccVisiting[curReturnAddrStackStr][node]:  # 这个点已经访问过
                        continue
            key = [curNode, node].__str__()
            if key in self.uncondJumpEdges.keys():  # 这是一条uncondjump边，但是不确定是调用边还是返回边
                e = self.uncondJumpEdges[key]
                if e.isCallerEdge:  # 是一条调用边
                    # 可以是环相关的点，循环内调用函数也可以
                    # if self.isLoopRelated[node]:  # 不能是环相关的点，例如循环内调用函数，会出现无限递归的情况
                    #     continue
                    if self.returnAddrStack.hasItem(
                            e.tetrad[1]):  # 如果是已经调用过的函数，则说明出现了环形函数调用的情况，此时需要放弃优化
                        # 找出所有环相关的函数，用于报错
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
                        self.log.fail(
                            "检测到环形函数调用链的情况，涉及的函数id有：{}，字节码无法被优化".format([i for i in callLoopRelatedFuncId.keys()]))
                        # 程序已经结束了
                    self.returnAddrStack.push(e.tetrad[1])  # push返回地址
                    self.__dfs(node, curTagStack)
                    # 已经走完了，返回信息栈需要pop掉这一个返回信息
                    self.returnAddrStack.pop()
                elif e.isReturnEdge:  # 是一条返回边
                    if self.returnAddrStack.empty():  # 栈里必须还有地址
                        continue
                    if e.tetrad[3] != self.returnAddrStack.getTop():  # 和之前push的返回地址相同，才能做返回
                        continue
                    stackItems = self.returnAddrStack.getStack()  # 保存之前的栈，防止栈因为走向终止节点而被清空
                    self.returnAddrStack.pop()  # 模拟返回后的效果
                    self.__dfs(node, curTagStack)  # 返回
                    self.returnAddrStack.setStack(stackItems)  # 如果走到过终点，则当前函数的返回地址以及前面函数的返回地址都没了，需要恢复
                else:  # 是一条普通的uncondjump边
                    self.__dfs(node, curTagStack)
            else:  # 不是unconditional jump
                self.__dfs(node, curTagStack)

        self.pathRecorder.pop()
        if self.isLoopRelated[curNode]:
            self.sccVisiting[curReturnAddrStackStr][curNode] = False

    def getPath(self):
        return self.paths

    def getJumpEdgeInfo(self):
        return self.jumpEdgeInfo

    def getCodecopyInfo(self):
        return self.codecopyInfo
