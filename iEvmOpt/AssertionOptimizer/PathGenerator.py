# 用于生成有向图中任意两点之间的所有路径
# 返回的格式为：[[路径1从起点到终点经过的点],[路径1从起点到终点经过的点]...]
# 需要注意，图中是没有有向环的
from AssertionOptimizer.Path import Path
from Cfg.Cfg import Cfg
from Utils import Stack
from AssertionOptimizer.JumpEdge import JumpEdge
from Utils.Logger import Logger
from AssertionOptimizer.TagStack import TagStack


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
        self.node2FuncId = node2FuncId  # 用于检测递归调用
        self.funcBodyDict = funcBodyDict  # 用于检测递归调用
        self.isInvalidNode = dict(zip(self.nodes, [False for i in range(self.nodes.__len__())]))  # 某个节点是否是invalid
        self.sccVisiting = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 记录某个函数内scc是否正在被访问

        self.jumpEdgeInfo = []  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]]
        self.pathRecorder = Stack()
        self.returnAddrStack = Stack()
        self.pathId = 0  # 路径的id
        self.paths = []  # 记录寻找到的路径，格式为路径对象

        # copdcopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]

        self.codecopyInfo = []
        self.log = Logger()

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

        # 因为得到的跳转信息有可能是重复的，这里需要做一个去重处理
        tempDict = {}
        for info in self.jumpEdgeInfo:
            tempDict[info.__str__()] = info
        self.jumpEdgeInfo = list(tempDict.values())
        # 再检查一下得到的跳转边信息是否有漏缺
        infoNum = 0
        for block in self.blocks.values():
            if block.jumpType == "unconditional":  # 可能有多个出边，每一个出边都应该由一个push和一个jump来组成
                infoNum += block.jumpDest.__len__()
            elif block.jumpType == "conditional":  # 只有两个出边
                infoNum += 1  # 一次push即可

        # for info in self.jumpEdgeInfo:
        #     print(info)
        # for path in self.paths:
        #     path.printPath()
        # self.uncondJumpEdges[[142,198].__str__()].output()
        assert infoNum == self.jumpEdgeInfo.__len__()

    def __dfs(self, curNode: int, parentTagStack: TagStack):
        """
        路径记录：每访问一个新节点，则将其加入到路径栈，离开时pop一次(其实就是pop自己)
        访问控制：每访问一个新节点，则将其设置为true状态，退出时设置为false
        """
        # print(curNode)
        self.pathRecorder.push(curNode)
        if self.isLoopRelated[curNode]:  # 当前访问的是一个scc，需要将其标记为true，防止死循环
            self.sccVisiting[curNode] = True

        # 第一步，进行tagstack执行，这一步需要复制父节点的tagstack信息
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
                self.sccVisiting[curNode] = False
                return
            elif opcode == 0x39:  # codecopy
                tmpOffset = curTagStack.getTagStackItem(1)
                tmpSize = curTagStack.getTagStackItem(2)
                assert tmpOffset is not None
                assert tmpSize is not None
                tmpOffset.extend(tmpSize)
                tmpOffset.append(curNode)
                self.codecopyInfo.append(tmpOffset)
            if curTagStack.isLastInstr():
                pushInfo = curTagStack.getTagStackTop()  # [push的值，push指令的地址，push指令所在的block]
            curTagStack.execNextOpCode()

        # 第二步，根据跳转的类型，记录跳转边的信息
        if self.blocks[curNode].jumpType in ["unconditional", "conditional"]:  # 是一条跳转边
            if pushInfo is None:
                self.log.fail("跳转地址经过了计算，拒绝优化")
            assert pushInfo[0] in self.nodes  # 必须是一个block的offset
            pushInfo.append(curNode)  # 添加一条信息，就是jump所在的block
            self.jumpEdgeInfo.append(pushInfo)

        # 第三步，查看每一条出边
        # 如果出边会造成环形函数调用，或者是函数内scc死循环，则不走这些出边
        # 否则，需要进行出边遍历
        for node in self.edges[curNode]:  # 查看每一个出边
            if self.sccVisiting[node]:  # 防止循环内调用函数造成死循环
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
                            "检测到环形函数调用链的情况，涉及的函数id有：{}".format([i for i in callLoopRelatedFuncId.keys()]))
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
        self.sccVisiting[curNode] = False

    def getPath(self):
        return self.paths

    def getJumpEdgeInfo(self):
        return self.jumpEdgeInfo

    def getCodecopyInfo(self):
        return self.codecopyInfo
