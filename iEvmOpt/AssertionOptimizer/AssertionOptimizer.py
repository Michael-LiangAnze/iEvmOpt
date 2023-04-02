from collections import deque

from graphviz import Digraph
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
from Utils.OpcodeTranslator import OpcodeTranslator

fullyRedundant = "fullyRedundant"
partiallyRedundant = "partiallyRedundant"
nonRedundant = "nonRedundant"


class AssertionOptimizer:
    def __init__(self, cfg: Cfg, inputFile: str, outputFile: str, outputProcessInfo: bool = False):
        self.cfg = cfg
        self.blocks = self.cfg.blocks  # 存储基本块，格式为 起始offset:BasicBlock
        self.inputFile = inputFile  # 处理前的文件
        self.outputFile = outputFile  # 处理后的新文件
        self.log = Logger()
        self.outputProcessInfo = outputProcessInfo

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
        self.fullyRedundantInvNodes = []  # 完全冗余的invalid节点
        self.partiallyRedundantInvNodes = []  # 部分冗余的invalid节点
        self.nonRedundantInvNodes = []  # 不冗余的invalid节点
        self.invNodeToRedundantCallChain = {}  # 每个invalid节点对应的，冗余的函数调用链，格式为： invNode:[[pid1,pid2],[pid3,pid4]]

        # 冗余assertion优化需要用到的信息
        self.domTree = {}  # 支配树。注意，为了方便从invalid节点往前做遍历，该支配树存储的是入边，格式为   to:from
        self.removedRange = dict(
            zip(self.nodes, [[] for i in range(0, len(self.nodes))]))  # 记录每个block中被移除的区间，每个区间的格式为:[from,to)

        # 重定位需要用到的信息
        self.jumpEdgeInfo = None  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选),新老函数体之间的offset(可选)]]
        # 这里给一个设定：
        # 在重定位时，一旦出现了第六个和第七个参数，即说明这是新构造函数体的相关跳转信息
        # 此时为第一次读取到这条信息，后面会根据这条信息进行试填入。填入之后，直接修改信息，然后将最后两个参数pop，即将该信息变回到普通的信息，统一处理。
        # 一旦出现第六第七个参数，则前面所有的信息都不是真实的，需要根据跳转边类型进行修改如下
        #   跳转的type为0，说明push在且jump也在新函数体，但是push的值不在（新函数体跳到其他地方），此时需要将2、3、4号位信息加上offset
        #   跳转的type为1，说明push在且jump也在新函数体，且push的值在（新函数体内部的跳转），此时需要将0、2、3、4号位信息加上offset，并重新计算字节数
        #   跳转的type为2，说明push不在且jump也不在新函数体，但是push的值在，而且callerNode==jump所在的Block（新函数的调用），此时需要将0号位的push加上offset，并重新计算字节数（调用新的函数体）
        #   跳转的type为3，说明push不在但jump在新函数体,而且callerNodeJumpAddr+1==push的值（新函数体返回），此时需要将4号位加上offset即可
        #   跳转的type为4，说明push在但jump不在新函数体（新函数体对其他函数的调用后返回），此时需要将0、2、3号位信息加上offset，并重新计算字节数

        # 将原文件读入一个字符串，然后让其和原函数体字符串做匹配，找到offset为0对应的下标
        with open(self.inputFile, "r") as f:
            self.originalBytecodeStr = f.read()
            f.close()
        sortedKeys = list(self.cfg.blocks.keys())
        sortedKeys.sort()
        funcBodyStr = "".join([self.cfg.blocks[k].bytecodeStr if k <= self.cfg.exitBlockId else "" for k in sortedKeys])
        assert self.originalBytecodeStr.count(funcBodyStr) == 1  # 应该只出现一次
        self.funcBodyStrBeginIndex = self.originalBytecodeStr.find(funcBodyStr)  # 找出的是字符串的偏移量，需要除2变为字节偏移量
        self.originalLength = 0  # 原来的字节码函数体的总长度
        for b in self.blocks.values():
            self.originalLength += b.length
        self.originalToNewAddr = {}  # 一个映射，格式为： 旧addr:新addr

        # 重新生成函数体代码的信息
        self.newBytecode1 = None  # 第一段字节码，即原函数体相关的字节码
        self.newBytecode2 = None  # 第二段字节码，即新构造函数体相关的字节码

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
            "路径搜索完毕，一共找到{}个待处理的Assertion，一共找到{}条路径，{}条函数调用链".format(self.invalidNodeList.__len__(),
                                                                    self.invalidPaths.__len__(), callChainNum))
        if self.invalidNodeList.__len__() == 0:
            self.log.info("没有待处理的Assertion，优化结束")
            return

        # 求解各条路径是否可行
        self.log.info("正在分析路径可达性")
        self.__reachabilityAnalysis()
        self.log.info("可达性分析完毕")

        # 生成cfg的支配树
        self.__buildDominatorTree()

        self.log.info(
            "一共找到{}个待优化的assertion，具体为：{}个完全冗余，{}个部分冗余，{}个不冗余".format(
                self.invalidNodeList.__len__(), self.fullyRedundantInvNodes.__len__(),
                self.partiallyRedundantInvNodes.__len__(),
                self.nonRedundantInvNodes.__len__()))
        if self.fullyRedundantInvNodes.__len__() == 0 and self.partiallyRedundantInvNodes.__len__() == 0:
            self.log.info("不存在可优化的Assertion，优化结束")
            return
        if self.fullyRedundantInvNodes.__len__() > 0:  # 存在完全冗余的节点
            self.log.info("正在对完全冗余的Assertion进行优化")
            self.__optimizeFullyRedundantAssertion()
            self.log.info("完全冗余Assertion优化完毕")
        if self.partiallyRedundantInvNodes.__len__() > 0:
            self.log.info("正在对部分冗余的Assertion进行优化")
            self.__optimizePartiallyRedundantAssertion()
            self.log.info("部分冗余Assertion优化完毕")

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
                                if self.outputProcessInfo:  # 需要输出处理信息
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

        # invalidNode2CallChain
        # 第二步，根据各个函数调用链的可达性，判断每个invalid节点的冗余类型
        for invNode in self.invalidNodeList:
            self.invNodeToRedundantCallChain[invNode] = []
            hasReachable = False  # 一个invalid的路径中是否包含可达的路径
            hasRedundantCallChain = False  # 一个invalid的所有函数调用链，是否都是冗余的
            for pathIds in self.invalidNode2CallChain[invNode]:  # 取出一条函数调用链中的所有路径
                isRedundantCallChain = True
                for pathId in pathIds:  # 取出一条路径
                    if self.pathReachable[pathId]:  # 找到一条可达的
                        hasReachable = True
                        isRedundantCallChain = False  # 该调用链不是冗余的
                if isRedundantCallChain:  # 调用链是冗余的
                    hasRedundantCallChain = True
                    self.invNodeToRedundantCallChain[invNode].append(pathIds)
            if not hasReachable:  # 没有一条路径可达，是完全冗余
                self.redundantType[invNode] = fullyRedundant
                self.fullyRedundantInvNodes.append(invNode)
            else:  # 有可达的路径
                if hasRedundantCallChain:  # 有冗余的函数调用链
                    self.redundantType[invNode] = partiallyRedundant
                    self.partiallyRedundantInvNodes.append(invNode)
                else:  # 没有冗余的调用链
                    self.redundantType[invNode] = nonRedundant
                    self.nonRedundantInvNodes.append(invNode)
        # # 第二步，根据各条路径的可达性，判断每个invalid节点的冗余类型
        # for invNode in self.invalidNodeList:
        #     hasReachable = False  # 一个invalid的路径中是否包含可达的路径
        #     for pathId in self.invalidNode2PathIds[invNode]:  # 取出一条路径
        #         if self.pathReachable[pathId]:  # 找到一条可达的
        #             hasReachable = True
        #     if not hasReachable:  # 没有一条路径可达，是完全冗余
        #         self.redundantType[invNode] = fullyRedundant
        #     else:  # 既有可达的也有不可达的，是部分冗余
        #         self.redundantType[invNode] = partiallyRedundant
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

    def __optimizeFullyRedundantAssertion(self):
        '''
        对字节码中完全冗余的assertion进行优化
        :return:
        '''
        # for pid, t in self.redundantType.items():
        #     print(pid, t)
        executor = SymbolicExecutor(self.cfg)
        for invNode in self.fullyRedundantInvNodes:  # 取出一个invalid节点
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
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("找到和节点{}程序状态相同的地址:{}，对应的节点为:{}".format(invNode, targetAddr, targetNode))

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

    def __optimizePartiallyRedundantAssertion(self):
        '''
        对字节码中部分冗余的assertion进行优化
        :return:
        '''
        # 第一步，修改原来exit block的长度以及内容，它的作用是替代合约字节码中的数据段，
        # 方便在后面插入新构造的函数体
        curLastNode = self.cfg.exitBlockId
        postStr = self.originalBytecodeStr[self.funcBodyStrBeginIndex + self.originalLength * 2:]
        assert postStr.__len__() % 2 == 0
        self.blocks[curLastNode].length = postStr.__len__() // 2  # 直接改exit block的长度
        tempByteCode = bytearray()
        for i in range(postStr.__len__() // 2):
            tempByteCode.append(0x1f)  # 指令置为空指令
        self.blocks[curLastNode].bytecode = tempByteCode

        executor = SymbolicExecutor(self.cfg)
        for invNode in self.partiallyRedundantInvNodes:  # 在可达性分析中已经确认该节点是部分冗余的
            # 首先做一个检查，检查是否为jumpi的失败边走向Invalid，且该invalid节点只有一个入边
            assert self.cfg.inEdges[invNode].__len__() == 1
            assert invNode == self.cfg.blocks[self.cfg.inEdges[invNode][0]].jumpiDest[False]

            # 第二步，使用符号执行，找到程序状态与Invalid执行完之后相同的targetNode和targetAddr
            pathIds = self.invNodeToRedundantCallChain[invNode][0]  # 随意取出一条调用链
            pathNodes = self.invalidPaths[pathIds[0]].pathNodes  # 随意取出一条路径
            stateMap = {}  # 状态map，实际存储的是，地址处的指令在执行前的程序状态
            executor.clearExecutor()
            for node in pathNodes:
                executor.setBeginBlock(node)
                while not executor.allInstrsExecuted():  # block还没有执行完
                    offset, state = executor.getCurState()
                    stateMap[offset] = state
                    executor.execNextOpCode()

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
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("找到和节点{}程序状态相同的地址:{}，对应的节点为:{}".format(invNode, targetAddr, targetNode))

            # 第四步，构造一个新函数体，其中去除了assertion相关的字节码
            # 新函数体不包括的部分为： targetAddr <= addr <= invNode之间的字节码
            invNodeFuncId = self.node2FuncId[invNode]  # 找出invalid节点所在的函数的id
            funcBodyNodes = self.funcBodyDict[invNodeFuncId].funcBodyNodes
            # print(funcBodyNodes)
            newFuncBodyNodes = []
            funcBodyNodes.sort()  # 从小到大一个个加
            offset = curLastNode + self.blocks[curLastNode].length - funcBodyNodes[0]  # 两个函数体之间的偏移量
            # print(curLastNode,self.blocks[curLastNode].length,funcBodyNodes[0])
            # print(offset)
            translator = OpcodeTranslator(self.cfg.exitBlockId)
            for node in funcBodyNodes:  # 对每一个原有的block，都新建一个相同的block
                originalBlock = self.blocks[node]
                beginOffset = node + offset
                newBlockInfo = {}
                newBlockInfo["offset"] = beginOffset
                newBlockInfo["length"] = originalBlock.length
                newBlockInfo["type"] = originalBlock.blockType
                newBlockInfo["stackBalance"] = str(originalBlock.stackBalance)
                newBlockInfo["bytecodeHex"] = originalBlock.bytecodeStr
                newBlockInfo["parsedOpcodes"] = originalBlock.instrsStr
                newBlock = BasicBlock(newBlockInfo)  # 新建一个block
                # 添加删除序列信息，并将被删除序列置为空指令
                self.removedRange[beginOffset] = []
                if targetNode <= node <= invNode:  # 是要删除字节码的block
                    beginAddr = max(targetAddr, node)
                    endAddr = node + originalBlock.length
                    for i in range(beginAddr - node, endAddr - node):
                        newBlock.bytecode[i] = 0x1f  # 置为空指令
                    beginAddr += offset
                    endAddr += offset
                    self.removedRange[beginOffset].append([beginAddr, endAddr])
                elif node == invNode + 1 and self.inEdges[invNode + 1].__len__() == 1:
                    # invalid的下一个block，只有一条入边，说明这个jumpdest也可以删除
                    self.removedRange[invNode + 1 + offset].append([invNode + 1 + offset, invNode + 2 + offset])
                    newBlock.bytecode[0] = 0x1f
                # 将原函数体中已经存在的删除序列信息，添加到新函数体中
                for info in self.removedRange[node]:
                    newInfo = list(info)
                    newInfo[0] += offset
                    newInfo[1] += offset
                    self.removedRange[beginOffset].append(newInfo)
                newBlock.instrs = translator.translate(newBlock)
                # 放入到cfg中
                self.blocks[beginOffset] = newBlock  # 添加到原图中
                self.nodes.append(beginOffset)  # 添加到原图中
                self.edges[beginOffset] = []
                newFuncBodyNodes.append(beginOffset)

            # 第六步，找出各个函数调用链的，新函数体的调用节点
            callerNodes = []
            for callChain in self.invNodeToRedundantCallChain[invNode]:
                pathId = callChain[0]  # 在调用链上随意取出一条路径
                pathNodes = self.invalidPaths[pathId].pathNodes
                for node in reversed(pathNodes):
                    curNodeFuncId = self.node2FuncId[node]
                    if curNodeFuncId != invNodeFuncId:  # 出了invalid的函数
                        callerNodes.append(node)
                        break
            returnedNodes = [node + self.blocks[node].length for node in callerNodes]  # 应当返回的节点

            # 第七步，添加跳转边信息
            # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选),新老函数体之间的offset(可选)]]
            # 这里给一个设定：
            # 在重定位时，一旦出现了第六个和第七个参数，即说明这是新构造函数体的相关跳转信息
            # 此时为第一次读取到这条信息，后面会根据这条信息进行试填入。填入之后，直接修改信息，然后将最后两个参数pop，即将该信息变回到普通的信息，统一处理。
            # 一旦出现第六第七个参数，则前面所有的信息都不是真实的，需要根据跳转边类型进行修改如下
            #   跳转的type为0，说明push在且jump也在新函数体，但是push的值不在（新函数体跳到其他地方），此时需要将2、3、4号位信息加上offset
            #   跳转的type为1，说明push在且jump也在新函数体，且push的值在（新函数体内部的跳转），此时需要将0、2、3、4号位信息加上offset，并重新计算字节数
            #   跳转的type为2，说明push不在且jump也不在新函数体，但是push的值在，而且callerNode==jump所在的Block（新函数的调用），此时需要将0号位的push加上offset，并重新计算字节数（调用新的函数体）
            #   跳转的type为3，说明push不在但jump在新函数体,而且callerNodeJumpAddr+1==push的值（新函数体返回），此时需要将4号位加上offset即可
            #   跳转的type为4，说明push在但jump不在新函数体（新函数体对其他函数的调用后返回），此时需要将0、2、3号位信息加上offset，并重新计算字节数
            newJumpEdgeInfo = []  # 要新添加的跳转边信息
            originalFuncRange = range(funcBodyNodes[0], funcBodyNodes[-1] + self.blocks[funcBodyNodes[-1]].length)
            for info in self.jumpEdgeInfo:
                newInfo = list(info)
                checker = 0  # 将三个信息映射到一个数字
                if info[3] in originalFuncRange:  # push在
                    checker |= 4
                if info[4] in originalFuncRange:  # jump在
                    checker |= 2
                if info[0] in originalFuncRange:  # push的值在
                    checker |= 1
                match checker:
                    case 0b110:  # 0
                        newInfo.append(0)
                        newInfo.append(offset)
                        newJumpEdgeInfo.append(newInfo)
                        self.edges[info[4] + offset].append(info[0])
                    case 0b111:  # 1
                        newInfo.append(1)
                        newInfo.append(offset)
                        newJumpEdgeInfo.append(newInfo)
                        self.edges[info[4] + offset].append(info[0] + offset)
                    case 0b001:  # 2
                        if info[4] in callerNodes:  # 是新函数体的调用边
                            newInfo.append(2)
                            newInfo.append(offset)
                            newJumpEdgeInfo.append(newInfo)
                            self.edges[info[4]].append(info[0] + offset)
                    case 0b011 | 0b010:  # 3
                        assert info[0] not in originalFuncRange  # 必须是返回边
                        if info[0] in returnedNodes:  # 是新函数体的返回边
                            newInfo.append(3)
                            newInfo.append(offset)
                            newJumpEdgeInfo.append(newInfo)
                            self.edges[info[4] + offset].append(info[0])
                    case 0b101 | 0b100:  # 4
                        assert info[0] in originalFuncRange  # 必须是返回到新函数体
                        newInfo.append(4)
                        newInfo.append(offset)
                        newJumpEdgeInfo.append(newInfo)
                        self.edges[info[4]].append(info[0] + offset)
                    # 否则，不需要修改这条边信息
            for info in newJumpEdgeInfo:
                self.jumpEdgeInfo.append(info)
            for node in funcBodyNodes:  # 将不需要重定位，而且不在删除序列中的边添加到edges中
                tempType = self.blocks[node].jumpType
                if tempType == "fall":
                    if targetNode <= node <= invNode:
                        continue
                    _from = node + offset
                    _to = node + offset + self.blocks[node].length
                    self.edges[_from].append(_to)
                elif tempType == "terminal":
                    if targetNode <= node <= invNode:
                        continue
                    _from = node + offset
                    self.edges[_from].append(self.cfg.exitBlockId)
                elif tempType == "conditional":  # 添加其中的fall边
                    _from = node + offset
                    _to = _to = node + offset + self.blocks[node].length
                    self.edges[_from].append(_to)

    def __regenerateBytecode(self):
        '''
        重新生成字节码，同时完成重定位
        :return:
        '''
        # for b in self.blocks.values():
        #     b.printBlockInfo()
        # print(self.jumpEdgeInfo)
        # print(self.removedRange)
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
        # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选),新老函数体之间的offset(可选)]]
        # 这里给一个设定：
        # 在重定位时，一旦出现了第六个和第七个参数，即说明这是新构造函数体的相关跳转信息
        # 此时为第一次读取到这条信息，后面会根据这条信息进行试填入。填入之后，直接修改信息，然后将最后两个参数pop，即将该信息变回到普通的信息，统一处理。
        # 一旦出现第六第七个参数，则前面所有的信息都不是真实的，需要根据跳转边类型进行修改如下
        #   跳转的type为0，说明push在且jump也在新函数体，但是push的值不在（新函数体跳到其他地方），此时需要将2、3、4号位信息加上offset
        #   跳转的type为1，说明push在且jump也在新函数体，且push的值在（新函数体内部的跳转），此时需要将0、2、3、4号位信息加上offset，并重新计算字节数
        #   跳转的type为2，说明push不在且jump也不在新函数体，但是push的值在，而且callerNode==jump所在的Block（新函数的调用），此时需要将0号位的push加上offset，并重新计算字节数（调用新的函数体）
        #   跳转的type为3，说明push不在但jump在新函数体,而且callerNodeJumpAddr+1==push的值（新函数体返回），此时需要将4号位加上offset即可
        #   跳转的type为4，说明push在但jump不在新函数体（新函数体对其他函数的调用后返回），此时需要将0、2、3号位信息加上offset，并重新计算字节数
        removedInfo = []
        # for _from,_to in self.edges.items():
        #     print(_from,_to)
        for info in self.jumpEdgeInfo:
            # 首先做一个检查
            addr = info[0]
            pushBlock = info[3]
            pushAddr = info[2]
            jumpBlock = info[4]
            if info.__len__() == 7:  # 是新block相关的信息
                match info[5]:
                    case 0:
                        pushBlock += info[6]
                        pushAddr += info[6]
                        jumpBlock += info[6]
                    case 1:
                        addr += info[6]
                        pushBlock += info[6]
                        pushAddr += info[6]
                        jumpBlock += info[6]
                    case 2:
                        addr += info[6]
                    case 3:
                        jumpBlock += info[6]
                    case 4:
                        addr += info[6]
                        pushAddr += info[6]
                        pushBlock += info[6]
            jumpAddr = jumpBlock + self.blocks[jumpBlock].length - 1
            delPush = False
            delJump = False
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
                self.edges[jumpBlock].remove(addr)
                if self.blocks[jumpBlock].jumpType == "conditional":  # 删除其中的fall边
                    self.edges[jumpBlock].remove(jumpBlock + self.blocks[jumpBlock].length)
        for info in removedInfo:
            self.jumpEdgeInfo.remove(info)  # 删除对应的信息
        # print(self.jumpEdgeInfo)

        # 第三步，对每一个block，删除空指令，同时还要记录旧地址到新地址的映射
        self.nodes.sort()  # 确保是从小到大排序的
        mappedAddr = 0  # 映射后的新地址
        for node in self.nodes:
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
        # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选),新老函数体之间的offset(可选)]]
        # 这里给一个设定：
        # 在重定位时，一旦出现了第六个和第七个参数，即说明这是新构造函数体的相关跳转信息
        # 此时为第一次读取到这条信息，后面会根据这条信息进行试填入。填入之后，直接修改信息，然后将最后两个参数pop，即将该信息变回到普通的信息，统一处理。
        # 一旦出现第六第七个参数，则前面所有的信息都不是真实的，需要根据跳转边类型进行修改如下
        #   跳转的type为0，说明push在且jump也在新函数体，但是push的值不在（新函数体跳到其他地方），此时需要将2、3、4号位信息加上offset
        #   跳转的type为1，说明push在且jump也在新函数体，且push的值在（新函数体内部的跳转），此时需要将0、2、3、4号位信息加上offset，并重新计算字节数
        #   跳转的type为2，说明push不在且jump也不在新函数体，但是push的值在，而且callerNode==jump所在的Block（新函数的调用），此时需要将0号位的push加上offset，并重新计算字节数（调用新的函数体）
        #   跳转的type为3，说明push不在但jump在新函数体,而且callerNodeJumpAddr+1==push的值（新函数体返回），此时需要将4号位加上offset即可
        #   跳转的type为4，说明push在但jump不在新函数体（新函数体对其他函数的调用后返回），此时需要将0、2、3号位信息加上offset，并重新计算字节数

        # 首先要根据push指令所在的地址，对这些进行进行一个排序(在路径生成器中已去重)
        pushAddrToInfo = {}
        for info in self.jumpEdgeInfo:
            if info.__len__() == 7:
                newPushAddr = info[2]
                match info[5]:
                    case 0 | 1 | 4:
                        newPushAddr += info[6]
                pushAddrToInfo[newPushAddr] = info
            else:
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
                originalByteNum = info[1]  # 原来的内容占据的字节数,这一条无需修改
                # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选), 新老函数体之间的offset(可选)]]
                #   跳转的type为0，说明push在且jump也在新函数体，但是push的值不在（新函数体跳到其他地方），此时需要将2、3、4号位信息加上offset
                #   跳转的type为1，说明push在且jump也在新函数体，且push的值在（新函数体内部的跳转），此时需要将0、2、3、4号位信息加上offset，并重新计算字节数
                #   跳转的type为2，说明push不在且jump也不在新函数体，但是push的值在（新函数的调用），此时需要将0号位的push加上offset，并重新计算字节数（调用新的函数体）
                #   跳转的type为3，说明push不在但jump在新函数体（新函数体返回），此时需要将4号位加上offset即可
                #   跳转的type为4，说明push在但jump不在新函数体（新函数体对其他函数的调用后返回），此时需要将0、2、3号位信息加上offset，并重新计算字节数
                if info.__len__() == 7:  # 第一次读取到这种信息，需要重新计算，计算完成后，pop两个元素，变为普通信息
                    tempAddr = info[0]
                    tempPushAddr = info[2]
                    tempPushBlock = info[3]
                    tempJumpBlock = info[4]
                    offset = info[6]
                    match info[5]:
                        case 0:
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                            info[4] = tempJumpBlock + offset
                        case 1:
                            info[0] = tempAddr + offset
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                            info[4] = tempJumpBlock + offset
                        case 2:
                            info[0] = tempAddr + offset
                        case 3:
                            info[4] = tempJumpBlock + offset
                        case 4:
                            info[0] = tempAddr + offset
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                    info = info[:5]
                # 当前读取到的是普通信息，尝试进行试填入
                newAddr = self.originalToNewAddr[info[0]]
                pushAddr = self.originalToNewAddr[info[2]]  # push指令的新地址
                pushBlock = info[3]  # push所在的block，当前的block还是按原来的为准
                pushBlockOffset = self.originalToNewAddr[pushBlock]  # push所在block的新偏移量

                newByteNum = 0  # 新内容需要的字节数
                tempAddr = newAddr
                while tempAddr != 0:
                    tempAddr >>= 8
                    newByteNum += 1
                info[1] = newByteNum  # 只修改字节数
                sortedJumpEdgeInfo[index] = info

                # 下面根据是否能填入，进行地址填入
                offset = newByteNum - originalByteNum
                if offset <= 0:  # 原有的字节数已经足够表示新地址，不需要移动，直接填入新内容即可
                    newAddrBytes = deque()  # 新地址的字节码
                    while newAddr != 0:
                        newAddrBytes.appendleft(newAddr & 0xff)  # 取低八位
                        newAddr >>= 8
                    for i in range(-offset):  # 高位缺失的字节用0填充
                        newAddrBytes.appendleft(0x00)
                    for i in range(originalByteNum):  # 按原来的字节数填
                        self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset + 1 + i] = newAddrBytes[
                            i]  # 改的是地址，因此需要+1
                else:  # 新内容不能直接填入，原位置空间不够，需要移动字节码
                    self.log.warning("原push位置:{}不能直接填入新地址:{}，需要移动字节码".format(pushAddr, newAddr))
                    # 先改push的操作码
                    originalOpcode = 0x60 + originalByteNum - 1
                    newOpcode = originalOpcode + offset
                    # print(originalOpcode, newOpcode)
                    assert 0x60 <= newOpcode <= 0x7f
                    self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset] = newOpcode

                    # 然后再改地址
                    if offset > 0:
                        for i in range(offset):
                            self.blocks[pushBlock].bytecode.insert(pushAddr - pushBlockOffset + 1, 0x00)  # 插入足够的位置
                    else:
                        for i in range(-offset):
                            self.blocks[pushBlock].bytecode.pop(pushAddr - pushBlockOffset + 1)  # 删掉多出的位置
                    # 改地址
                    # for i in range(newByteNum):
                    #     self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset + 1 + i] = newAddrBytes[
                    #         i]  # 改的是地址，因此需要+1
                    # 不改地址，因为会进行下一次的试填入，而且下一次试填入时必然是可以填入的，会填入新地址

                    # 接着，需要修改新旧地址映射，以及跳转信息中的字节量（供下一次试填入使用)
                    for original in self.originalToNewAddr.keys():
                        if original > info[2]:
                            self.originalToNewAddr[original] += offset  # 映射信息需要增加偏移量
                    # 最后需要改一些其他信息
                    self.blocks[pushBlock].length += offset
                    finishFilling = False  # 本次试填入失败
                    break  # 不再查看其他的跳转信息，重新开始再做试填入

        # 第五步，尝试将这些字节码拼成一个整体
        self.newBytecode1 = deque()  # 效率更高
        self.newBytecode2 = deque()
        for node in self.nodes:  # 有序的
            if node < self.cfg.exitBlockId:
                for bc in self.blocks[node].bytecode:
                    self.newBytecode1.append(bc)
            elif node > self.cfg.exitBlockId:
                for bc in self.blocks[node].bytecode:
                    self.newBytecode2.append(bc)
        # print(sortedJumpEdgeInfo)

        # 第六步，修改各个block的偏移量，添加新的边信息
        # 这些修改都是用于输出新的cfg的图片
        newOffset = 0
        newToOriginal = {}
        originalToNew = {}
        for node in self.nodes:  # 有序的
            newToOriginal[newOffset] = node
            originalToNew[node] = newOffset
            self.blocks[node].offset = newOffset
            newOffset += self.blocks[node].length
        self.nodes = list(newToOriginal.keys())
        newBlocks = {}
        for node in self.nodes:
            newBlocks[node] = self.blocks[newToOriginal[node]]
        self.blocks = newBlocks
        self.cfg.exitBlockId = originalToNew[self.cfg.exitBlockId]
        newEdge = {}
        for node in self.nodes:
            newEdge[node] = []

        # 对于需要重定位的边
        for info in sortedJumpEdgeInfo:
            _from = originalToNew[info[4]]
            _to = originalToNew[info[0]]
            if self.blocks[_from].jumpType == "unconditional":
                newEdge[_from].append(_to)
            elif self.blocks[_from].jumpType == "conditional":
                newEdge[_from].append(_to)
                _to = _from + self.blocks[_from].length
                newEdge[_from].append(_to)
        # 对于不需要重定位的边
        for node in self.nodes:
            if self.blocks[node].jumpType == "terminal":
                newEdge[node].append(self.cfg.exitBlockId)
            elif self.blocks[node].jumpType == "fall":
                if node != self.cfg.exitBlockId:  # exit节点默认也是fall类型
                    newEdge[node].append(node + self.blocks[node].length)
        self.edges = newEdge
        # for b in self.blocks.values():
        #     b.printBlockInfo()

        # translator = OpcodeTranslator(self.cfg.exitBlockId)
        # for node in self.blocks.keys():
        #     self.blocks[node].instrs = translator.translate(self.blocks[node])
        # self.blocks[299].printBlockInfo()
        # self.blocks[308].printBlockInfo()
        # 第七步，将相邻的，本应该连在一起的block合成一个大的block
        self.nodes.sort()
        removedNode = []
        index = 0
        while index < self.nodes.__len__() - 1:
            node = self.nodes[index]
            nextNode = self.nodes[index + 1]
            if self.cfg.exitBlockId in [node, nextNode]:
                index += 1
                continue
            lastByte = self.blocks[node].bytecode[-1]
            nextBlockFirstByte = self.blocks[nextNode].bytecode[0]
            if lastByte not in [0x56, 0x57] and nextBlockFirstByte != 0x5b:
                # 不以jump/jumpi结尾，而且不以jumpdest开头的两个block
                combinedNode = [node, nextNode]
                index += 1
                while index < self.nodes.__len__() - 1:
                    node = self.nodes[index]
                    nextNode = self.nodes[index + 1]
                    if self.cfg.exitBlockId == nextNode:
                        break
                    lastByte = self.blocks[node].bytecode[-1]
                    nextBlockFirstByte = self.blocks[nextNode].bytecode[0]
                    if lastByte not in [0x56, 0x57] and nextBlockFirstByte != 0x5b:
                        combinedNode.append(nextNode)
                        index += 1
                    else:
                        break
                for node in combinedNode:
                    if node == combinedNode[0]:
                        continue
                    removedNode.append(node)
                    self.blocks[combinedNode[0]].length += self.blocks[node].length
                    self.blocks[combinedNode[0]].bytecode.extend(self.blocks[node].bytecode)
                for _to in self.edges[combinedNode[-1]]:
                    self.edges[combinedNode[0]].append(_to)
                self.edges.pop(combinedNode[-1])
            else:
                index += 1
        for node in removedNode:
            self.nodes.remove(node)
            self.blocks.pop(node)
        # self.blocks[299].printBlockInfo()

    def __outputFile(self):
        '''
        将修改后的cfg写回到文件中
        :return:
        '''
        # for b in self.blocks.values():
        #     b.printBlockInfo()

        # 第二步，获取原文件中，在函数体之前的以及之后的字符串，同时将其与新函数体的字符串拼接起来
        preStr = self.originalBytecodeStr[:self.funcBodyStrBeginIndex]
        postStr = self.originalBytecodeStr[self.funcBodyStrBeginIndex + self.originalLength * 2:]
        newFuncBodyStr1 = "".join(['{:02x}'.format(num) for num in self.newBytecode1])  # 再转换回字符串
        newFuncBodyStr2 = "".join(['{:02x}'.format(num) for num in self.newBytecode2])  # 再转换回字符串
        newBytecodeStr = preStr + newFuncBodyStr1 + postStr + newFuncBodyStr2

        # 第三步，将结果写入文件
        with open(self.outputFile, "w+") as f:
            f.write(newBytecodeStr)

    def outputNewCfgPic(self):
        # 测试使用，将新的cfg输出为图片，方便检查
        self.blocks[self.cfg.exitBlockId].bytecode = bytearray()
        self.blocks[self.cfg.exitBlockId].length = 0
        translator = OpcodeTranslator(self.cfg.exitBlockId)
        for node in self.blocks.keys():
            self.blocks[node].instrs = translator.translate(self.blocks[node])

        # for b in self.blocks.values():
        #     b.printBlockInfo()
        G = Digraph(name="G",
                    node_attr={'shape': 'box',
                               'style': 'filled',
                               'color': 'black',
                               'fillcolor': 'white',
                               'fontname': 'arial',
                               'fontcolor': 'black'
                               }
                    )
        G.attr(bgcolor='transparent')
        G.attr(rankdir='UD')
        for node in self.nodes:
            if self.blocks[node].instrs.__len__() == 0 and node != self.cfg.exitBlockId:
                continue
            if node == self.cfg.initBlockId:
                G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l", fillcolor='gold',
                       shape='Msquare')
            elif node == self.cfg.exitBlockId:
                G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l", fillcolor='crimson',
                       )
            elif self.blocks[node].blockType == "dispatcher":
                if self.blocks[node].jumpType != "terminal":
                    G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l", fillcolor='lemonchiffon'
                           )
                else:
                    G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l", fillcolor='lemonchiffon',
                           color='crimson', shape='Msquare')
            elif self.blocks[node].jumpType == "terminal":  # invalid
                G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l", color='crimson',
                       shape='Msquare')
            else:
                G.node(name=str(node), label="\l".join(self.blocks[node].instrs) + "\l")

        for _from in self.edges.keys():
            for _to in self.edges[_from]:
                G.edge(str(_from), str(_to))
        G.render(filename=sys.argv[0] + "_regenerate_bytecode.gv",
                 outfile=sys.argv[0] + "_regenerate_bytecode.png", format='png')
