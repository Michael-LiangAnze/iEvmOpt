from collections import deque

from z3 import *

from AssertionOptimizer.Function import Function
from AssertionOptimizer.Path import Path
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from AssertionOptimizer.JumpEdge import JumpEdge
from GraphTools import DominatorTreeBuilder
from GraphTools.GraphMapper import GraphMapper
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from AssertionOptimizer.PathGenerator import PathGenerator
from Utils import Stack
import json
from Utils.Logger import Logger

# 调试用
fullyRedundant = "fullyRedundant"
partiallyRedundant = "partiallyRedundant"


# fullyRedundant = 0
# partiallyRedundant = 1


class AssertionOptimizer:
    def __init__(self, cfg: Cfg, inputFile: str, outputFile: str):
        self.cfg = cfg
        self.blocks = self.cfg.blocks  # 存储基本块，格式为 起始offset:BasicBlock
        self.inputFile = inputFile  # 处理前的文件
        self.outputFile = outputFile  # 处理后的新文件
        self.log = Logger()

        # 函数识别、处理时需要用到的信息
        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.edges = self.cfg.edges  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = self.cfg.inEdges  # 存储入边表，格式为 to:[from1,from2...]
        self.funcCnt = 0  # 函数计数
        self.funcBodyDict = {}  # 记录找到的所有函数，格式为：  funcId:function
        self.node2FuncId = dict(
            zip(self.nodes, [None for i in range(0, self.nodes.__len__())]))  # 记录节点属于哪个函数，格式为：  node：funcId
        self.isFuncBodyHeadNode = dict(
            zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 函数体头结点信息，用于后续做函数内环压缩时，判断某个函数是否存在递归的情况
        self.isLoopRelated = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 标记各个节点是否为loop-related
        self.isFuncCallLoopRelated = None  # 记录节点是否在函数调用环之内，该信息只能由路径搜索得到

        # 路径搜索需要用到的信息
        self.invalidNodeList = []  # 记录所有invalid节点的offset
        self.invalidPaths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidPathId:Path
        self.invalidNode2PathIds = {}  # 记录每个invalid节点包含的路径，格式为：  invalidNodeOffset:[pathId1,pathId2]
        self.invalidNode2CallChain = {}  # 记录每个invalid节点包含的调用链，格式为： invalidNodeOffset:[[callchain1中的pathid],[callchain2中的pathid]]

        # 可达性分析需要用到的信息
        self.pathReachable = {}  # 某条路径是否可达
        self.invNodeReachable = None  # 某个Invalid节点是否可达，格式为： invNode:True/Flase
        self.redundantType = {}  # 每个invalid节点的冗余类型，类型包括fullyredundant和partiallyredundant，格式为： invNode: type

        # 冗余assertion优化需要用到的信息
        self.domTree = {}  # 支配树。注意，为了方便从invalid节点往前做遍历，该支配树存储的是入边，格式为   to:from
        self.removedRange = dict(
            zip(self.nodes, [[] for i in range(0, len(self.nodes))]))  # 记录每个block中被移除的区间，每个区间的格式为:[from,to)

        # 重定位需要用到的信息
        self.jumpEdgeInfo = None  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]]
        self.originalLength = 0  # 原来的字节码总长度
        self.originalToNewAddr = {}  # 一个映射，格式为： 旧addr:新addr
        self.newBytecode = None  # 重新生成的字节码，用deque效率更高

    def optimize(self):
        self.log.info("开始进行字节码分析")

        # 首先识别出所有的函数体，将每个函数体内的强连通分量的所有点标记为loop-related
        self.__identifyAndCheckFunctions()
        self.log.info("函数体识别完毕，一共识别到:{}个函数体".format(self.funcCnt))

        # 然后找到所有invalid节点，找出他们到起始节点之间所有的边
        self.__searchPaths()

        callChainNum = 0
        for invNode in self.invalidNodeList:
            callChainNum += self.invalidNode2CallChain[invNode].__len__()
        self.log.info(
            "路径搜索完毕，一共找到{}个可优化的Invalid节点，一共找到{}条路径，{}条函数调用链".format(self.invalidNodeList.__len__(),
                                                                    self.invalidPaths.__len__(), callChainNum))

        # 求解各条路径是否可行
        self.log.info("正在分析路径可达性")
        self.__reachabilityAnalysis()
        self.log.info("可达性分析完毕")

        # 生成cfg的支配树
        self.__buildDominatorTree()

        # 根据冗余类型进行优化
        fullyRedundantNodes = []
        partiallyRedundantNodes = []
        for invNode, rType in self.redundantType.items():
            if rType == fullyRedundant:
                fullyRedundantNodes.append(invNode)
            else:
                partiallyRedundantNodes.append(invNode)
        if fullyRedundantNodes.__len__() == 0 and partiallyRedundantNodes.__len__() == 0:
            self.log.info("不存在可优化的Assertion，优化结束")

        self.log.info("一共找到{}个完全冗余的invalid节点，{}个部分冗余的invalid节点".format(fullyRedundantNodes.__len__(),
                                                                       partiallyRedundantNodes.__len__()))
        if fullyRedundantNodes.__len__() > 0:  # 存在完全冗余的节点
            self.log.info("正在对完全冗余的Assertion进行优化")
            self.__optimizeFullyRedundantAssertion(fullyRedundantNodes)
            self.log.info("完全冗余Assertion优化完毕")
        # if partiallyRedundantNodes.__len__() > 0:
        #     self.log.info("正在对部分冗余的Assertion进行优化")
        #     self.__optimizePartiallyRedundantAssertion(partiallyRedundantNodes)
        #     self.log.info("部分冗余Assertion优化完毕")

        # 重新生成字节码序列
        self.log.info("正在重新生成字节码序列")
        self.__regenerateBytecode()
        self.log.info("字节码序列生成完毕")

        # 将优化后的字节码写入文件
        self.log.info("正在将优化后的字节码写入到文件: {}".format(self.outputFile))
        self.__outputFile()
        self.log.info("写入完毕")

    def __identifyAndCheckFunctions(self):
        '''
        识别所有的函数
        给出三个基本假设：
        1. 同一个函数内的指令的地址都是从小到大连续的
        2. 任何函数调用的起始边，必然是伴随这样两条指令产生的：PUSH 返回地址;JUMP
        3. 任何函数调用的返回边，必然不是这样的结构：PUSH 返回地址;JUMP
        给出一个求解前提：
           我们不关心函数调用关系产生的“错误的环”，因为这种错误的环我们可以在搜索路径时，可以通过符号执行或者返回地址栈解决掉
        '''

        # 第一步，检查是否除了0号offset节点之外，是否还有节点没有入边,若有，则存在返回边错误，一般为递归情况
        for _to, _from in self.inEdges.items():
            if _to == self.cfg.initBlockId:
                continue
            if _from.__len__() == 0:
                self.log.warning("发现一个不是初始节点，但没有入边的Block: {}".format(_to))

        # 第二步，找出所有unconditional jump的边
        for n in self.cfg.blocks.values():
            if n.jumpType == "unconditional":
                _from = n.offset
                for _to in self.edges[_from]:  # 可能有几个出边
                    # 这里做一个assert，防止出现匹配到两个节点都在dispatcher里面的情况，但是真的有吗？先不处理
                    assert not (n.blockType == "dispatcher" and self.cfg.blocks[_to].blockType == "dispatcher")
                    e = JumpEdge(n, self.cfg.blocks[_to])
                    self.uncondJumpEdge.append(e)
        # for e in self.uncondJumpEdge:
        #     print(e.tetrad)

        # 第三步，两两之间进行匹配
        funcRange2Calls = {}  # 一个映射，格式为:
        # (一个字符串，内容为"[第一条指令所在的block的offset,最后一条指令所在的block的offset]"):[[funcbody调用者的起始node,funcbody返回边的目的node]]
        # 解释一下value为什么要存这个：如果发现出现了函数调用，那么就在其调用者调用前的节点和调用后的返回节点之间加一条边
        # 这样在使用dfs遍历一个函数内的所有节点时，就可以只看地址范围位于key内的节点，如果当前遍历的函数出现了函数调用，那么不需要进入调用的函数体，
        # 也能成功找到它的所有节点
        uncondJumpNum = len(self.uncondJumpEdge)
        for i in range(0, uncondJumpNum):
            for j in range(0, uncondJumpNum):
                if i == j:
                    pass
                e1, e2 = self.uncondJumpEdge[i], self.uncondJumpEdge[j]  # 取出两个不同的边进行匹配
                if e1.tetrad[0] == e2.tetrad[2] and e1.tetrad[1] == e2.tetrad[3] and e1.tetrad[
                    0] is not None:  # 匹配成功，e1为调用边，e2为返回边。注意None之间是不匹配的
                    e1.isCallerEdge = True
                    e2.isReturnEdge = True
                    self.isFuncBodyHeadNode[e1.targetNode] = True
                    key = [e1.targetNode, e2.beginNode].__str__()
                    value = [e1.beginNode, e2.targetNode]
                    if key not in funcRange2Calls.keys():
                        funcRange2Calls[key] = []
                    funcRange2Calls[key].append(value)
        # for i in funcRange2Calls.items():
        #     print(i)

        # 第四步，在caller的jump和返回的jumpdest节点之间加边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].append(pair[1])
                self.inEdges[pair[1]].append(pair[0])

        # 第五步，从一个函数的funcbody的起始block开始dfs遍历，只走offset范围在 [第一条指令所在的block的offset,最后一条指令所在的block的offset]之间的节点，尝试寻找出所有的函数节点
        for rangeInfo in funcRange2Calls.keys():  # 找到一个函数
            offsetRange = json.loads(rangeInfo)  # 还原之前的list
            offsetRange[1] += 1  # 不用每次调用range函数的时候都加
            funcBody = []
            stack = Stack()
            visited = {}
            visited[offsetRange[0]] = True
            stack.push(offsetRange[0])  # 既是范围一端，也是起始节点的offset
            while not stack.empty():  # dfs找出所有节点
                top = stack.pop()
                funcBody.append(top)
                for out in self.edges[top]:
                    if out not in visited.keys() and out in range(offsetRange[0], offsetRange[1]):
                        stack.push(out)
                        visited[out] = True
            # 存储函数信息
            self.funcCnt += 1
            offsetRange[1] -= 1
            f = Function(self.funcCnt, offsetRange[0], offsetRange[1], funcBody, self.edges)
            self.funcBodyDict[self.funcCnt] = f
            for node in funcBody:
                self.node2FuncId[node] = self.funcCnt
            # 这里做一个检查，看看所有找到的同一个函数的节点的长度拼起来，是否是其应有的长度，防止漏掉一些顶点
            funcLen = offsetRange[1] + self.cfg.blocks[offsetRange[1]].length - offsetRange[0]
            tempLen = 0
            for n in funcBody:
                tempLen += self.cfg.blocks[n].length
            assert funcLen == tempLen
            # f.printFunc()

        # 第六步，检查一个函数内的节点是否存在环，存在则将其标记出来
        for func in self.funcBodyDict.values():  # 取出一个函数
            tarjan = TarjanAlgorithm(func.funcBodyNodes, func.funcSubGraphEdges)
            tarjan.tarjan(func.firstBodyBlockOffset)
            sccList = tarjan.getSccList()
            for scc in sccList:
                if len(scc) > 1:  # 找到函数内的一个强连通分量
                    for node in scc:  # 将这些点标记为loop-related
                        self.isLoopRelated[node] = True
                        if self.isFuncBodyHeadNode[node]:  # 函数头存在于scc，出现了递归的情况
                            self.log.fail("检测到函数递归调用的情况，该字节码无法被优化!")
        # 这里再做一个检查，看是否所有的common节点都被标记为了函数相关的节点
        for node in self.nodes:
            if self.cfg.blocks[node].blockType == "common":
                if self.node2FuncId[node] == None:  # 没有标记
                    self.log.fail("未能找全所有的函数节点，放弃优化")
                else:
                    continue

        # 第七步，去除之前添加的边，因为下面要做路径搜索，新加入的边并不是原来cfg中应该出现的边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].remove(pair[1])
                self.inEdges[pair[1]].remove(pair[0])

    def __searchPaths(self):
        '''
        从cfg的起始节点开始做dfs，完成以下几项任务（注意，这个dfs是经过修改的）：
        1.找出所有从init节点到所有invalid节点的路径
        2.寻路过程中，同时进行tagStack的记录，从而找到所有jump/jumpi的边的地址是何处被push的
        3.在寻路过程中，找出是否存在环形函数调用链的情况。路径中包含相关节点的assertion同样不会被优化
        '''
        # 第一步，找出所有的invalid节点
        for node in self.blocks.values():
            if node.isInvalid:
                self.invalidNodeList.append(node.offset)
        # print(self.invalidList)

        # 第二步，从起点开始做dfs遍历，完成提到的三个任务
        generator = PathGenerator(self.cfg, self.invalidNodeList, self.uncondJumpEdge, self.isLoopRelated,
                                  self.node2FuncId, self.funcBodyDict)
        generator.genPath()
        paths = generator.getPath()
        self.jumpEdgeInfo = generator.getJumpEdgeInfo()

        # 第三步，将这些路径根据invalid节点进行归类
        for invNode in self.invalidNodeList:
            self.invalidNode2PathIds[invNode] = []
        for path in paths:
            pathId = path.getId()
            self.invalidPaths[pathId] = path
            invNode = path.getLastNode()
            self.invalidNode2PathIds[invNode].append(pathId)
        # for k, v in self.invalidNode2PathIds.items():
        #     print("invalid node is:{}".format(k))
        #     for pathId in v:
        #         self.invalidPaths[pathId].printPath()

        # 第四步，对于一个Invalid节点，检查它的所有路径中，是否存在scc相关的节点
        # 若有，则这些路径对应的invalid将不会被分析
        removedInvPaths = []
        removedInvNodes = []
        for invNode in self.invalidNodeList:
            isProcess = True
            for pathId in self.invalidNode2PathIds[invNode]:
                for node in self.invalidPaths[pathId].pathNodes:
                    if self.isLoopRelated[node]:  # 存在
                        isProcess = False
                        break
                if not isProcess:
                    break
            if not isProcess:
                removedInvNodes.append(invNode)
                for pathId in self.invalidNode2PathIds[invNode]:
                    removedInvPaths.append(pathId)
        for pathId in removedInvPaths:
            self.invalidPaths.pop(pathId)
        for node in removedInvNodes:
            self.invalidNodeList.remove(node)
            self.invalidNode2PathIds.pop(node)

        # for k, v in self.invalidNode2PathIds.items():
        #     print("invalid node is:{}".format(k))
        #     for pathId in v:
        #         self.invalidPaths[pathId].printPath()
        # print(self.isFuncCallLoopRelated)

        # 第五步，对于每个可优化的invalid节点，将其所有路径根据函数调用链进行划分
        for invNode in self.invalidNodeList:  # 取出一个invalid节点
            callChain2PathIds = {}  # 记录调用链内所有的点,格式： 调用链 : [pathId1,pathId2]
            for pathId in self.invalidNode2PathIds[invNode]:  # 取出他所有路径的id
                # 检查这条路径的函数调用链
                callChain = []
                preFuncId = None
                for node in self.invalidPaths[pathId].pathNodes:
                    if self.node2FuncId[node] != preFuncId:  # 进入了一个新函数
                        callChain.append(self.node2FuncId[node])
                        preFuncId = self.node2FuncId[node]
                # 得到一条函数调用链
                self.invalidPaths[pathId].setFuncCallChain(callChain)
                key = callChain.__str__()
                if key not in callChain2PathIds.keys():
                    callChain2PathIds[key] = []
                callChain2PathIds[key].append(pathId)
            # 已经得到了invalid节点所有调用链的路径id
            self.invalidNode2CallChain[invNode] = []
            for callChain, pathIds in callChain2PathIds.items():
                self.invalidNode2CallChain[invNode].append(pathIds)

        # for k, v in self.invalidNode2PathIds.items():
        #     print("invalid node is:{}".format(k))
        #     for pathId in v:
        #         self.invalidPaths[pathId].printPath()
        # print(self.invalidNode2CallChain)

    def __reachabilityAnalysis(self):
        '''
        可达性分析：对于一个invalid节点，检查它的所有路径是否可达，并根据这些可达性信息判断冗余类型
        :return:None
        '''
        # 第一步，使用求解器判断各条路径是否是可达的
        self.invNodeReachable = dict(zip(self.invalidNodeList, [False for i in range(self.invalidNodeList.__len__())]))
        executor = SymbolicExecutor(self.cfg)
        for invNode in self.invalidNodeList:  # 对一个invalid节点
            for pathId in self.invalidNode2PathIds[invNode]:  # 取出一条路径
                self.pathReachable[pathId] = False
                executor.clearExecutor()
                nodeList = self.invalidPaths[pathId].pathNodes
                isSolve = True  # 默认是做约束检查的。如果发现路径走到了一个不应该到达的节点，则不做check，相当于是优化了过程
                constrains = []  # 路径上的约束
                for nodeIndex in range(0, nodeList.__len__() - 1):  # invalid节点不计入计算
                    node = nodeList[nodeIndex]  # 取出一个节点
                    executor.setBeginBlock(node)
                    while not executor.allInstrsExecuted():  # block还没有执行完
                        executor.execNextOpCode()
                    jumpType = executor.getBlockJumpType()
                    if jumpType == "conditional":
                        # 先判断，是否为确定的跳转地址
                        curNode = nodeList[nodeIndex]
                        nextNode = nodeList[nodeIndex + 1]
                        isCertainJumpDest, jumpCond = executor.checkIsCertainJumpDest()
                        if isCertainJumpDest:  # 是一个固定的跳转地址
                            # 检查预期的跳转地址是否和栈的信息匹配
                            expectedTarget = self.cfg.blocks[curNode].jumpiDest[jumpCond]
                            if nextNode != expectedTarget:  # 不匹配，直接置为不可达，后续不做check
                                self.pathReachable[pathId] = False
                                isSolve = False  # 不对这一条路径使用约束求解了
                                self.log.processing(
                                    "路径{}在实际运行中不可能出现：在节点{}处本应跳转到{}，却跳转到了{}".format(pathId, curNode, expectedTarget,
                                                                                   nextNode))
                                break
                        else:  # 不是确定的跳转地址
                            if nextNode == self.cfg.blocks[curNode].jumpiDest[True]:
                                constrains.append(executor.getJumpCond(True))
                            elif nextNode == self.cfg.blocks[curNode].jumpiDest[False]:
                                constrains.append(executor.getJumpCond(False))
                            else:
                                assert 0
                if isSolve:
                    s = Solver()
                    self.pathReachable[pathId] = s.check(constrains) == sat
        # for pid, r in self.pathReachable.items():
        #     print(pid, r)

        # 第二步，根据各条路径的可达性，判断每个invalid节点的冗余类型
        for invNode in self.invalidNodeList:
            hasReachable = False  # 一个invalid的路径中是否包含可达的路径
            for pathId in self.invalidNode2PathIds[invNode]:  # 取出一条路径
                if self.pathReachable[pathId]:  # 找到一条可达的
                    hasReachable = True
            if not hasReachable:  # 没有一条路径可达，是完全冗余
                self.redundantType[invNode] = fullyRedundant
            else:  # 既有可达的也有不可达的，是部分冗余
                self.redundantType[invNode] = partiallyRedundant
        # for node, t in self.redundantType.items():
        #     print(node, t)

    def __buildDominatorTree(self):
        # 因为支配树算法中，节点是按1~N进行标号的，因此需要先做一个标号映射，并处理映射后的边，才能进行支配树的生成
        mapper = GraphMapper(self.nodes, self.edges)
        # mapper.output()
        newEdges = mapper.getNewEdges()
        domTreeEdges = []
        for _from in newEdges.keys():
            for _to in newEdges[_from]:
                domTreeEdges.append([_from, _to])
        domTree = DominatorTreeBuilder()
        domTree.initGraph(self.nodes.__len__(), domTreeEdges)
        domTree.buildTreeFrom(1)  # 原图的偏移量为0的block对应新图中标号为1的节点
        # domTree.outputIdom()
        idoms = domTree.getIdom()
        for _to in idoms.keys():
            _from = idoms[_to]
            if _from != 0:  # 初始节点没有支配节点，被算法标记为0
                self.domTree[mapper.newToOffset(_to)] = mapper.newToOffset(_from)
        # 边格式不可用
        # g3 = DotGraphGenerator(self.domTree, self.nodes)
        # g3.genDotGraph(sys.argv[0], "_dom_tree")

    def __optimizeFullyRedundantAssertion(self, fullyRedundantNodes: list):
        '''
        对字节码中完全冗余的assertion进行优化
        :return:
        '''
        # for pid, t in self.redundantType.items():
        #     print(pid, t)
        executor = SymbolicExecutor(self.cfg)
        for invNode in fullyRedundantNodes:  # 取出一个invalid节点
            # 首先做一个检查，检查是否为jumpi的失败边走向Invalid，且该invalid节点只有一个入边
            assert self.inEdges[invNode].__len__() == 1
            assert invNode == self.blocks[self.inEdges[invNode][0]].jumpiDest[False]
            executor.clearExecutor()
            # for pathsOfCallChain in self.invalidNode2CallChain[invNode]:  # 取出一条调用链
            pathsOfCallChain = self.invalidNode2CallChain[invNode][0]  # 随意取出一条调用链，格式为[pathId1,pathId2...]

            # 第一步，获取路径上所有指令位置的程序状态
            pathNodes = self.invalidPaths[pathsOfCallChain[0]].pathNodes  # 随意取出一条路径
            stateMap = {}  # 状态map，实际存储的是，地址处的指令在执行前的程序状态
            for node in pathNodes:
                executor.setBeginBlock(node)
                while not executor.allInstrsExecuted():  # block还没有执行完
                    offset, state = executor.getCurState()
                    stateMap[offset] = state
                    executor.execNextOpCode()
            # print(statemap)

            # 第二步，在支配树中，从invalid节点出发，寻找程序状态与之相同的地址
            # 因为在符号执行中，invalid指令没有做任何操作，因此invalid处的状态和执行完jumpi的状态是一致的
            # 即 targetState = stateMap[invNode]
            targetAddr = None
            targetNode = None
            targetState = stateMap[invNode]
            node = self.domTree[invNode]
            while node != 0:
                addrs = self.blocks[node].instrAddrs
                for addr in reversed(addrs):  # 从后往前遍历
                    if stateMap[addr] == targetState:  # 找到一个状态相同的点
                        targetAddr = addr
                        targetNode = node
                node = self.domTree[node]
            assert targetAddr and targetNode  # 不能为none
            assert self.blocks[targetNode].blockType != "dispatcher"  # 不应该出现在dispatcher中
            # print(targetNode)
            # print(targetAddr)

            # 第三步，将这一段序列置为空指令
            for node in self.nodes:
                if targetNode <= node <= invNode:  # invNode后的block暂时不处理
                    beginAddr = max(targetAddr, node)
                    endAddr = node + self.blocks[node].length
                    for i in range(beginAddr - node, endAddr - node):
                        self.blocks[node].bytecode[i] = 0x1f  # 置为空指令
                    self.removedRange[node].append([beginAddr, endAddr])
            if self.inEdges[invNode + 1].__len__() == 1:
                # invalid的下一个block，只有一条入边，说明这个jumpdest也可以删除
                self.removedRange[invNode + 1].append([invNode + 1, invNode + 2])
                self.blocks[invNode + 1].bytecode[0] = 0x1f
            # print(self.removedRange)

    def __optimizePartiallyRedundantAssertion(self, partiallyRedundantNodes: list):
        '''
        对字节码中部分冗余的assertion进行优化
        :return:
        '''
        executor = SymbolicExecutor(self.cfg)
        for invNode in partiallyRedundantNodes:
            # 首先做一个检查，检查是否为jumpi的失败边走向Invalid，且该invalid节点只有一个入边
            assert self.cfg.inEdges[invNode].__len__() == 1
            assert invNode == self.cfg.blocks[self.cfg.inEdges[invNode][0]].jumpiDest[False]
            executor.clearExecutor()

            # 第一步，检查所有的函数调用链，找到所有路径都不可达的函数函数调用链
            for pathIdsOfCallChain in self.invalidNode2CallChain[invNode]:  # 对一个调用链
                allUnreachable = True
                for pathId in pathIdsOfCallChain:  # 取出所有的路径
                    if self.pathReachable[pathId]:  # 发现一条是可达的
                        allUnreachable = False
                        break
                if not allUnreachable:  # 该调用链中所有的路径都不可达
                    continue

                # 第二步，获取路径上所有指令位置的程序状态，同时使用tagStack记录栈的情况，关键是记录调用
                # assertion所在函数的jump的地址在何处被push
                pathNodes = self.invalidPaths[pathIdsOfCallChain[0]].pathNodes  # 随意取出一条路径
                invNodeFuncId = self.node2FuncId[pathNodes[pathNodes.__len__() - 1]]  # 找出invalid节点所在的函数的id
                jumpNode = None  # 调用者的jump所在节点
                jumpAddr = None  # 调用者的jump所在地址
                for node in reversed(pathNodes):
                    if self.node2FuncId[node] != invNodeFuncId:  # 找到invalid所在函数的调用者的id
                        jumpNode = node
                        jumpAddr = self.cfg.blocks[node].length + jumpNode - 1  # 找到jump的地址
                        break

                pushOpcodeAddr = None  # 需要寻找的push指令所在的地址
                pushOpcodeBlock = None
                stateMap = {}  # 状态map，实际存储的是，地址处的指令在执行前的程序状态
                for node in pathNodes:
                    executor.setBeginBlock(node)
                    while not executor.allInstrsExecuted():  # block还没有执行完
                        offset, state = executor.getCurState()
                        stateMap[offset] = state
                        if node == jumpNode and offset == jumpAddr:  # 到了调用者的jump节点，但是还没有做jump，栈顶为跳转地址
                            tagStackTop = executor.getTagStackTop()  # 格式：[push的值，push指令的地址，push指令所在的block]
                            assert tagStackTop is not None, "跳转地址不是通过push得到的"  # 该值应该是通过push得到的
                            pushOpcodeAddr = tagStackTop[1]
                            pushOpcodeBlock = tagStackTop[2]
                            # print(pushOpcodeAddr,pushOpcodeBlock)
                        executor.execNextOpCode()
                # print(stateMap)

                # 第三步，在支配树中，从invalid节点出发，寻找程序状态与之相同的地址，定位invalid相关字节码
                # 因为在符号执行中，invalid指令没有做任何操作，因此invalid处的状态和执行完jumpi的状态是一致的
                # 即 targetState = stateMap[invNode]
                targetAddr = None
                targetNode = None
                targetState = stateMap[invNode]
                node = self.domTree[invNode]
                while node != 0:
                    addrs = self.cfg.blocks[node].instrAddrs
                    for addr in reversed(addrs):  # 从后往前遍历
                        if stateMap[addr] == targetState:  # 找到一个状态相同的点
                            targetAddr = addr
                            targetNode = node
                    node = self.domTree[node]
                assert targetAddr and targetNode  # 不能为none
                assert self.cfg.blocks[targetNode].blockType != "dispatcher"  # 不应该出现在dispatcher中
                print(targetAddr)
                print(targetNode)

                # 第四步，构造一个新函数体，其中去除了assertion相关的字节码
                # 新函数体不包括的部分为： targetAddr <= offset <= invNode之间的字节码
                # originalFuncBytecodes = bytearray()
                newFuncBytecodes = bytearray()
                funcBodyNodes = self.funcBodyDict[invNodeFuncId].funcBodyNodes
                # print(funcBodyNodes)
                funcBodyNodes.sort()
                for node in funcBodyNodes:
                    for i in range(self.cfg.blocks[node].length):
                        offset = node + i
                        # originalFuncBytecodes.append(self.cfg.blocks[node].bytecode[i])
                        if targetAddr <= offset <= invNode:
                            continue
                        newFuncBytecodes.append(self.cfg.blocks[node].bytecode[i])
                self.cfg.blocks[244].printBlockInfo()
                # originalFuncBytecodeStr = "".join([self.cfg.blocks[k].bytecodeStr for k in funcBodyNodes])
                # newFuncBytecodeStr = "".join(['{:02x}'.format(num) for num in newFuncBytecodes])
                # print(originalFuncBytecodeStr)
                # print(newFuncBytecodeStr)

                # # 第三步，直接修改该地址处的字节码，将其变为jump，跳转到invalid前的jumpi的true的地方，即invalid的地址+1处
            # jumpDestAddr = hex(invNode + 1)[2:]  # 转为了十六进制，并且去除了0x
            # # jumpDestAddr = hex(0x01ffff)[2:]  # 测试用
            # if jumpDestAddr.__len__() % 2 == 1:
            #     jumpDestAddr = '0' + jumpDestAddr
            # pushOpcode = 0x60 + jumpDestAddr.__len__() // 2 - 1  # push指令的操作码
            # # print("put {}:{} in addr {}".format(pushOpcode, jumpDestAddr, targetAddr))
            # originalBytecode = self.cfg.blocks[targetNode].bytecode
            # # print(originalBytecode)
            # pushOffsetInTargetBlock = targetAddr - targetNode  # push指令的偏移量，这里的偏移量是字节偏移量
            # jumpOffsetInTargetBlock = pushOffsetInTargetBlock + jumpDestAddr.__len__() // 2 + 1  # jump指令的偏移量
            # assert jumpOffsetInTargetBlock < self.cfg.blocks[targetNode].length  # 修改的所有内容，不应当超出原的block的范围
            # newBytecode = bytearray()
            # for i in range(self.cfg.blocks[targetNode].length):
            #     if i < pushOffsetInTargetBlock:  # 还没到push指令，直接复制
            #         newBytecode.append(originalBytecode[i])
            #     elif i == pushOffsetInTargetBlock:  # 到了push指令处
            #         newBytecode.append(pushOpcode)
            #     elif i < pushOffsetInTargetBlock + 1 + jumpDestAddr.__len__() // 2:  # 到了push指令的内容处
            #         addrIndex = 2 * (i - pushOffsetInTargetBlock - 1)
            #         newBytecode.append(int(jumpDestAddr[addrIndex:addrIndex + 2], 16))
            #     elif i == jumpOffsetInTargetBlock:  # 到了jump指令的内容处
            #         newBytecode.append(0x56)  # jump
            #         # newBytecode.append(0x57)
            #     else:  # 过了jump指令，后面全部用5b代替
            #         newBytecode.append(0x5b)
            #
            # assert newBytecode.__len__() == originalBytecode.__len__()
            # self.cfg.blocks[targetNode].bytecode = newBytecode  # 改为新的字节数组
            # self.cfg.blocks[targetNode].isModified = True
            # # for i in range(18):
            # #     print(hex(originalBytecode[i]), hex(newBytecode[i]))
            #
            # # 第四步，将该invalid的其他所有路径中targetNode之后的所有node全部置为空指令
            # for pathId in self.invalidNode2PathIds[invNode]:
            #     for node in self.invalidPaths[pathId].pathNodes:
            #         if node <= targetNode:
            #             continue
            #         # 取到一个大于targetNode的节点
            #         self.cfg.blocks[node].isModified = True
            #         for i in range(self.cfg.blocks[node].length):
            #             self.cfg.blocks[node].bytecode[i] = 0x5b

    def __regenerateBytecode(self):
        '''
        重新生成字节码，同时完成重定位
        :return:
        '''

        # 第一步，对删除区间信息去重
        for node in self.nodes:
            if self.removedRange[node].__len__() == 0:
                continue
            tempSet = set()
            for _range in self.removedRange[node]:
                tempSet.add(_range.__str__())  # 存为字符串
            self.removedRange[node] = []  # 置空
            for rangeStr in tempSet:
                self.removedRange[node].append(json.loads(rangeStr))  # 再还原为list

        # 第二步，将出现在已被删除字节码序列中的跳转信息删除
        # [push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]
        removedInfo = []
        for info in self.jumpEdgeInfo:
            # 首先做一个检查
            delPush = False
            delJump = False
            pushBlock = info[3]
            pushAddr = info[2]
            jumpBlock = info[4]
            jumpAddr = jumpBlock + self.blocks[jumpBlock].length - 1
            for _range in self.removedRange[pushBlock]:
                if _range[0] <= pushAddr < _range[1]:  # push语句位于删除序列内
                    delPush = True
                    break
            for _range in self.removedRange[jumpBlock]:
                if _range[0] <= jumpAddr < _range[1]:  # jump/jumpi语句位于删除序列内
                    delJump = True
                    break
            # 解释一下为什么要做这个assert:因为这一个跳转信息是根据返回地址栈得出的
            # 也就是说，如果要删除push，则jump必须也要被删除，否则当出现这个函数调用关系时，
            # 在jump的时候会找不到返回地址
            assert delPush == delJump
            if delPush:  # 确定要删除
                removedInfo.append(info)
        for info in removedInfo:
            self.jumpEdgeInfo.remove(info)  # 删除对应的信息
        # print(self.jumpEdgeInfo)

        # 第三步，对每一个block，删除空指令，同时还要记录旧地址到新地址的映射
        self.nodes.sort()  # 确保是从小到大排序的
        mappedAddr = 0  # 映射后的新地址
        for node in self.nodes:
            self.originalLength += self.blocks[node].length
            blockLen = self.blocks[node].length
            newBlockLen = blockLen  # block的新长度
            isDelete = [False for i in range(blockLen)]
            # 设置要删除的下标，以及计算新的block长度
            for _range in self.removedRange[node]:  # 查看这一个block的删除区间
                for i in range(_range[0] - node, _range[1] - node):
                    isDelete[i] = True  # 设置要删除的下标
                newBlockLen -= _range[1] - _range[0]
            # 重新生成字节码，并计算地址映射
            bytecode = self.blocks[node].bytecode
            newBytecode = bytearray()
            for i in range(blockLen):
                self.originalToNewAddr[i + node] = mappedAddr
                if isDelete[i]:  # 这一个字节是需要被删除的
                    continue
                newBytecode.append(bytecode[i])
                mappedAddr += 1
            self.blocks[node].length = newBlockLen  # 设置新的block长度
            self.blocks[node].bytecode = newBytecode  # 设置新的block字节码
        # print(self.removedRange)
        # for k,v in self.originalToNewAddr.items():
        #     print(k,v)
        # for b in self.blocks.values():
        #     b.printBlockInfo()

        # 第四步，尝试将跳转地址填入
        # 每一次都是做试填入，不能保证一定可以填入成功，地址可能会过长或者过短
        # 这两种情况都需要改地址映射，并重新生成所有地址映射
        # [push的值，push的字节数，push指令的地址，push指令所在的block,jump所在的block]
        # 首先要根据push指令所在的地址，对这些进行进行一个排序(在路径生成器中已去重)
        pushAddrToInfo = {}
        for info in self.jumpEdgeInfo:
            pushAddrToInfo[info[2]] = info
        sortedAddrs = list(pushAddrToInfo.keys())
        sortedAddrs.sort()
        sortedJumpEdgeInfo = []
        for addr in sortedAddrs:
            sortedJumpEdgeInfo.append(pushAddrToInfo[addr])
        # print(sortedJumpEdgeInfo)
        # 然后尝试对每一个跳转信息，进行试填入
        finishFilling = False
        while not finishFilling:  # 只有所有的info都能成功填入，才能停止
            finishFilling = True  # 默认可以全部成功填入
            for index in range(sortedJumpEdgeInfo.__len__()):
                info = sortedJumpEdgeInfo[index]
                originalByteNum = info[1]  # 原来的内容占据的字节数
                newAddr = self.originalToNewAddr[info[0]]  # 新的需要push的内容
                tempAddr = newAddr
                newByteNum = 0  # 新内容需要的字节数
                while tempAddr != 0:
                    tempAddr >>= 8
                    newByteNum += 1
                offset = newByteNum - originalByteNum
                # if offset == 0:  # 不需要移动，直接填入新内容即可
                if offset <= 0:  # 不需要移动，直接填入新内容即可
                    pushBlock = info[3]
                    pushBlockOffset = self.originalToNewAddr[pushBlock]  # push所在block的新偏移量
                    pushAddr = self.originalToNewAddr[info[2]]  # push指令的新地址
                    newAddrBytes = deque()  # 新地址的字节码
                    tempAddr = newAddr
                    while tempAddr != 0:
                        newAddrBytes.appendleft(tempAddr & 0xff)  # 取低八位
                        tempAddr >>= 8
                    for i in range(-offset):
                        newAddrBytes.appendleft(0x00)  # 原有的位置多出来的地方，用0填充
                    for i in range(originalByteNum):  # 按原来的字节数填
                        self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset + 1 + i] = newAddrBytes[
                            i]  # 改的是地址，因此需要+1
                else:  # 新内容不能直接填入，原位置空间不够，需要移动字节码
                    self.log.warning("原push位置不能直接填入新地址，需要移动字节码")
                    # 先改push的操作码
                    originalOpcode = 0x60 + originalByteNum - 1
                    newOpcode = originalOpcode + offset
                    # print(originalOpcode, newOpcode)
                    assert 0x60 <= newOpcode <= 0x7f
                    pushBlock = info[3]
                    pushBlockOffset = self.originalToNewAddr[pushBlock]  # push所在block的新偏移量
                    pushAddr = self.originalToNewAddr[info[2]]  # push指令的新地址
                    self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset] = newOpcode

                    # 然后再改地址
                    if offset > 0:
                        for i in range(offset):
                            self.blocks[pushBlock].bytecode.insert(pushAddr - pushBlockOffset + 1, 0x00)  # 先插入足够的位置
                    else:
                        for i in range(-offset):
                            self.blocks[pushBlock].bytecode.pop(pushAddr - pushBlockOffset + 1)  # 先删掉多出的位置
                    # 再改地址
                    # for i in range(newByteNum):
                    #     self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset + 1 + i] = newAddrBytes[
                    #         i]  # 改的是地址，因此需要+1
                    # 不改地址，因为会进行下一次的试填入，必然会填入新地址

                    # 接着，需要修改新旧地址映射，以及跳转信息中的字节量（供下一次试填入使用)
                    for original in self.originalToNewAddr.keys():
                        if original > info[2]:
                            self.originalToNewAddr[original] += offset  # 映射信息需要增加偏移量
                    sortedJumpEdgeInfo[index][1] = newByteNum  # 只改字节数，其他信息与原来相同

                    # 最后需要改一些其他信息
                    self.blocks[pushBlock].length += offset
                    finishFilling = False  # 本次试填入失败
                    break  # 不再查看其他的跳转信息，重新开始再做试填入

        # 第四步，尝试将这些字节码拼成一个整体
        self.newBytecode = deque()  # 效率更高
        for node in self.nodes:  # 有序的
            # 第一步，
            for bc in self.blocks[node].bytecode:
                self.newBytecode.append(bc)

    def __outputFile(self):
        '''
        将修改后的cfg写回到文件中
        :return:
        '''
        # 给定一个假设，dispatcher中的内容不能被修改
        # 第一步，将原文件读入一个字符串，然后让其和原函数体字符串做匹配，找到offset为0对应的下标
        with open(self.inputFile, "r") as f:
            originalBytecodeStr = f.read()
            f.close()
        # print(originalBytecodeStr)
        sortedKeys = list(self.cfg.blocks.keys())
        sortedKeys.sort()
        # print(sortedKeys)
        funcBodyStr = "".join([self.cfg.blocks[k].bytecodeStr for k in sortedKeys])
        # print(funcBodyStr)
        assert originalBytecodeStr.count(funcBodyStr) == 1

        # 第二步，获取原文件中，在函数体之前的以及之后的字符串，同时将其与新函数体的字符串拼接起来
        beginIndex = originalBytecodeStr.find(funcBodyStr)  # 因为找出的是字符串的偏移量，需要除2变为字节偏移量
        preStr = originalBytecodeStr[:beginIndex]
        postStr = originalBytecodeStr[beginIndex + self.originalLength * 2:]
        newFuncBodyStr = "".join(['{:02x}'.format(num) for num in self.newBytecode])  # 再转换回字符串
        newBytecodeStr = preStr + newFuncBodyStr + postStr

        # 第三步，将结果写入文件
        with open(self.outputFile, "w+") as f:
            f.write(newBytecodeStr)
