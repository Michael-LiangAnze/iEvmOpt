from collections import deque

from graphviz import Digraph
from z3 import *

from AssertionOptimizer.Function import Function
from AssertionOptimizer.JumpEdge import JumpEdge
from AssertionOptimizer.Path import Path
from AssertionOptimizer.PathGenerator import PathGenerator
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from AssertionOptimizer.TagStacks.TagStack import TagStack
from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from GraphTools import DominatorTreeBuilder
from GraphTools.GraphMapper import GraphMapper
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from Utils import Stack, DotGraphGenerator
import json
from Utils.Logger import Logger

# 调试用
from Utils.OpcodeTranslator import OpcodeTranslator

fullyRedundant = "fullyRedundant"
partiallyRedundant = "partiallyRedundant"
nonRedundant = "nonRedundant"


class AssertionOptimizer:
    def __init__(self, constructorCfg: Cfg, cfg: Cfg, constructorDataSegStr: str, dataSegStr: str, outputFile: str,
                 outputProcessInfo: bool = False):
        """
        对部分冗余和完全冗余进行优化，并重新生成字节码
        :param constructorCfg:构造部分cfg
        :param cfg:运行时函数体的cfg
        :param constructorDataSegStr:构造部分数据段字符串
        :param dataSegStr:数据段字符串
        :param outputFile: 输出文件的路径
        :param outputProcessInfo:是否输出处理过程信息，默认为不输出
        """
        self.constructorCfg = constructorCfg
        self.cfg = cfg
        self.constructorDataSegStr = constructorDataSegStr
        self.dataSegStr = dataSegStr
        self.blocks = self.cfg.blocks  # 存储基本块，格式为 起始offset:BasicBlock
        self.outputFile = outputFile  # 处理后的新文件
        self.log = Logger()
        self.outputProcessInfo = outputProcessInfo

        # 函数识别、处理时需要用到的信息
        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.edges = self.cfg.edges  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = self.cfg.inEdges  # 存储入边表，格式为 to:[from1,from2...]
        self.funcCnt = 0  # 函数计数
        self.funcDict = {}  # 记录找到的所有函数，格式为：  funcId:function
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
        self.fullyRedundantInvNodes = []  # 全部的完全冗余的invalid节点
        self.partiallyRedundantInvNodes = []  # 全部的部分冗余的invalid节点
        self.abandonedFullyRedundantInvNodes = []  # 放弃优化的完全冗余invalid节点
        self.abandonedpartiallyRedundantInvNodes = []  # 放弃优化的部分冗余invalid节点
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

        # 重新生成函数体代码的信息
        self.originalToNewAddr = {}  # 一个映射，格式为： 旧addr:新addr
        self.constructorOpcode = None  # constructor的字节码
        self.newFuncBodyOpcode = None  # 原函数体相关的字节码

        self.constructorFuncBodyLength = self.constructorCfg.bytecodeLength
        self.funcBodyLength = self.cfg.bytecodeLength
        self.constructorDataSegLength = self.constructorDataSegStr.__len__() // 2
        self.dataSegLength = self.dataSegStr.__len__() // 2

        # copdcopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]
        self.codeCopyInfo = None
        # 构造函数重定位需要用到的信息
        self.runtimeDataSegOffset = 0  # 运行时的数据段的移动偏移量，即运行时的函数体总长度变化的偏移量
        self.isProcessingConstructor = False  # 是否正在对构造函数进行分析

    def optimize(self):
        self.log.info("开始进行字节码分析")
        if self.outputProcessInfo:
            self.log.processing("\n\n以下是原字节码文件的长度信息:")
            self.log.processing("构造函数的函数体长度为:{}".format(self.constructorFuncBodyLength))
            self.log.processing("构造函数的数据段长度为:{}".format(self.constructorDataSegLength))
            self.log.processing("运行时的函数体长度为:{}".format(self.funcBodyLength))
            self.log.processing("运行时的数据段长度为:{}\n".format(self.dataSegLength))

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
            "一共找到{}个待优化的assertion，具体为：{}个完全冗余{}，{}个部分冗余{}，{}个不冗余{}".format(
                self.invalidNodeList.__len__(), self.fullyRedundantInvNodes.__len__(),
                self.fullyRedundantInvNodes.__str__(),
                self.partiallyRedundantInvNodes.__len__(), self.partiallyRedundantInvNodes.__str__(),
                self.nonRedundantInvNodes.__len__(), self.nonRedundantInvNodes.__str__()))
        if self.fullyRedundantInvNodes.__len__() == 0 and self.partiallyRedundantInvNodes.__len__() == 0:
            self.log.info("不存在可优化的Assertion，优化结束")
            return

        # 这里需要注意，只有在部分冗余的处理函数里，才会将exit Block假装成数据段
        # 因此，如果只有完全冗余，没有部分冗余，这时候也要执行部分冗余的函数，此时部分冗余的函数只会做假装的工作
        if self.fullyRedundantInvNodes.__len__() > 0:  # 存在完全冗余的情况
            self.log.info("正在对完全冗余的Assertion进行优化")
            self.__optimizeFullyRedundantAssertion()
            if self.partiallyRedundantInvNodes.__len__() == 0:  # 不存在部分冗余的情况
                self.__optimizePartiallyRedundantAssertion()  # 关键
            self.log.info("完全冗余Assertion优化完毕")
        if self.partiallyRedundantInvNodes.__len__() > 0:
            self.log.info("正在对部分冗余的Assertion进行优化")
            self.__optimizePartiallyRedundantAssertion()
            self.log.info("部分冗余Assertion优化完毕")

        # 重新生成运行时的字节码序列
        self.log.info("正在重新生成运行时字节码序列")
        self.__regenerateRuntimeBytecode()
        self.log.info("运行时字节码序列生成完毕")

        # 重新生成构造函数的字节码序列
        self.log.info("正在重新生成构造函数字节码序列")
        # self.__regenerateConstructorBytecode()
        # 两套方案：
        #   一套是尝试修复构造函数，然后用处理运行时函数的步骤来处理构造函数
        #   一套是只改构造函数内的codecopy
        # 要切换回第一套方案，只需要使用上面的函数，并在ethersolver里取消修复构造函数的注释即可
        self.__processCodecopyInConstructor()
        self.log.info("构造函数字节码序列生成完毕")

        if self.outputProcessInfo:
            self.log.processing("\n\n以下是新字节码文件的长度信息:")
            self.log.processing("构造函数的函数体长度为:{}".format(self.constructorOpcode.__len__()))
            self.log.processing("构造函数的数据段长度为:{}".format(self.constructorDataSegLength))
            self.log.processing("运行时的函数体长度为:{}".format(self.newFuncBodyOpcode.__len__()))
            self.log.processing("运行时的数据段长度为:{}".format(self.dataSegLength))

        # 将优化后的运行时字节码写入文件
        self.log.info("正在将优化后的字节码写入到文件: {}".format(self.outputFile))
        self.__outputFile()
        self.log.info("写入完毕")

    def __identifyAndCheckFunctions(self):
        """
        识别所有的函数
        给出三个基本假设：
        1. 同一个函数内的指令的地址都是从小到大连续的
        2. 任何函数调用的起始边，必然是伴随这样两条指令产生的：PUSH 返回地址;JUMP
        3. 任何函数调用的返回边，必然不是这样的结构：PUSH 返回地址;JUMP
        给出一个求解前提：
           我们不关心函数调用关系产生的“错误的环”，因为这种错误的环我们可以在搜索路径时，可以通过符号执行或者返回地址栈解决掉
        """

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
                    # 真的有，见test12
                    # assert not (n.blockType == "dispatcher" and self.cfg.blocks[_to].blockType == "dispatcher")
                    # if n.blockType == "dispatcher" and self.cfg.blocks[_to].blockType == "dispatcher": # 两个点都在dispatcher里，不认为是函数
                    #     continue
                    e = JumpEdge(n, self.cfg.blocks[_to])
                    self.uncondJumpEdge.append(e)
        # for e in self.uncondJumpEdge:
        #     e.output()

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
                    continue
                e1, e2 = self.uncondJumpEdge[i], self.uncondJumpEdge[j]  # 取出两个不同的边进行匹配
                if e1.tetrad[0] == e2.tetrad[2] and e1.tetrad[1] == e2.tetrad[3] and e1.tetrad[
                    0] is not None:  # 匹配成功，e1为调用边，e2为返回边。注意None之间是不匹配的
                    # 4.21新问题：如果是添加了修复边的话，可能会出现，调用边不是push addr,jump的结构
                    # 比如说 AND JUMP。此时要多加一个限制，就是调用边指向的节点的offset，要比返回边的起始节点小
                    if e1.targetNode > e2.beginNode:
                        continue
                    e1.isCallerEdge = True
                    e2.isReturnEdge = True
                    self.isFuncBodyHeadNode[e1.targetNode] = True
                    key = [e1.targetNode, e2.beginNode].__str__()
                    value = [e1.beginNode, e2.targetNode]
                    if key not in funcRange2Calls.keys():
                        funcRange2Calls[key] = []
                    funcRange2Calls[key].append(value)
        # for k, v in funcRange2Calls.items():
        #     print(k, v)

        originalInEdge = {}
        for _from, tos in self.inEdges.items():
            originalInEdge[_from] = []
            for _to in tos:
                originalInEdge[_from].append(_to)

        # 第四步，在caller的jump和返回的jumpdest节点之间加边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].append(pair[1])
                self.inEdges[pair[1]].append(pair[0])

        # # 按组赋颜色
        # groupId = 0
        # groups = dict(zip(self.nodes, [0 for i in range(0, len(self.nodes))]))
        # for rangeInfo in funcRange2Calls.keys():
        #     offsetRange = json.loads(rangeInfo)
        #     groupId += 1
        #     for node in self.nodes:
        #         if node in range(offsetRange[0], offsetRange[1] + 1):
        #             # assert groups[node] == 0  # 不能是赋值过的
        #             groups[node] = groupId
        # # 不是common节点，赋上其他颜色。这样，没有和函数关联的节点，便是透明的
        # groupId += 1
        # for node in self.nodes:
        #     if self.blocks[node].blockType != 'common':
        #         groups[node] = groupId
        # length = dict(zip(self.nodes, [b.length for b in self.blocks.values()]))
        # # g3 = DotGraphGenerator(self.nodes, self.edges, groups, length)
        # g3 = DotGraphGenerator(self.nodes, oldEdge, groups, length)
        # g3.genDotGraph(sys.argv[0], "tmp")

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
            # 先做一个检查，如果并没能找出所有的函数节点，则放弃这一个函数，因为下面会尝试寻找selfdestruct引起的函数
            # 检查方式是，看看所有找到的同一个函数的节点的长度拼起来，是否是其应有的长度
            offsetRange[1] -= 1
            funcLen = offsetRange[1] + self.cfg.blocks[offsetRange[1]].length - offsetRange[0]
            tempLen = 0
            for n in funcBody:
                tempLen += self.cfg.blocks[n].length
            if funcLen != tempLen:  # 没能找全节点
                continue

            # 检查通过，找全了函数节点，存储函数信息
            self.funcCnt += 1
            f = Function(self.funcCnt, offsetRange[0], offsetRange[1], funcBody, self.edges)
            self.funcDict[self.funcCnt] = f
            for node in funcBody:
                assert self.node2FuncId[node] is None  # 一个点只能被赋值一次
                self.node2FuncId[node] = self.funcCnt

        # 第六步，尝试处理没有返回边selfdestruct函数
        # 注意，有些selfdestruct函数是有返回边的，我们处理的是没有返回边的情况
        # 一个假设：selfdestruct函数若没有返回边，则应当返回的节点（编译器生成的，但是实际上不会走到的block）应当是：JUMPDEST；STOP
        # 同时，为了及早放弃优化一些没有入边的合约，这里顺带记录没有入边的节点，如果最后发现存在没有入边的节点，它并不具备selfdestruct的特征
        # 则直接放弃优化

        selfdestructNode = []
        withoutInedgeNode = []
        for offset, b in self.blocks.items():
            if offset == 0:
                continue
            if originalInEdge[offset].__len__() == 0:  # 没有入边
                withoutInedgeNode.append(offset)
            else:
                continue
            if b.length != 2:
                continue
            if b.bytecode[0] != 0x5b or b.bytecode[1] != 0x00:
                continue
            selfdestructNode.append(offset)
        if selfdestructNode.__str__() != withoutInedgeNode.__str__():  # 放弃优化
            self.log.fail("未能找全函数节点，放弃优化")
        self.nodes.sort()
        for node in selfdestructNode:
            # 找出这个可疑节点的上一个节点，它有可能是selfdestruct的调用节点
            callBlock = None
            for b in self.blocks.values():
                if b.offset + b.length == node:
                    callBlock = b
                    break
            # 检查这个节点是否为为可能的调用者节点
            if not callBlock.couldBeCaller:
                continue
            # 检查这个节点里面push，是否压入了相应的地址，没有则不进行处理
            hasReturnAddr = False
            for addr in callBlock.instrAddrs:
                i = addr - callBlock.offset
                if callBlock.bytecode[i] in range(0x60, 0x80):  # push指令
                    pushData = int(callBlock.instrs[i].split(" ")[2], 16)
                    if pushData == node:  # push的内容与返回地址一致
                        hasReturnAddr = True
                        break
                if hasReturnAddr:
                    break
            if not hasReturnAddr:
                continue
            # 从起始节点开始做dfs，看是否能够走完这个函数
            funcBegin = self.edges[callBlock.offset][0]  # 因为是push addr;jump因此只有一条出边
            funcRange = range(funcBegin, self.cfg.exitBlockId)
            funcBody = []
            stack = Stack()
            visited = {}
            visited[funcBegin] = True
            stack.push(funcBegin)  # 既是范围一端，也是起始节点的offset
            while not stack.empty():  # dfs找出所有节点
                top = stack.pop()
                funcBody.append(top)
                for out in self.edges[top]:
                    if out not in visited.keys() and out in funcRange:
                        stack.push(out)
                        visited[out] = True
            # 检查找出的是否为同一个函数内的节点，并且节点这些节点中是否存在selfdestruct指令
            funcBody.sort()
            findAll = True
            for i in range(funcBody.__len__() - 1):
                curBlock, nextBlock = self.blocks[funcBody[i]], self.blocks[funcBody[i + 1]]
                if curBlock.offset + curBlock.length != nextBlock.offset:
                    findAll = False
                    break
            findSelfDestruct = False
            for n in funcBody:
                curBlock = self.blocks[n]
                for addr in curBlock.instrAddrs:
                    opcode = curBlock.bytecode[addr - n]
                    if opcode == 0xff:
                        findSelfDestruct = True
                        break
                if findSelfDestruct:
                    break
            if not findAll or not findSelfDestruct:
                # 这不仅代表着，寻找函数节点的失败，也是合约优化的失败
                self.log.fail("未能找全函数节点，放弃优化")

            # 找到了selfdestruct函数，将其标出
            self.funcCnt += 1
            f = Function(self.funcCnt, funcBody[0], funcBody[-1], funcBody, self.edges)
            self.funcDict[self.funcCnt] = f
            for n in funcBody:
                assert self.node2FuncId[n] is None  # 一个点只能被赋值一次
                self.node2FuncId[n] = self.funcCnt
            if self.isProcessingConstructor:
                self.log.info("构造函数中发现对selfdestruct函数的调用，无入边节点:{}修复成功".format(str(node)))
            else:
                self.log.info("运行时函数中发现对selfdestruct函数的调用，无入边节点:{}修复成功".format(str(node)))

        # 最后还要做一个检查，检查是否所有的common节点都被标记为了函数
        for offset, b in self.blocks.items():
            if b.blockType == "common" and self.node2FuncId[offset] is None:
                self.log.fail("未能找全函数节点，放弃优化")

        # 第七步，检查一个函数内的节点是否存在环，存在则将其标记出来
        for func in self.funcDict.values():  # 取出一个函数
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
        for offset, block in self.blocks.items():
            if block.blockType == "common":
                if self.node2FuncId[offset] == None:  # 没有标记
                    self.log.fail("未能找全所有的函数节点，放弃优化")
                else:
                    continue

        # 第八步，因为dispatcher中也有可能存在scc，因此需要将它们也标记出来
        # 4.21新问题：dispatcher也可能被识别为函数体，如在KOLUSDTFund.bin的构造函数中，某些函数体就是由dispatcher节点构成的
        # 因此，讨论dispatcher中scc的问题时，应当考虑的是，非函数的非common节点
        # 先生成子图
        nonCommonNodes = []  # 如果从0开始，一次走不完，则取一个非common节点开始（可能是common、fallback
        subGraphEdges = {}  # 子图的边
        for offset, block in self.blocks.items():
            # if block.blockType == "dispatcher":
            if block.blockType != "common" and self.node2FuncId[offset] is None:
                nonCommonNodes.append(offset)
                subGraphEdges[offset] = []
        checkSet = set(nonCommonNodes)
        for node in nonCommonNodes:
            for out in self.edges[node]:
                if out in checkSet:  # 找到一个指向内部节点的边
                    subGraphEdges[node].append(out)
        tarjan = TarjanAlgorithm(nonCommonNodes, subGraphEdges)
        tarjan.tarjan(0)
        for node in nonCommonNodes:
            if not tarjan.visited[node]:
                tarjan.tarjan(node)
        sccList = tarjan.getSccList()
        for scc in sccList:
            if len(scc) > 1:  # 找到函数内的一个强连通分量
                for node in scc:  # 将这些点标记为loop-related
                    self.isLoopRelated[node] = True
                    if self.isFuncBodyHeadNode[node]:  # 函数头存在于scc，出现了递归的情况
                        self.log.fail("检测到函数递归调用的情况，该字节码无法被优化!")

        # 第九步，处理可能出现的“自环”，见test12
        for node in self.nodes:
            if node in self.edges[node]:  # 出边指向自己
                self.isLoopRelated[node] = True

        # 第十步，去除之前添加的边，因为下面要做路径搜索，新加入的边并不是原来cfg中应该出现的边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].remove(pair[1])
                self.inEdges[pair[1]].remove(pair[0])

    def __searchPaths(self):
        """
        从cfg的起始节点开始做dfs，完成以下几项任务（注意，这个dfs是经过修改的）：
        1.找出所有从init节点到所有invalid节点的路径
        2.寻路过程中，同时进行tagStack的记录，从而找到所有jump/jumpi的边的地址是何处被push的
        3.在寻路过程中，找出是否存在环形函数调用链的情况。路径中包含相关节点的assertion同样不会被优化
        4.在寻路过程中，使用tagstack记录所有codecopy的参数在何处被push
        """
        # 第一步，找出所有的invalid节点
        for node in self.blocks.values():
            if node.isInvalid:
                self.invalidNodeList.append(node.offset)
        # print(self.invalidList)

        # 第二步，从起点开始做dfs遍历，完成提到的三个任务
        generator = PathGenerator(self.cfg, self.uncondJumpEdge, self.isLoopRelated,
                                  self.node2FuncId, self.funcDict)
        generator.genPath()
        paths = generator.getPath()

        self.jumpEdgeInfo = generator.getJumpEdgeInfo()
        self.codeCopyInfo = generator.getCodecopyInfo()
        # for p in paths:
        #     p.printPath()
        # for info in self.codeCopyInfo:
        #     print(info)

        # 第三步，做一个检查信息，看codecopy指令是否只是用于复制运行时的代码，或者是用于访问数据段的信息
        # codecopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block]]
        # 对于运行时的codecopy，假设其用于访问数据段，因此size是不做任何处理的，只关心offset的情况。
        #   如果offset是一个可以获得的数，则保留该codecopy；如果offset是untag，且被push的位置为codesize，则直接删除
        # 对于构造函数的codecopy，假设其用于访问数据段以及copy runtime，它的offset和size必须是untag的
        if not self.isProcessingConstructor:  # 正在分析的是runtimecfg
            removeList = []
            for info in self.codeCopyInfo:
                # print(info)
                offset = info[0]
                if offset is None:  # 为None，则只能是codesize
                    pushAddr, pushBlock = info[2], info[3]
                    if self.blocks[pushBlock].bytecode[pushAddr - pushBlock] == 0x38:  # 是codesize
                        removeList.append(info)
                    else:
                        self.log.fail("函数体的codecopy无法进行分析: offset未知:{}".format(info))
                elif offset in range(self.funcBodyLength,
                                     self.funcBodyLength + self.dataSegLength):  # 不是None，则offset只能在数据段，不能为代码段
                    # 以数据段的偏移量为开头，且长度不能超出数据段
                    continue
                else:
                    self.log.fail("函数体的codecopy无法进行分析: offset不在数据段内")
            for info in removeList:
                self.codeCopyInfo.remove(info)
        else:  # 正在分析的是构造函数cfg
            for info in self.codeCopyInfo:
                offset, _size = info[0], info[4]
                if offset in range(self.constructorFuncBodyLength,
                                   self.constructorFuncBodyLength + self.constructorDataSegLength):
                    # 访问的是构造函数的数据段
                    continue
                # 注意，offset可能是整个字节码的长度
                # elif offset in range(
                #         self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength,
                #         self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength + self.dataSegLength):
                elif offset >= self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength:
                    # 访问的是函数体后的数据段
                    continue
                # elif offset == self.constructorFuncBodyLength + self.constructorDataSegLength and _size == self.funcBodyLength + self.dataSegLength:
                elif offset == self.constructorFuncBodyLength + self.constructorDataSegLength:
                    # 用来复制运行时的代码，注意，size有可能小于函数体+数据段的长度
                    # 这里判断的方法为，offset为运行时的开头
                    continue
                else:
                    # 访问其他地址
                    # print(self.constructorFuncBodyLength + self.constructorDataSegLength,self.funcBodyLength + self.dataSegLength)
                    self.log.fail("构造函数的codecopy无法进行分析: offset为{}，size为{}".format(info[0], info[4]))

        # 第四步，将这些路径根据invalid节点进行归类
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

        # 第五步，对于一个Invalid节点，检查它的所有路径中，是否存在scc相关的节点
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

        # 第六步，对于每个可优化的invalid节点，将其所有路径根据函数调用链进行划分
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
        """
        可达性分析：对于一个invalid节点，检查它的所有路径是否可达，并根据这些可达性信息判断冗余类型
        :return:None
        """

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
            else:  # 有可达的路径，不是完全冗余
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
        """
        对字节码中完全冗余的assertion进行优化，完成以下任务：
        1.对每个完全冗余的invalid，找出与invalid程序状态相同的地址targetAddr
        2.将targetAddr到invalid之间的所有指令置为空指令，同时记录删除信息
        :return:
        """
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
            # 根据evmopt中的注释，需要辨别路径上是否有SHA3指令，有则从SHA3指令开始，不保留内存状态
            # 这是例子：contracts/0x054bfcd07b64575c23c0045615b37b297e2e2929/bin/TokenERC20.bin
            # 如果谁看到了这里，并愿意修复这个问题，我在这里提前感谢了！
            # 我的代码暂时还是比evmopt里比较内存的部分优秀一点点的，毕竟它是直接放弃内存状态 :D
            pathNodes = self.invalidPaths[pathsOfCallChain[0]].pathNodes  # 随意取出一条路径
            sha3Exist = False
            for node in pathNodes:
                bytecode = self.blocks[node].bytecode
                addrs = self.blocks[node].instrAddrs
                for addr in addrs:
                    if bytecode[addr - node] == 0x20:
                        sha3Exist = True
                        break
                if sha3Exist:
                    break
            stateMap = {}  # 状态map，实际存储的是，地址处的指令在执行前的程序状态
            for node in pathNodes:
                executor.setBeginBlock(node)
                while not executor.allInstrsExecuted():  # block还没有执行完
                    offset, state = executor.getCurState()
                    if sha3Exist:  # 不再保留内存状态
                        stateList = state.split("<=>")
                        state = stateList[0] + "<=>" + stateList[2]
                    stateMap[offset] = state
                    executor.execNextOpCode()

            # 第二步，在支配树中，从invalid节点出发，寻找程序状态与之相同的地址
            # 因为在符号执行中，invalid指令没有做任何操作，因此invalid处的状态和执行完jumpi的状态是一致的
            # 即 targetState = stateMap[invNode]
            targetAddr = None
            targetNode = None
            targetState = stateMap[invNode]
            node = self.domTree[invNode]
            while node != 0:
                # self.blocks[node].printBlockInfo()
                addrs = self.blocks[node].instrAddrs
                for addr in reversed(addrs):  # 从后往前遍历
                    if stateMap[addr] == targetState:  # 找到一个状态相同的点
                        targetAddr = addr
                        targetNode = node
                node = self.domTree[node]

            # 新坑：assert里面调函数，并不是无副作用的，这时候会找不到程序状态相同的节点
            # assert targetAddr and targetNode, pathNodes  # 不能为none
            if targetAddr is None:
                self.abandonedFullyRedundantInvNodes.append(invNode)
                continue  # 放弃当前Assertion的优化
            # print(targetAddr, targetNode, pathNodes)
            assert self.blocks[targetNode].blockType != "dispatcher"  # 不应该出现在dispatcher中
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("找到和节点{}程序状态相同的地址:{}，对应的节点为:{}".format(invNode, targetAddr, targetNode))

            # 第三步，将这一段序列置为空指令，并且记录删除序列信息
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

        if self.abandonedFullyRedundantInvNodes.__len__() != 0:  # 有移除的invalid
            self.log.info(
                "放弃优化有副作用的Assertion:{}".format(",".join([str(n) for n in self.abandonedFullyRedundantInvNodes])))

    def __optimizePartiallyRedundantAssertion(self):
        """
        对字节码中部分冗余的assertion进行优化
        :return:
        """
        # # 第一步，修改原来exit block的长度以及内容，它的作用是替代合约字节码中的数据段，
        # # 方便在后面插入新构造的函数体
        # curLastNode = self.cfg.exitBlockId
        # self.blocks[curLastNode].length = 1 + self.dataSegLength  # 直接改exit block的长度，+1是因为00/fe
        # tempByteCode = bytearray()
        # for i in range(1 + self.dataSegLength):
        #     tempByteCode.append(0x1f)  # 指令置为空指令
        # self.blocks[curLastNode].bytecode = tempByteCode

        # 4.11新方法：
        # 第一步，直接删除原来的exitblock，新构建的函数体从exitblock的位置开始放置
        self.nodes.remove(self.cfg.exitBlockId)  # 弹出exitblock
        tempExitBlock = self.blocks[self.cfg.exitBlockId]  # 暂时存下来，后面不需要重新构架
        self.blocks.pop(self.cfg.exitBlockId)
        curLastNode = max(self.nodes)

        # 第二步，使用符号执行，找到程序状态与Invalid执行完之后相同的targetNode和targetAddr
        executor = SymbolicExecutor(self.cfg)
        for invNode in self.partiallyRedundantInvNodes:  # 在可达性分析中已经确认该节点是部分冗余的
            # 首先做一个检查，检查是否为jumpi的失败边走向Invalid，且该invalid节点只有一个入边
            assert self.cfg.inEdges[invNode].__len__() == 1
            assert invNode == self.cfg.blocks[self.cfg.inEdges[invNode][0]].jumpiDest[False]
            pathIds = self.invNodeToRedundantCallChain[invNode][0]  # 随意取出一条调用链
            pathNodes = self.invalidPaths[pathIds[0]].pathNodes  # 随意取出一条路径
            sha3Exist = False
            for node in pathNodes:
                bytecode = self.blocks[node].bytecode
                addrs = self.blocks[node].instrAddrs
                for addr in addrs:
                    if bytecode[addr - node] == 0x20:
                        sha3Exist = True
                        break
                if sha3Exist:
                    break
            stateMap = {}  # 状态map，实际存储的是，地址处的指令在执行前的程序状态
            executor.clearExecutor()
            for node in pathNodes:
                executor.setBeginBlock(node)
                while not executor.allInstrsExecuted():  # block还没有执行完
                    offset, state = executor.getCurState()
                    if sha3Exist:  # 不再保留内存状态
                        stateList = state.split("<=>")
                        state = stateList[0] + "<=>" + stateList[2]
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
            # 没有找到程序状态相同的节点，放弃优化
            if targetAddr is None:
                self.abandonedpartiallyRedundantInvNodes.append(invNode)
                continue  # 放弃当前Assertion的优化

            assert self.cfg.blocks[targetNode].blockType != "dispatcher"  # 不应该出现在dispatcher中
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("找到和节点{}程序状态相同的地址:{}，对应的节点为:{}".format(invNode, targetAddr, targetNode))

            # 第四步，暂时不构造新的函数体，只是将invNode添加到对应函数，并记录冗余的地址区间
            targetFuncId = self.node2FuncId[invNode]
            self.funcDict[targetFuncId].addPartiallyInvalidNode(invNode)
            if self.inEdges[invNode + 1].__len__() == 1:  # jumpdest只有一个入边，要把它也删除掉
                self.funcDict[targetFuncId].addRemovedRangeInfo(invNode, [targetAddr, targetNode, invNode + 2])
            else:  # 不止一个入边，不删jumpdest
                self.funcDict[targetFuncId].addRemovedRangeInfo(invNode, [targetAddr, targetNode, invNode + 1])

        if self.abandonedFullyRedundantInvNodes.__len__() != 0:  # 有移除的invalid
            self.log.info(
                "放弃优化有副作用的Assertion:{}".format(",".join([str(n) for n in self.abandonedFullyRedundantInvNodes])))

        # 第五步，对每一个包含部分冗余的函数体，都构造一个新函数体，其中去除了assertion相关的字节码
        # 同时，将旧函数体节点的对应信息，添加到新函数体中去
        for funcId, func in self.funcDict.items():  # 取出一个函数
            invNodes = func.getInvalidNodes()
            if invNodes.__len__() == 0:
                continue
            # 添加一个新函数体到数据段后面
            funcBodyNodes = func.funcBodyNodes
            funcBodyNodes.sort()  # 从小到大一个个加
            offset = curLastNode + self.blocks[curLastNode].length - funcBodyNodes[0]  # 两个函数体之间的偏移量
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
                self.nodes.append(beginOffset)
                self.blocks[beginOffset] = newBlock
                self.removedRange[beginOffset] = []
                self.runtimeDataSegOffset += originalBlock.length  # 数据段后移
                curLastNode = beginOffset

            # 添加部分冗余删除序列信息
            for invNode in invNodes:
                info = func.getRemovedRangeInfo(invNode)
                for node in funcBodyNodes:
                    if info[1] <= node < info[2]:  # 节点中存在要删除的序列
                        beginAddr = max(node, info[0]) + offset
                        endAddr = min(node + self.blocks[node].length, info[2]) + offset
                        self.removedRange[node + offset].append([beginAddr, endAddr])

            # 将原函数体中已经存在的完全冗余删除序列信息，添加到新函数体中
            for node in funcBodyNodes:
                for info in self.removedRange[node]:
                    newInfo = list(info)
                    newInfo[0] += offset
                    newInfo[1] += offset
                    self.removedRange[node + offset].append(newInfo)

            # 找出各个冗余函数调用链的，新函数体的调用节点
            callerNodes = []
            for invNode in invNodes:  # 取出一个Invalid
                for callChain in self.invNodeToRedundantCallChain[invNode]:  # 取出相关的调用链路径
                    pathId = callChain[0]  # 在调用链上随意取出一条路径
                    pathNodes = self.invalidPaths[pathId].pathNodes
                    for node in reversed(pathNodes):
                        curNodeFuncId = self.node2FuncId[node]
                        if curNodeFuncId != funcId:  # 出了invalid的函数
                            callerNodes.append(node)
                            break
            returnedNodes = [node + self.blocks[node].length for node in callerNodes]  # 应当返回的节点

            # 添加跳转边信息，注意，这些边中有需要被移除的，只是暂时不处理，后面生成字节码的时候，会把出现在删除序列中的跳转信息删除掉
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
                    case 0b111:  # 1
                        newInfo.append(1)
                        newInfo.append(offset)
                        newJumpEdgeInfo.append(newInfo)
                    case 0b001:  # 2
                        if info[4] in callerNodes:  # 是新函数体的调用边
                            newInfo.append(2)
                            newInfo.append(offset)
                            newJumpEdgeInfo.append(newInfo)
                    case 0b011 | 0b010:  # 3
                        assert info[0] not in originalFuncRange  # 必须是返回边
                        if info[0] in returnedNodes:  # 是新函数体的返回边
                            newInfo.append(3)
                            newInfo.append(offset)
                            newJumpEdgeInfo.append(newInfo)
                    case 0b101 | 0b100:  # 4
                        assert info[0] in originalFuncRange  # 必须是返回到新函数体
                        newInfo.append(4)
                        newInfo.append(offset)
                        newJumpEdgeInfo.append(newInfo)
                    # 否则，不需要修改这条边信息
            for info in newJumpEdgeInfo:
                self.jumpEdgeInfo.append(info)

        # 第六步，将exit block放在函数字节码的最后面，用于填充原来的数据段的位置，防止codecopy重定位时，因为offset位于数据段而出错
        # 新坑：codecopy的offset刚好为整个字节码的长度，因此，exitBlock的长度设置为数据段的长度+1
        # 貌似这种情况只会出现在构造函数里，但是当时连这里也改了，代码也跑了没出错，就算了吧
        newBlockOffset = curLastNode + self.blocks[curLastNode].length
        self.nodes.append(newBlockOffset)
        tempExitBlock.length = self.dataSegLength + 1
        tempExitBlock.offset = newBlockOffset
        tempBytecode = bytearray()
        for i in range(tempExitBlock.length):
            tempBytecode.append(0x1f)  # 空指令
        tempExitBlock.bytecode = tempBytecode
        self.cfg.exitBlockId = newBlockOffset
        self.blocks[newBlockOffset] = tempExitBlock  # 复用之前的exit block
        self.removedRange[newBlockOffset] = []

    def __regenerateRuntimeBytecode(self):
        """
        重新生成运行时的字节码，同时完成重定位
        :return:None
        """
        # for info in self.codeCopyInfo:
        #     print(info)

        # 第一步，将codecopy信息转换成jump的信息，方便统一处理
        # 格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #          size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]
        # 如果处理的是运行时代码的信息，则转换的方式为：将前四个信息变成jump信息中的前四个，最后将codecopy指令的地址变成jump信息的第五个（即jump所在的block）。此时offset会发生剧烈的变化
        # 如果处理的是构造函数中信息，因为可能涉及到函数体后数据段的访问、运行时代码的复制，此时size会发生剧烈的变化
        # 因此，添加两个长度为7的跳转信息，专门用来处理这种情况：
        # 类型5：该信息是由codecopy中的offset信息修改而来的，在该情况下，push的addr需要加上offset，在第一次处理到这条信息时，会做试填入
        #       填入完成之后，变回成长度为5的普通信息
        # 类型6：该信息时由codecopy中的size信息修改而来，在该情况下，push的addr（即codecopy的size）需要加上offset，但是需要注意
        #       该信息不会被修改成长度为5的信息，同时，也不使用新旧地址的映射进行处理，因为size就是一个固定的值，不会随着代码的移动而发生变化
        # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选), 新老函数体之间的offset(可选)]]
        constructorTotalLen = self.constructorFuncBodyLength + self.constructorDataSegLength  # 构造函数的总长度
        runtimeTotalLen = self.funcBodyLength + self.dataSegLength  # 运行时的代码+数据段的总长度
        if not self.isProcessingConstructor:  # 如果当前处理的是运行时的代码
            for info in self.codeCopyInfo:
                newInfo = list(info[:4])
                newInfo.append(info[8])
                newInfo.append(5)
                newInfo.append(self.runtimeDataSegOffset)
                self.jumpEdgeInfo.append(newInfo)
        else:  # 当前处理的是构造函数的代码，则要根据不同情况进行处理
            for info in self.codeCopyInfo:
                if info[0] in range(self.constructorFuncBodyLength, constructorTotalLen):
                    # 访问的是构造函数的数据段，则只需要对codecopy offset重定位即可
                    newInfo = list(info[:4])
                    newInfo.append(info[8])
                    self.jumpEdgeInfo.append(newInfo)
                # offset可能是整个字节码的长度
                # elif info[0] in range(constructorTotalLen + self.funcBodyLength, constructorTotalLen + runtimeTotalLen):
                elif info[0] >= constructorTotalLen + self.funcBodyLength:
                    # 访问的是函数体后的数据段，则要修改为第5类信息，其中的offset为数据段移动的偏移量
                    # 只需要对codecopy offset做处理即可，size保持不变
                    newInfo = list(info[:4])
                    newInfo.append(info[8])
                    newInfo.append(5)
                    newInfo.append(self.runtimeDataSegOffset)
                    self.jumpEdgeInfo.append(newInfo)
                # elif info[0] == constructorTotalLen and info[4] == runtimeTotalLen:
                elif info[0] == constructorTotalLen:  # and info[4] >= self.funcBodyLength
                    # 用来复制运行时的代码，则要修改为第5类信息
                    # 注意，size不一定等于runtime的总程度，可能会出现：运行时函数体长度 <= size < 运行时总长度
                    # 对codecopy的offset，只需要对offset重定位即可
                    newInfo = list(info[:4])
                    newInfo.append(info[8])
                    self.jumpEdgeInfo.append(newInfo)
                    # 对codecopy的size，则要改为第6类信息，其中的offset为运行时代码段的位置变化偏移量
                    newInfo = list(info[4:])
                    newInfo.append(5)
                    # print(self.runtimeDataSegOffset)
                    newInfo.append(self.runtimeDataSegOffset)
                    self.jumpEdgeInfo.append(newInfo)
                else:  # 不应该出现的访问
                    assert 0

        # 第二步，对删除区间信息去重
        # 因为添加了从codecopy转换而来的跳转信息，而这些新添加的信息
        # 有可能是重复的，因此需要再对跳转信息做一次去重
        # 注意，对后者的去重只能现在做，因为信息中可能包含None，会触发json.loads错误
        for node in self.nodes:
            if self.removedRange[node].__len__() == 0:
                continue
            tempSet = set()
            for _range in self.removedRange[node]:
                tempSet.add(_range.__str__())  # 存为字符串
            self.removedRange[node] = []  # 置空
            for rangeStr in tempSet:
                self.removedRange[node].append(json.loads(rangeStr))  # 再还原为list
        tempSet = set()
        for info in self.jumpEdgeInfo:
            tempSet.add(info.__str__())
        self.jumpEdgeInfo = []
        for infoStr in tempSet:
            self.jumpEdgeInfo.append(json.loads(infoStr))

        # 第三步，将出现在已被删除字节码序列中的跳转信息删除
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
        #   跳转的type为5，该信息是由codecopy中的offset信息修改而来的，在该情况下，push的addr需要加上offset，在第一次处理到这条信息时，会做试填入。填入完成之后，变回成长度为5的普通信息
        #   跳转的type为6，该信息时由codecopy中的size信息修改而来，在该情况下，push的addr（即codecopy的size）需要加上offset，但是需要注意
        #         #       该信息不会被修改成长度为5的信息，同时，也不使用新旧地址的映射进行处理，因为size就是一个固定的值，不会随着代码的移动而发生变化
        #   类型5和6不需要做任何处理
        removedInfo = []
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
                    case 5 | 6:
                        continue
            jumpAddr = jumpBlock + self.blocks[jumpBlock].length - 1
            delPush = False
            delJump = False
            for _range in self.removedRange[pushBlock]:
                if _range[0] <= pushAddr < _range[1]:  # push语句位于删除序列内
                    delPush = True
                    break
            for _range in self.removedRange[jumpBlock]:
                if _range[0] <= jumpAddr < _range[1]:  # jump/jumpi/codecopy语句位于删除序列内
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

        # 第四步，对每一个block，删除空指令，同时还要记录旧地址到新地址的映射
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

        # 第五步，尝试将跳转地址填入
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
        #   跳转的type为5，该信息是由codecopy中的offset信息修改而来的，在该情况下，push的addr需要加上offset，在第一次处理到这条信息时，会做试填入。填入完成之后，变回成长度为5的普通信息
        #   跳转的type为6，该信息时由codecopy中的size信息修改而来，在该情况下，push的addr（即codecopy的size）需要加上offset，但是需要注意

        # 首先要根据push指令所在的地址，对这些信息进行一个排序(在路径生成器中已去重)
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
                #   跳转的type为5，该信息是由codecopy中的offset信息修改而来的，在该情况下，push的addr需要加上offset，在第一次处理到这条信息时，会做试填入。填入完成之后，变回成长度为5的普通信息
                #   跳转的type为6，该信息时由codecopy中的size信息修改而来，在该情况下，push的addr（即codecopy的size）需要加上offset，但是需要注意
                if info.__len__() == 7:  # 第一次读取到这种信息，需要重新计算
                    tempAddr = info[0]
                    tempPushAddr = info[2]
                    tempPushBlock = info[3]
                    tempJumpBlock = info[4]
                    offset = info[6]
                    newAddr = None
                    match info[5]:
                        case 0:
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                            info[4] = tempJumpBlock + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 1:
                            info[0] = tempAddr + offset
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                            info[4] = tempJumpBlock + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 2:
                            info[0] = tempAddr + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 3:
                            info[4] = tempJumpBlock + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 4:
                            info[0] = tempAddr + offset
                            info[2] = tempPushAddr + offset
                            info[3] = tempPushBlock + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 5:
                            info[0] = tempAddr + offset
                            newAddr = self.originalToNewAddr[info[0]]
                            info = info[:5]
                        case 6:
                            # 注意，该类型既不做地址映射（size保持不变），也不变成普通信息（否则会做地址映射）# 注意，该类型既不做地址映射（size保持不变），也不变成普通信息（否则会做地址映射）
                            info[0] = tempAddr + offset
                            newAddr = info[0]
                else:
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

                    for i in range(offset):
                        self.blocks[pushBlock].bytecode.insert(pushAddr - pushBlockOffset + 1, 0x00)  # 插入足够的位置
                    # 改地址
                    # for i in range(newByteNum):
                    #     self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset + 1 + i] = newAddrBytes[
                    #         i]  # 改的是地址，因此需要+1
                    # 不改地址，因为会进行下一次的试填入，而且下一次试填入时必然是可以填入的，会填入正确的新地址

                    # 接着，需要修改新旧地址映射，以及跳转信息中的字节量（供下一次试填入使用)
                    for original in self.originalToNewAddr.keys():
                        if original > info[2]:
                            self.originalToNewAddr[original] += offset  # 映射信息需要增加偏移量
                    # 最后需要改一些其他信息
                    self.blocks[pushBlock].length += offset
                    finishFilling = False  # 本次试填入失败
                    break  # 不再查看其他的跳转信息，重新开始再做试填入

        # 第六步，将这些字节码拼成一个整体
        tempFuncBodyLen = 0
        if not self.isProcessingConstructor:  # 当前处理的是runtime的部分
            self.blocks[self.cfg.exitBlockId].length = 0  # 此时exitblock不再代表数据段
            self.blocks[self.cfg.exitBlockId].bytecode = bytearray()
            self.newFuncBodyOpcode = deque()  # 效率更高
            for node in self.nodes:  # 有序的
                for bc in self.blocks[node].bytecode:
                    self.newFuncBodyOpcode.append(bc)
                tempFuncBodyLen += self.blocks[node].length
            self.runtimeDataSegOffset = tempFuncBodyLen - self.funcBodyLength  # 同时记录数据段的偏移量，用于构造函数中对数据段访问的重定位
            # self.funcBodyLength = tempFuncBodyLen # 暂时不改，保留原值，用于对构造函数进行分析
            # print(self.runtimeDataSegOffset,self.funcBodyLength)
            # print(sortedJumpEdgeInfo)
        else:  # 当前处理的是构造函数部分
            self.constructorOpcode = deque()  # 效率更高
            for node in self.nodes:  # 有序的
                if node < self.cfg.exitBlockId:  # 不是构造函数的函数字节码不要
                    for bc in self.blocks[node].bytecode:
                        self.constructorOpcode.append(bc)

    def __regenerateConstructorBytecode(self):
        """
        重新生成构建函数的字节码序列，任务有以下几个：
        1.进行函数识别和路径搜索，得到其中的跳转信息和codecopy信息
        2.根据获取到的信息进行重定位即可
        为了重用之前写过的代码，直接将当前的cfg信息改成constructorcfg的信息，并初始化相关数据结构即可
        :return:None
        """
        # print(self.runtimeDataSegOffset)
        self.isProcessingConstructor = True

        # 第一步，将constructorcfg设置为cfg，并初始化相关信息
        self.cfg = self.constructorCfg  # 重新设置cfg
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.blocks = self.cfg.blocks
        self.edges = self.cfg.edges  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = self.cfg.inEdges  # 存储入边表，格式为 to:[from1,from2...]

        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.funcCnt = 0  # 函数计数
        self.funcDict = {}  # 记录找到的所有函数，格式为：  funcId:function
        self.node2FuncId = dict(
            zip(self.nodes, [None for i in range(0, self.nodes.__len__())]))  # 记录节点属于哪个函数，格式为：  node：funcId
        self.isFuncBodyHeadNode = dict(
            zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 函数体头结点信息，用于后续做函数内环压缩时，判断某个函数是否存在递归的情况
        self.isLoopRelated = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 标记各个节点是否为loop-related
        self.isFuncCallLoopRelated = None  # 记录节点是否在函数调用环之内，该信息只能由路径搜索得到

        # 第二步，进行函数识别和路径搜索，得到其中的跳转信息和codecopy信息
        self.invalidNodeList = []  # 记录所有invalid节点的offset
        self.invalidPaths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidPathId:Path
        self.invalidNode2PathIds = {}  # 记录每个invalid节点包含的路径，格式为：  invalidNodeOffset:[pathId1,pathId2]
        self.invalidNode2CallChain = {}  # 记录每个invalid节点包含的调用链，格式为： invalidNodeOffset:[[callchain1中的pathid],[callchain2中的pathid]]

        self.__identifyAndCheckFunctions()
        self.__searchPaths()

        # 第三步，修改原来exit block的长度以及内容，它的作用是替代构造函数的数据段、函数代码段、数据段、新添加的函数
        # 方便做新旧地址映射
        # 新坑：有可能出现offset刚好为整个字节码长度的codecopy，因此需要将lastNodeLen + 1
        curLastNode = self.cfg.exitBlockId
        lastNodeLen = self.constructorDataSegLength + self.funcBodyLength + self.dataSegLength + self.runtimeDataSegOffset + 1
        self.blocks[curLastNode].length = lastNodeLen  # 直接改exit block的长度
        tempByteCode = bytearray()
        for i in range(lastNodeLen):
            tempByteCode.append(0x1f)  # 指令置为空指令
        self.blocks[curLastNode].bytecode = tempByteCode

        # 第四步，使用原来生成运行时函数的函数体，来生成新的构造函数函数体
        self.removedRange = dict(
            zip(self.nodes, [[] for i in range(0, len(self.nodes))]))  # 记录每个block中被移除的区间，每个区间的格式为:[from,to)
        self.originalToNewAddr = {}  # 一个映射，格式为： 旧addr:新addr
        self.__regenerateRuntimeBytecode()

    def __processCodecopyInConstructor(self):
        """
        4.24新思路：
        因为实际上，在构造函数里面，只需要处理codecopy即可，不需要过多处理重定位信息
        只在一种情况下，需要对重定位信息进行考虑：新的codecopy的size/offset无法填入原来的位置
        考虑到出现这种情况的概率非常小，同时，构造函数在做完ethersolve分析之后，出现没有入边的情况非常多
        后者出现的概率甚至可以达到，1200+份合约当中，出现了超过份
        因此这里做一个取舍：在构造函数里面，假设是不会出现无法填入的情况，也不做试填入。但是一旦出现了无法填入的情况，就立即放弃优化
        同时还做一个假设：所有在构造函数里的codecopy，其参数都是在同一个block内push进去的
        :return:
        """
        self.cfg = self.constructorCfg  # 重新设置cfg
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.blocks = self.cfg.blocks
        # 第一步，对构造函数的每一个block做tagStack执行，找出offset和size
        self.codeCopyInfo = []
        preInfo = [[None, None, None, None, False] for i in range(128)]
        pushInfo = None
        tagStack = TagStack(self.cfg)
        for offset, b in self.cfg.blocks.items():
            tagStack.clear()
            tagStack.setBeginBlock(offset)
            tagStack.setTagStack(preInfo)
            while not tagStack.allInstrsExecuted():
                opcode = tagStack.getOpcode()
                if opcode == 0x39:  # codecopy
                    tmpOffset = tagStack.getTagStackItem(1)
                    tmpSize = tagStack.getTagStackItem(2)
                    tmpOffset.extend(tmpSize)
                    self.codeCopyInfo.append(tmpOffset)
                tagStack.execNextOpCode()

        # 第二步，做一个检查信息，看codecopy指令是否只是用于复制运行时的代码，或者是用于访问数据段的信息
        # codecopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block]]
        #   对于构造函数的codecopy，假设其用于访问数据段以及copy runtime，它的offset和size必须是untag的
        for info in self.codeCopyInfo:
            offset, _size = info[0], info[4]
            if offset in range(self.constructorFuncBodyLength,
                               self.constructorFuncBodyLength + self.constructorDataSegLength):
                # 访问的是构造函数的数据段
                continue
            # 注意，offset可能是整个字节码的长度
            # elif offset in range(
            #         self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength,
            #         self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength + self.dataSegLength):
            elif offset >= self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength:
                # 访问的是函数体后的数据段
                continue
            # elif offset == self.constructorFuncBodyLength + self.constructorDataSegLength and _size == self.funcBodyLength + self.dataSegLength:
            elif offset == self.constructorFuncBodyLength + self.constructorDataSegLength:
                # 用来复制运行时的代码，注意，size有可能小于函数体+数据段的长度
                # 这里判断的方法为，offset为运行时的开头
                continue
            else:
                # 访问其他地址
                # print(self.constructorFuncBodyLength + self.constructorDataSegLength,self.funcBodyLength + self.dataSegLength)
                self.log.fail("构造函数的codecopy无法进行分析: offset为{}，size为{}".format(info[0], info[4]))

        # 第三步，根据运行时函数段的长度变化，修改这些codecopy信息
        # 同时需要检查，原来的字节数，是否能够填入新的内容
        for info in self.codeCopyInfo:
            offset, _size = info[0], info[4]
            offsetByteNum, sizeByteNum = info[1], info[5]
            newOffset, newSize = None, None
            if offset in range(self.constructorFuncBodyLength,
                               self.constructorFuncBodyLength + self.constructorDataSegLength):
                # 访问的是构造函数的数据段
                continue  # 什么都不改
            elif offset >= self.constructorFuncBodyLength + self.constructorDataSegLength + self.funcBodyLength:
                # 访问的是函数体后的数据段
                newOffset = info[0] + self.runtimeDataSegOffset
            elif offset == self.constructorFuncBodyLength + self.constructorDataSegLength:
                # 用来复制运行时的代码，注意，size有可能小于函数体+数据段的长度
                newSize = info[4] + self.runtimeDataSegOffset
            # 检查原字节数是否能填入
            if newOffset is not None:
                newByteNum = 0  # 新内容需要的字节数
                tmp = newOffset
                while tmp != 0:
                    tmp >>= 8
                    newByteNum += 1
                offset = newByteNum - offsetByteNum
                if offset > 0:
                    self.log.fail("构造函数的codecopy无法填入新信息")  # 程序已经结束
                newBytes = deque()  # 新地址的字节码
                while newOffset != 0:
                    newBytes.appendleft(newOffset & 0xff)  # 取低八位
                    newOffset >>= 8
                for i in range(-offset):  # 高位缺失的字节用0填充
                    newBytes.appendleft(0x00)
                for i in range(offsetByteNum):  # 按原来的字节数填
                    self.blocks[info[3]].bytecode[info[2] - info[3] + 1 + i] = newBytes[i]  # 改的是地址，因此需要+1
            if newSize is not None:
                newByteNum = 0  # 新内容需要的字节数
                tmp = newSize
                while tmp != 0:
                    tmp >>= 8
                    newByteNum += 1
                offset = newByteNum - sizeByteNum
                if offset > 0:
                    self.log.fail("构造函数的codecopy无法填入新信息")  # 程序已经结束
                newBytes = deque()  # 新地址的字节码
                while newSize != 0:
                    newBytes.appendleft(newSize & 0xff)  # 取低八位
                    newSize >>= 8
                for i in range(-offset):  # 高位缺失的字节用0填充
                    newBytes.appendleft(0x00)
                for i in range(sizeByteNum):  # 按原来的字节数填
                    self.blocks[info[7]].bytecode[info[6] - info[7] + 1 + i] = newBytes[i]  # 改的是地址，因此需要+1

        # 第四步，将构造字节码拼成一个新的整体
        self.constructorOpcode = deque()  # 效率更高
        self.nodes.sort()
        for node in self.nodes:
            if node < self.cfg.exitBlockId:  # 不是构造函数的函数字节码不要
                for bc in self.blocks[node].bytecode:
                    self.constructorOpcode.append(bc)

    def __outputFile(self):
        '''
        将修改后的cfg写回到文件中
        :return:
        '''
        constructorStr = "".join(['{:02x}'.format(num) for num in self.constructorOpcode])
        newFuncBodyStr = "".join(['{:02x}'.format(num) for num in self.newFuncBodyOpcode])
        with open(self.outputFile, "w+") as f:
            f.write(
                constructorStr + self.constructorDataSegStr + newFuncBodyStr + self.dataSegStr)

    def __outputNewCfgPic(self, picName: str):
        # 4.11 因为可以用ethersolve直接得出新的cfg图片，因此不再维护之前的边关系，并删除相关的代码，该方法作废
        return
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
        G.render(filename=sys.argv[0] + "_" + picName + ".gv",
                 outfile=sys.argv[0] + "_" + picName + ".png", format='png')
