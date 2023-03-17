import sys

from z3 import *

from AssertionOptimizer.Function import Function
from AssertionOptimizer.Path import Path
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from AssertionOptimizer.JumpEdge import JumpEdge
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from GraphTools.PathGenerator import PathGenerator
from GraphTools.SccCompressor import SccCompressor
from Utils import DotGraphGenerator, Stack
import json
from concurrent.futures import ThreadPoolExecutor
import threading
from Utils.Logger import Logger


class AssertionOptimizer:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.log = Logger()
        # 函数识别、处理时需要用到的信息
        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.edges = dict(self.cfg.edges)  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = dict(self.cfg.inEdges)  # 存储入边表，格式为 to:[from1,from2...]
        self.funcCnt = 0  # 函数计数
        self.funcBodyDict = {}  # 记录找到的所有函数，格式为：  funcId:function
        self.node2FuncId = dict(
            zip(self.nodes, [None for i in range(0, self.nodes.__len__())]))  # 记录节点属于哪个函数，格式为：  node：funcId
        self.isFuncBodyHeadNode = dict(
            zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 函数体头结点信息，用于后续做函数内环压缩时，判断某个函数是否存在递归的情况
        self.isLoopRelated = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 标记各个节点是否为loop-related
        self.isFuncCallLoopRelated = None  # 记录节点是否在函数调用环之内，该信息只能由路径搜索得到
        self.newNodeId = max(self.nodes) + 1  # 找到函数内的环之后，需要添加的新节点的id(一个不存在的offset)
        self.recursionExist = False  # 是否存在递归调用的情况，用于log输出

        # 路径搜索需要用到的信息
        self.invalidNodeList = []  # 记录所有invalid节点的offset
        self.invalidPathId = 0  # 路径id
        self.invalidPaths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidPathId:Path
        self.invalidNode2PathIds = {}  # 记录每个invalid节点包含的路径，格式为：  invalidNodeOffset:[pathId1,pathId2]
        self.invalidNode2CallChain = {}  # 记录每个invalid节点包含的调用链，格式为： invalidNodeOffset:[[callchain1中的pathid],[callchain2中的pathid]]

        # 可达性分析需要用到的信息
        self.constrains = {}  # 每条路径包含的约束
        self.pathReachable = {}  # 某条路径是否可达
        self.invNodeReachable = None  # 某个Invalid节点是否可达

    def optimize(self):
        self.log.info("开始进行字节码分析")

        # 首先识别出所有的函数体，将每个函数体内的强连通分量的所有点压缩为一个点，同时标记为loop-related
        self.__identifyFunctions()
        self.log.info("函数体识别完毕，一共识别到:{}个函数体".format(self.funcCnt))
        if self.recursionExist:  # 存在递归调用的情况
            self.log.warning("因为存在递归调用的情况，因此函数体识别的数量可能有误")

        # 然后找到所有invalid节点，找出他们到起始节点之间所有的边
        self.__searchPaths()
        callChainNum = 0
        for invNode in self.invalidNodeList:
            callChainNum += self.invalidNode2CallChain[invNode].__len__()

        self.log.info(
            "路径搜索完毕，一共找到{}个可优化的Invalid节点，一共找到{}条路径，{}条函数调用链".format(self.invalidNodeList.__len__(),
                                                                    self.invalidPaths.__len__(), callChainNum))

        # 求解各条路径是否可行
        self.__reachabilityAnalysis()

    def __identifyFunctions(self):
        '''
        识别所有的函数
        给出三个基本假设：
        1. 同一个函数内的指令的地址都是从小到大连续的
        2. 任何函数调用的起始边，必然是伴随这样两条指令产生的：PUSH 返回地址;JUMP
        3. 任何函数调用的返回边，必然不是这样的结构：PUSH 返回地址;JUMP
        给出一个求解前提：
           我们不关心函数调用关系产生的“错误的环”，因为这种错误的环我们可以在搜索路径时，可以通过符号执行或者返回地址栈解决掉
        '''
        # 第一步，找出所有unconditional jump的边
        for n in self.cfg.blocks.values():
            if n.jumpType == "unconditional":
                _from = n.offset
                for _to in self.edges[_from]:
                    # 这里做一个assert，防止出现匹配到两个节点都在dispatcher里面的情况，但是真的有吗？先不处理
                    assert not (n.blockType == "dispatcher" and self.cfg.blocks[_to].blockType == "dispatcher")
                    e = JumpEdge(n, self.cfg.blocks[_to])
                    self.uncondJumpEdge.append(e)
        # for e in self.uncondJumpEdge:
        #     print(e.tetrad)

        # 第二步，两两之间进行匹配
        funcRange2Calls = {}  # 一个映射，格式为:
        # 一个函数的区间(一个字符串，内容为"[第一条指令所在的block的offset,最后一条指令所在的block的offset]"):[[funcbody调用者的起始node,funcbody返回边的目的node]]
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

        # 第三步，在caller的jump和返回的jumpdest节点之间加边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].append(pair[1])
                self.inEdges[pair[1]].append(pair[0])

        # 第四步，从一个函数的funcbody的起始block开始dfs遍历，只走offset范围在 [第一条指令所在的block的offset,最后一条指令所在的block的offset]之间的节点，尝试寻找出所有的函数节点
        for rangeInfo in funcRange2Calls.keys():  # 找到一个函数
            offsetRange = json.loads(rangeInfo)  # 还原之前的list
            offsetRange[1] += 1  # 不用每次调用range函数的时候都加
            funcBody = []
            stack = Stack()
            visited = {}
            visited[offsetRange[0]] = True
            stack.push(offsetRange[0])  # 既是范围一端，也是起始节点的offset
            while not stack.empty():
                top = stack.pop()
                funcBody.append(top)
                for out in self.edges[top]:
                    if out not in visited.keys() and out in range(offsetRange[0], offsetRange[1]):
                        stack.push(out)
                        visited[out] = True
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

        # 第五步，检查一个函数内的所有节点是否存在环，是则将其压缩为一个点
        compressor = SccCompressor()
        for func in self.funcBodyDict.values():  # 取出一个函数
            tarjan = TarjanAlgorithm(func.funcBodyNodes, func.funcSubGraphEdges)
            tarjan.tarjan(func.firstBodyBlockOffset)
            sccList = tarjan.getSccList()
            for scc in sccList:
                if len(scc) > 1:  # 找到loop-related节点
                    # 标记
                    self.isLoopRelated[self.newNodeId] = True
                    self.isFuncBodyHeadNode[self.newNodeId] = False  # 这个点默认不是函数头，但是可能会是
                    for node in scc:
                        self.isLoopRelated[node] = True
                        # assert not self.isFuncBodyHeadNode[node]  # 函数头不应该出现在函数内的scc，否则可能会引起错误
                        if self.isFuncBodyHeadNode[node]:  # 函数头存在于scc，出现了递归的情况
                            self.isFuncBodyHeadNode[self.newNodeId] = True
                            self.recursionExist = True
                            self.log.warning("检测到函数递归调用的情况，该函数将不会被优化")
                    # 压缩为一个点，这个点也需要标记为loop-related，并标记为funcid
                    self.node2FuncId[self.newNodeId] = func.funcId
                    compressor.setInfo(self.nodes, scc, self.edges, self.inEdges, self.newNodeId)
                    compressor.compress()
                    self.nodes, self.edges, self.inEdges = compressor.getNodes(), compressor.getEdges(), compressor.getInEdges()
                    self.newNodeId += 1
        # g = DotGraphGenerator(self.edges, self.nodes)
        # g.genDotGraph(sys.argv[0], "_removed_scc")

        # 第六步，去除之前添加的边，因为下面要开始做路径搜索了，新加入的边并不是原来cfg中应该出现的边
        # 需要注意，因为前面已经做了scc压缩，要移除的边可能已经不存在了
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                if pair[0] in self.edges.keys():
                    if pair[1] in self.edges[pair[0]]:  # 边还存在
                        self.edges[pair[0]].remove(pair[1])
                        self.inEdges[pair[1]].remove(pair[0])
        # g = DotGraphGenerator(self.edges, self.nodes)
        # g.genDotGraph(sys.argv[0], "_removed_edge")

    def __searchPaths(self):
        '''
        找到所有的Invalid节点，并搜索从起点到他们的所有路径
        '''
        # 第一步，找出所有的invalid节点
        for node in self.cfg.blocks.values():
            if node.isInvalid:
                self.invalidNodeList.append(node.offset)
        # print(self.invalidList)

        # 第二步，搜索从起点到invalid节点的所有路径
        generator = PathGenerator(self.nodes, self.edges, self.uncondJumpEdge, self.isLoopRelated, self.node2FuncId,
                                  self.funcBodyDict)
        for invNode in self.invalidNodeList:
            generator.genPath(self.cfg.initBlockId, invNode)
            paths = generator.getPath()
            self.invalidNode2PathIds[invNode] = []
            for pathNodeList in paths:
                path = Path(self.invalidPathId, pathNodeList)
                self.invalidPaths[self.invalidPathId] = path
                self.invalidNode2PathIds[invNode].append(self.invalidPathId)
                self.invalidPathId += 1
        # for k, v in self.invalidNode2PathIds.items():
        #     print("invalid node is:{}".format(k))
        #     for pathId in v:
        #         self.invalidPaths[pathId].printPath()

        # 第三步，对于一个Invalid节点，检查它的所有路径中，是否存在
        # scc或者函数调用环相关的节点
        self.isFuncCallLoopRelated = generator.getFuncCallLoopRelated()
        removedInvPaths = []
        removedInvNodes = []
        for invNode in self.invalidNodeList:
            isProcess = True
            for pathId in self.invalidNode2PathIds[invNode]:
                for node in self.invalidPaths[pathId].pathNodes:
                    if self.isLoopRelated[node] or self.isFuncCallLoopRelated[node]:  # 存在
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
            self.invalidNode2PathIds.pop(node)
        for node in removedInvNodes:
            self.invalidNodeList.remove(node)

        # for k, v in self.invalidNode2PathIds.items():
        #     print("invalid node is:{}".format(k))
        #     for pathId in v:
        #         self.invalidPaths[pathId].printPath()
        # print(self.isFuncCallLoopRelated)

        # 第四步，对于每个可优化的invalid节点，将其所有路径根据函数调用链进行划分
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

        for k, v in self.invalidNode2PathIds.items():
            print("invalid node is:{}".format(k))
            for pathId in v:
                self.invalidPaths[pathId].printPath()
        print(self.invalidNode2CallChain)

    def __reachabilityAnalysis(self):
        '''
        可达性分析：对于一个invalid节点，检查它的所有路径是否可达
        :return:
        '''
        self.invNodeReachable = dict(zip(self.invalidNodeList, [False for i in range(self.invalidNodeList.__len__())]))
        executor = SymbolicExecutor(self.cfg)
        removedPath = []
        for invNode in self.invalidNodeList:
            for pathId in self.invalidNode2PathIds[invNode]:  # 取出一条路径
                self.pathReachable[pathId] = False
                executor.clearExecutor()
                self.constrains[pathId] = []
                nodeList = self.invalidPaths[pathId].pathNodes
                isSolve = True  # 默认是做约束检查的。如果发现路径走到了一个不应该到达的节点，则不做check，相当于是优化了过程
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
                        checkInfo = executor.checkIsCertainJumpDest()
                        if checkInfo[0]:  # 是一个固定的跳转地址
                            # 检查预期的跳转地址是否和栈的信息匹配
                            expectedTarget = self.cfg.blocks[curNode].jumpiDest[checkInfo[1]]
                            if nextNode != expectedTarget:  # 不匹配，直接置为不可达，后续不做check
                                self.pathReachable[pathId] = False
                                isSolve = False  # 不处理这一条路径了
                                self.log.info(
                                    "路径{}在实际运行中不可能出现：在节点{}处本应跳转到{}，却跳转到了{}".format(pathId, curNode, expectedTarget,
                                                                                   nextNode))
                                break
                        else:  # 不是固定的跳转地址
                            if nextNode == self.cfg.blocks[curNode].jumpiDest[True]:
                                self.constrains[pathId].append(executor.getJumpCond(True))
                            elif nextNode == self.cfg.blocks[curNode].jumpiDest[False]:
                                self.constrains[pathId].append(executor.getJumpCond(False))
                            else:
                                assert 0
                if isSolve:
                    s = Solver()
                    if s.check(self.constrains[pathId]) == sat:
                        self.pathReachable[pathId] = True
                    else:
                        self.pathReachable[pathId] = False

        # for pathId in removedPath:
        #     self.invalidPaths.pop(pathId)
        #     self.pathReachable.pop(pathId)
        #     self.constrains.pop(pathId)

        for pid, r in self.pathReachable.items():
            print(pid, r)
