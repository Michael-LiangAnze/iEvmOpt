import multiprocessing
import pickle
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

from z3 import *

from AssertionOptimizer.Function import Function
from AssertionOptimizer.JumpEdge import JumpEdge
from AssertionOptimizer.Path import Path
from AssertionOptimizer.PathGenerator import PathGenerator
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from AssertionOptimizer.TagStacks.TagStack import TagStack
from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from Cfg.EtherSolver import EtherSolver
from GraphTools import DominatorTreeBuilder
from GraphTools.GraphMapper import GraphMapper
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from Utils import Stack
import json
from Utils.Logger import Logger

from multiprocessing import Process, Queue, Pool
import multiprocessing
import threading

fullyRedundant = "fullyRedundant"
partiallyRedundant = "partiallyRedundant"
nonRedundant = "nonRedundant"


class AssertionOptimizer:
    def __init__(self, inputFile: str, outputPath: str, outputName: str, outputProcessInfo: bool = False,
                 outputHtml: bool = False):
        """
        对部分冗余和完全冗余进行优化，并重新生成字节码
        :param inputFile: 输入文件的路径
        :param outputPath: 输出文件的路径
        :param outputName: 输出文件的文件名
        :param outputProcessInfo:是否输出处理过程信息，默认为不输出
        :param outputHtml:是否输出HTML报告
        """

        # 输入输出路径文件
        self.inputFile = inputFile
        self.outputPath = outputPath
        self.outputName = outputName
        self.outputProcessInfo = outputProcessInfo
        self.outputHtml = outputHtml

        # 存储cfg需要用到的信息
        self.constructorCfg = None
        self.cfg = None
        self.constructorDataSegStr = None
        self.dataSegStr = None

        self.blocks = None  # 存储基本块，格式为 起始offset:BasicBlock

        self.log = Logger()

        # 函数识别、处理时需要用到的信息
        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.nodes = []  # 存储点，格式为 [n1,n2,n3...]
        self.edges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = {}  # 存储入边表，格式为 to:[from1,from2...]
        self.funcCnt = 0  # 函数计数
        self.funcDict = {}  # 记录找到的所有函数，格式为：  funcId:function
        self.node2FuncId = {}  # 记录节点属于哪个函数，格式为：  node：funcId
        self.isFuncBodyHeadNode = {}  # 函数体头结点信息，用于后续做函数内环压缩时，判断某个函数是否存在递归的情况
        self.isLoopRelated = {}  # 标记各个节点是否为loop-related

        # 路径搜索需要用到的信息
        self.invalidNodeList = []  # 记录所有invalid节点的offset
        self.invalidPaths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidPathId:Path对象
        self.invalidNode2PathIds = {}  # 记录每个invalid节点包含的路径，格式为：  invalidNodeOffset:[pathId1,pathId2]
        self.invalidNode2CallChain = {}  # 记录每个invalid节点包含的调用链，格式为： invalidNodeOffset:[[callchain1中的pathid],[callchain2中的pathid]]

        # 可达性分析需要用到的信息
        self.pathReachable = {}  # 某条路径是否可达
        self.invNodeReachable = None  # 某个Invalid节点是否可达，格式为： invNode:True/Flase
        self.redundantType = {}  # 每个invalid节点的冗余类型，类型包括fullyredundant和partiallyredundant，格式为： invNode: type
        self.fullyRedundantInvNodes = []  # 全部的完全冗余的invalid节点
        self.partiallyRedundantInvNodes = []  # 全部的部分冗余的invalid节点
        self.abandonedFullyRedundantInvNodes = []  # 放弃优化的完全冗余invalid节点
        self.abandonedPartiallyRedundantInvNodes = []  # 放弃优化的部分冗余invalid节点
        self.nonRedundantInvNodes = []  # 不冗余的invalid节点
        self.invNodeToRedundantCallChain = {}  # 每个invalid节点对应的，冗余的函数调用链，格式为： invNode:[[pid1,pid2],[pid3,pid4]]
        self.checkInvNode = {}  # 对某个invalid node，是否进行分析。因为在求解过程中，可能会出现超时，一旦出现超时，就把这个invNode的所有路径，都设置成不分析

        # 冗余assertion优化需要用到的信息
        self.domTree = {}  # 支配树。注意，为了方便从invalid节点往前做遍历，该支配树存储的是入边，格式为   to:from

        # 重定位需要用到的信息
        self.jumpEdgeInfo = []  # 跳转边信息，格式为:[[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选),新老函数体之间的offset(可选)]]
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

        self.constructorFuncBodyLength = 0
        self.funcBodyLength = 0
        self.constructorDataSegLength = 0
        self.dataSegLength = 0

        # copdcopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block，
        #                       codecopy所在的block]]
        self.codeCopyInfo = None
        # 构造函数重定位需要用到的信息
        self.runtimeDataSegOffset = 0  # 运行时的数据段的移动偏移量，即运行时的函数体总长度变化的偏移量

    def optimize(self):
        self.log.info("开始进行字节码分析")
        self.__etherSolve()
        if self.outputProcessInfo:
            self.log.processing("\n\n以下是原字节码文件的长度信息:")
            self.log.processing("构造函数的函数体长度为:{}".format(self.constructorFuncBodyLength))
            self.log.processing("构造函数的数据段长度为:{}".format(self.constructorDataSegLength))
            self.log.processing("运行时的函数体长度为:{}".format(self.funcBodyLength))
            self.log.processing("运行时的数据段长度为:{}\n".format(self.dataSegLength))

        # 简单检查是否有invalid，可以提高效率
        if not self.cfg.invalidExist:
            self.log.info("没有找到Assertion，优化结束")
            return

        # 首先识别出所有的函数体，将每个函数体内的强连通分量的所有点标记为loop-related
        self.__identifyAndCheckFunctions()
        self.log.info("函数体识别完毕，一共识别到:{}个函数体".format(self.funcCnt))

        # 然后找到所有invalid节点，找出他们到起始节点之间所有的路径
        self.log.info("开始进行路径搜索")
        self.__searchPaths()

        if self.invalidNodeList.__len__() == 0:
            self.log.info("没有找到可优化的Assertion，优化结束")
            return
        self.log.info(
            "路径搜索完毕，一共找到{}个Assertion:{},{}条路径".format(self.invalidNodeList.__len__(), self.invalidNodeList,
                                                      len(self.invalidPaths.keys())))

        # 求解各条路径是否可行
        self.log.info("正在分析路径可达性")
        self.__reachabilityAnalysis()
        self.log.info("可达性分析完毕")

        self.log.info(
            "分析结果：{}个完全冗余{}，{}个部分冗余{}，{}个不冗余{}".format(
                self.fullyRedundantInvNodes.__len__(),
                self.fullyRedundantInvNodes.__str__(),
                self.partiallyRedundantInvNodes.__len__(),
                self.partiallyRedundantInvNodes.__str__(),
                self.nonRedundantInvNodes.__len__(),
                self.nonRedundantInvNodes.__str__())
        )
        if self.fullyRedundantInvNodes.__len__() == 0 and self.partiallyRedundantInvNodes.__len__() == 0:
            self.log.info("不存在可优化的Assertion，优化结束")
            return

        # 这里需要注意，只有在部分冗余的处理函数里，才会将exit Block假装成数据段
        # 因此，如果只有完全冗余，没有部分冗余，这时候也要执行部分冗余的函数，此时部分冗余的函数只会做假装的工作

        # 生成cfg的支配树
        if self.outputProcessInfo:
            self.log.processing("正在生成支配树")
        self.__buildDominatorTree()

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
        self.__processCodecopyInConstructor()
        self.log.info("构造函数字节码序列生成完毕")

        if self.outputProcessInfo:
            self.log.processing("\n\n以下是新字节码文件的长度信息:")
            self.log.processing("构造函数的函数体长度为:{}".format(self.constructorOpcode.__len__()))
            self.log.processing("构造函数的数据段长度为:{}".format(self.constructorDataSegLength))
            self.log.processing("运行时的函数体长度为:{}".format(self.newFuncBodyOpcode.__len__()))
            self.log.processing("运行时的数据段长度为:{}".format(self.dataSegLength))

        # 将优化后的运行时字节码写入文件
        self.__outputFile()
        self.log.info("写入完毕")

    def __etherSolve(self):
        '''
        使用ethersolve对字节码进行分析
        :return:
        '''
        # 检查文件路径是否存在
        if not os.path.exists(self.inputFile):
            self.log.fail("输入文件:{} 不存在".format(self.inputFile))
        if not os.path.exists(self.outputPath):
            self.log.fail("输出路径:{} 不存在".format(self.outputPath))

        self.inputFile = self.inputFile.replace("\\", "/")
        self.inputFile = self.inputFile.replace("\\\\", "/")
        self.outputPath = self.outputPath.replace("\\", "/")
        self.outputPath = self.outputPath.replace("\\\\", "/")
        if self.outputPath[-1] != '/':
            self.outputPath += '/'

        # 使用ethersolve工具进行处理
        es = EtherSolver(self.inputFile, self.outputPath, outputHtml=self.outputHtml)
        es.execSolver()

        # 处理完成之后，对优化使用到的数据进行初始化
        self.constructorCfg = es.getConstructorCfg()
        self.cfg = es.getCfg()
        self.constructorDataSegStr = es.getConstructorDataSegStr()
        self.dataSegStr = es.getDataSeg()
        self.constructorFuncBodyLength = self.constructorCfg.bytecodeLength
        self.funcBodyLength = self.cfg.bytecodeLength
        self.constructorDataSegLength = self.constructorDataSegStr.__len__() // 2
        self.dataSegLength = self.dataSegStr.__len__() // 2
        self.blocks = self.cfg.blocks  # 存储基本块，格式为 起始offset:BasicBlock
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.edges = self.cfg.edges  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = self.cfg.inEdges  # 存储入边表，格式为 to:[from1,from2...]
        self.node2FuncId = dict(
            zip(self.nodes, [None for i in range(0, self.nodes.__len__())]))  # 记录节点属于哪个函数，格式为：  node：funcId
        self.isFuncBodyHeadNode = dict(
            zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 函数体头结点信息，用于后续做函数内环压缩时，判断某个函数是否存在递归的情况
        self.isLoopRelated = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 标记各个节点是否为loop-related

    def __identifyAndCheckFunctions(self):
        """
        识别所有的函数
        给出三个基本假设：
        1. 同一个函数内的指令的地址都是从小到大连续的
        2. 任何函数的调用节点，必然是现在本节点内push跳转地址再进行无条件跳转
        3. 任何函数在进行返回的时候，必然不会再本节点内push跳转地址，而是使用栈上的某个已有的地址，最后进行无条件跳转
        给出一个求解前提：
           我们不关心函数调用关系产生的“错误的环”，因为这种错误的环我们可以在搜索路径时，可以通过符号执行或者返回地址栈解决掉
        """

        # 第一步，检查是否除了0号offset节点之外，是否还有节点没有入边,若有，则可能存在错误，输出警告信息
        # 同时记录除起始节点以外没有入边的节点，这些节点用于后续的处理
        nodeWithoutInedge = set()
        for _to, _from in self.inEdges.items():
            if _to == self.cfg.initBlockId:
                continue
            if _from.__len__() == 0:
                self.log.warning("发现一个不是初始节点，但没有入边的Block: {}".format(_to))
                nodeWithoutInedge.add(_to)

        # 第二步，找出所有unconditional jump的边
        for n in self.cfg.blocks.values():
            if n.jumpType == "unconditional":
                _from = n.offset
                for _to in self.edges[_from]:  # 可能有几个出边
                    e = JumpEdge(n, self.cfg.blocks[_to])
                    self.uncondJumpEdge.append(e)

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

        # 第五步，从一个函数的funcbody的起始block开始dfs遍历，只走offset范围在 [第一条指令所在的block的offset,最后一条指令所在的block的offset]之间的节点，尝试寻找出所有的函数节点
        # 因为函数中可能包含没有入边的JUMPDEST，下面会先收集缺失的block，这些block只能是没有入边的JUMPDEST
        for rangeInfo in funcRange2Calls.keys():  # 找到一个函数
            offsetRange = json.loads(rangeInfo)  # 还原之前的list
            funcBody = []
            stack = Stack()
            visited = {}
            visited[offsetRange[0]] = True
            stack.push(offsetRange[0])  # 既是范围一端，也是起始节点的offset
            while not stack.empty():  # dfs找出所有节点
                top = stack.pop()
                funcBody.append(top)
                for out in self.edges[top]:
                    if out not in visited.keys() and out in range(offsetRange[0], offsetRange[1] + 1):
                        stack.push(out)
                        visited[out] = True
            missingBlocks = []  # 缺失的block
            funcBody.sort()
            isProcess = True
            for i in range(len(funcBody) - 1):
                length = self.blocks[funcBody[i]].length
                if funcBody[i] + length == funcBody[i + 1]:
                    continue
                elif funcBody[i] + length + 1 == funcBody[i + 1]:  # 刚好缺一个字节的长度
                    missingBlocks.append(funcBody[i] + length)
                else:  # 缺一个不是一个字节的block，放弃处理这个函数
                    isProcess = False
                    break
            if not isProcess:  # 放弃处理这个函数
                continue

            # 检查找到的所有缺失的block，是否都是只有一个JUMPDEST
            for missingBlockOffset in missingBlocks:
                if self.blocks[missingBlockOffset].length != 1:
                    isProcess = False
                    break
                if self.blocks[missingBlockOffset].bytecode[0] != 0x5b:
                    isProcess = False
                    break
                if missingBlockOffset not in nodeWithoutInedge:
                    isProcess = False
                    break
                if missingBlockOffset in self.cfg.pushedData:
                    # 这暂时是不被允许的，因为这里能修复的是，没有push过返回地址的jumpdest
                    # 具体如何触发见readme
                    self.log.fail("未能找全函数节点，放弃优化")
                    exit(0)
            if not isProcess:
                continue

            # 经过检查，可以通过加入没有入边的jumpdest来使函数保持完整.找全了函数节点，存储函数信息
            for missingBlockOffset in missingBlocks:
                funcBody.append(missingBlockOffset)
                nodeWithoutInedge.remove(missingBlockOffset)
            self.funcCnt += 1
            f = Function(self.funcCnt, offsetRange[0], offsetRange[1], funcBody, self.edges)
            self.funcDict[self.funcCnt] = f
            for node in funcBody:
                assert self.node2FuncId[node] is None  # 一个点只能被赋值一次
                self.node2FuncId[node] = self.funcCnt
            if len(missingBlocks) != 0:
                self.log.info("运行时函数中发现无入边JUMPDEST，无入边节点:{}修复成功".format(str(node)))

        # 此时不应该还有无入边的jumpdest块
        for offset in nodeWithoutInedge:
            if self.blocks[offset].length != 1:
                continue
            if self.blocks[offset].bytecode[0] == 0x5b:
                self.log.fail("未能找全函数节点，放弃优化")
                exit(0)

        # 第六步，尝试处理没有返回边selfdestruct、revert函数
        # 注意，有些selfdestruct函数是有返回边的，我们处理的是没有返回边的情况
        self.nodes.sort()
        removedNode = []
        for node in nodeWithoutInedge:
            # 找出这个可疑节点的上一个节点，它有可能是调用节点
            callBlock = None
            for b in self.blocks.values():
                if b.offset + b.length == node:
                    callBlock = b
                    break
            # 检查这个节点是否为为可能的调用者节点
            if not callBlock.couldBeCaller:
                continue
            # 之前的假设是，在调用者节点里会压入一个返回地址。对于遇到的大多数情况确实成立
            # 现在观察到合约0xE0339e6EBd1CCC09232d1E979d50257268B977Ef在调用包含revert函数的时候，调用者节点中并没有push返回地址，而是在之前的几个节点中进行了push
            # 于是这里取消这个限制，只检查无入边节点的前一个节点是否为可能的调用者节点
            # hasReturnAddr = False
            # for addr in callBlock.instrAddrs:
            #     i = addr - callBlock.offset
            #     if callBlock.bytecode[i] in range(0x60, 0x80):  # push指令
            #         pushData = int(callBlock.instrs[i].split(" ")[2], 16)
            #         if pushData == node:  # push的内容与返回地址一致
            #             hasReturnAddr = True
            #             break
            #     if hasReturnAddr:
            #         break
            # if not hasReturnAddr:
            #     continue
            # 从起始节点开始做dfs，看是否能够走完这个函数
            assert len(self.edges[callBlock.offset]) == 1  # 假设是"push addr;jump"因此只有一条出边
            funcBegin = self.edges[callBlock.offset][0]
            if self.node2FuncId[funcBegin] is not None:
                continue  # 函数起始节点已经被标记为某个函数？真的有这个情况吗？不确定，但是不影响结果
            funcEnd = None  # 先找出这个函数的可能范围，即从funcBegin开始的，没有被标记为任何函数节点的一个连续序列(不包含exit block)
            for n in self.nodes:  # 已排序
                if n <= funcBegin:
                    continue
                elif self.node2FuncId[n] is None and n != self.cfg.exitBlockId:
                    continue
                else:  # 要么到了Exit，要么到了一个被标记为函数的节点
                    funcEnd = n
            assert funcEnd is not None
            funcRange = range(funcBegin, funcEnd)
            funcBody = []
            stack = Stack()
            visited = {}
            visited[funcBegin] = True
            stack.push(funcBegin)  # 既是范围一端，也是起始节点的offset
            while not stack.empty():  # dfs找出所有节点
                top = stack.pop()
                funcBody.append(top)
                for out in self.edges[top]:
                    if out not in visited.keys() and out in funcRange and self.node2FuncId[out] is None:  # 不能是已经标记过的函数
                        stack.push(out)
                        visited[out] = True
            # 检查找出的是否为一个连续的字节码序列
            funcBody.sort()
            findAll = True
            for i in range(len(funcBody) - 1):
                curBlock, nextBlock = self.blocks[funcBody[i]], self.blocks[funcBody[i + 1]]
                if curBlock.offset + curBlock.length != nextBlock.offset:
                    findAll = False
                    break
            if not findAll:
                # 这不仅代表着，寻找函数节点的失败，也是合约优化的失败
                self.log.fail("未能找全函数节点，放弃优化")
                exit(0)

            # 找全了函数节点，将其标出
            self.funcCnt += 1
            f = Function(self.funcCnt, funcBody[0], funcBody[-1], funcBody, self.edges)
            self.funcDict[self.funcCnt] = f
            for n in funcBody:
                assert self.node2FuncId[n] is None  # 一个点只能被赋值一次
                self.node2FuncId[n] = self.funcCnt
            self.log.info("运行时函数中发现无返回边函数，无入边节点:{}修复成功".format(str(node)))
            removedNode.append(node)
        for node in removedNode:
            nodeWithoutInedge.remove(node)

        # 最后还要做一个检查，检查是否所有的common节点都被标记为了函数，以及没有入边的节点是否已经被处理干净
        # 检查通过才能进行优化，否则拒绝优化合约
        for offset, b in self.blocks.items():
            if b.blockType == "common" and self.node2FuncId[offset] is None:
                self.log.fail("未能找全函数节点，放弃优化")
                exit(0)
        if len(nodeWithoutInedge) != 0:
            self.log.fail("未能找全函数节点，放弃优化")
            exit(0)

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
                            exit(0)

        # 第八步，因为dispatcher中也有可能存在scc，因此需要将它们也标记出来
        # 4.21新问题：dispatcher也可能被识别为函数体，如在KOLUSDTFund.bin的构造函数中，某些函数体就是由dispatcher节点构成的
        # 因此，讨论dispatcher中scc的问题时，应当考虑的是，非函数的非common节点
        # 最新：不再对构造函数进行这样的处理，不必要对他们进行关系，这一步可以完全删除

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
                        exit(0)

        # 第九步，处理可能出现的“自环”，见test12
        for node in self.nodes:
            if node in self.edges[node]:  # 出边指向自己
                self.isLoopRelated[node] = True

        # 第十步，去除之前添加的边，因为下面要做路径搜索，新加入的边并不是原来cfg中应该出现的边
        for pairs in funcRange2Calls.values():
            for pair in pairs:
                self.edges[pair[0]].remove(pair[1])
                self.inEdges[pair[1]].remove(pair[0])

        # # 生成颜色图
        # group = {}
        # for node,id in self.node2FuncId.items():
        #     if id is not None:
        #         group[node] = id + 1
        #     else:
        #         group[node] = 0
        # length = {}
        # for offset,b in self.blocks.items():
        #     length[offset] = b.length
        # dg = DotGraphGenerator(self.nodes,self.edges,group,length)
        # dg.genDotGraph(sys.argv[0],"temp")

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
                self.checkInvNode[node.offset] = True  # 默认对所有的invalid都做可达性分析

        # 第二步，从起点开始做dfs遍历，完成提到的三个任务
        generator = PathGenerator(self.cfg, self.uncondJumpEdge, self.isLoopRelated,
                                  self.node2FuncId, self.funcDict)
        generator.genPath()
        paths = generator.getPath()
        self.jumpEdgeInfo = generator.getJumpEdgeInfo()
        self.codeCopyInfo = generator.getCodecopyInfo()

        # 第三步，做一个检查信息，看codecopy指令是否只是用于复制运行时的代码，或者是用于访问数据段的信息
        # codecopy信息，格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #                       size push的值，size push的字节数，size push指令的地址， size push指令所在的block]]
        # 对于运行时的codecopy，假设其用于访问数据段，因此size是不做任何处理的，只关心offset的情况。
        #   如果offset是一个可以获得的数，则保留该codecopy；如果offset是untag，且被push的位置为codesize，则直接删除
        # 对于构造函数的codecopy，假设其用于访问数据段以及copy runtime，它的offset和size必须是untag的
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
                    exit(0)
            elif offset in range(self.funcBodyLength,
                                 self.funcBodyLength + self.dataSegLength):  # 不是None，则offset只能在数据段，不能为代码段
                # 以数据段的偏移量为开头，且长度不能超出数据段
                continue
            else:
                self.log.fail("函数体的codecopy无法进行分析: offset不在数据段内")
                exit(0)
        for info in removeList:
            self.codeCopyInfo.remove(info)

        # 第四步，将这些路径根据invalid节点进行归类
        for invNode in self.invalidNodeList:
            self.invalidNode2PathIds[invNode] = []
        for path in paths:
            pathId = path.getId()
            self.invalidPaths[pathId] = path
            invNode = path.getLastNode()
            self.invalidNode2PathIds[invNode].append(pathId)
            self.invalidPaths[pathId].setInvNode(invNode)

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
        if len(removedInvNodes) > 0:
            self.log.info("放弃优化路径中包含SCC节点的Assertion:{}".format(removedInvNodes))

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

    def __reachabilityAnalysis(self):
        """
        多线程可达性分析：对于一个invalid节点，检查它的所有路径是否可达，并根据这些可达性信息判断冗余类型
        :return:None
        """

        # 第一步，使用多线程对路径进行可达性分析
        self.invNodeReachable = dict(zip(self.invalidNodeList, [False for i in range(self.invalidNodeList.__len__())]))
        multiprocessing.set_start_method('spawn')  # win和linux下创建子进程的默认方式不一致，这里强制其为win下的创建方式
        manager = multiprocessing.Manager()
        pool = Pool()
        pathLock, resLock = manager.Lock(), manager.Lock()
        pathQueue, resQueue = manager.Queue(), manager.Queue()
        subProcessNum = multiprocessing.cpu_count() - 2  # 创建cpu数量-2的子进程
        self.log.info("启动{}个子进程进行约束求解".format(subProcessNum))

        for i in range(subProcessNum):
            pool.apply_async(strainWorker,
                             args=(self.cfg, pathQueue, pathLock, resQueue, resLock))

        # 创建一个线程用来获取数据
        collector = threading.Thread(target=self.__resCollector, args=(resQueue,))
        collector.start()

        # 使用多线程进行约束求解
        for pathId, path in self.invalidPaths.items():  # 取出一条路径
            # 对于路径超时了的invalid，照样将路径放入队列，这些路径已经被设置为了不分析状态，求解进程会直接返回一个timeout = True
            while True:  # 往队列中放入所有的路径
                pathLock.acquire()
                if pathQueue.full():
                    pathLock.release()
                    time.sleep(1)
                else:
                    pathQueue.put(path)
                    pathLock.release()
                    break

        # 等待结果，结果收集完毕之后，发送特殊的路径信息，用以结束子进程
        collector.join()
        tempPath = Path(-1, [None])
        putNum = 0
        while putNum < subProcessNum:
            pathLock.acquire()
            if pathQueue.full():
                pathLock.release()
                time.sleep(1)
            else:
                pathQueue.put(tempPath)
                putNum += 1
                pathLock.release()
        pool.close()
        pool.join()
        self.log.info("所有约束求解子进程已关闭")

        # 第二步，根据各个函数调用链的可达性，判断每个invalid节点的冗余类型
        # 对于超时的invalid，它的所有路径被设置为可达的，不会被判断为冗余。详见求解结果收集函数
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

    def __buildDominatorTree(self):
        # 因为支配树算法中，节点是按1~N进行标号的，因此需要先做一个标号映射，并处理映射后的边，才能进行支配树的生成
        # 4.27新问题：如果有多个没有入边的节点，会导致算法不收敛
        # 最简单的触发办法：domTree.initGraph(3, [[1, 3], [2, 3], [1, 2]])
        # 下面改变原来策略，如果是没有入边的节点，而且不是init block，都会在计算支配树时被移除，而且对应的边也移除
        # 因为已经经过了函数检查，此时没有入边，而且没有不是Init的block都是被修复过的，要么是返回节点
        # 要么是没有入边的JUMPDEST，不影响程序的正确性
        newNode = list(self.nodes)
        tmpEdge = {}
        for k, v in self.edges.items():
            tmpEdge[k] = list(v)
        for _to, _froms in self.inEdges.items():
            if _to != 0 and len(_froms) == 0:  # 找到一个没有入边的，非init节点
                newNode.remove(_to)
                tmpEdge.pop(_to)

        # mapper = GraphMapper(self.nodes, self.edges)
        mapper = GraphMapper(newNode, tmpEdge)
        newEdges = mapper.getNewEdges()
        domTreeEdges = []
        for _from in newEdges.keys():
            for _to in newEdges[_from]:
                domTreeEdges.append([_from, _to])
        domTree = DominatorTreeBuilder()
        # domTree.initGraph(self.nodes.__len__(), domTreeEdges)
        domTree.initGraph(newNode.__len__(), domTreeEdges)
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
            # 这是个很无语的问题，如果要严格优化，那么包含了sha3指令路径的invalid就应该放弃优化
            # 但是实际上，很多路径都会包含sha3指令，也就是说，如果放弃的话，优化率会很难看
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
                addrs = self.blocks[node].instrAddrs
                for addr in reversed(addrs):  # 从后往前遍历
                    if stateMap[addr] == targetState:  # 找到一个状态相同的点
                        targetAddr = addr
                        targetNode = node
                        break
                if targetAddr is not None:
                    break
                node = self.domTree[node]

            # 新坑：assert里面调函数，并不是无副作用的，这时候会找不到程序状态相同的节点
            # assert targetAddr and targetNode, pathNodes  # 不能为none
            if targetAddr is None:
                self.abandonedFullyRedundantInvNodes.append(invNode)
                continue  # 放弃当前Assertion的优化
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("找到和节点{}程序状态相同的地址:{}，对应的节点为:{}".format(invNode, targetAddr, targetNode))

            # 第三步，将这一段序列置为空指令，并且记录删除序列信息
            for node in self.nodes:
                if targetNode <= node <= invNode:  # invNode后的block暂时不处理
                    beginAddr = max(targetAddr, node)
                    endAddr = node + self.blocks[node].length
                    for i in range(beginAddr - node, endAddr - node):
                        self.blocks[node].bytecode[i] = 0x1f  # 置为空指令
                        self.blocks[node].removedByte[i] = True  # 将字节标记为待删除
            if self.inEdges[invNode + 1].__len__() == 1:
                # invalid的下一个block，只有一条入边，说明这个jumpdest也可以删除
                self.blocks[invNode + 1].bytecode[0] = 0x1f
                self.blocks[invNode + 1].removedByte[0] = True

        if self.abandonedFullyRedundantInvNodes.__len__() != 0:  # 有移除的invalid
            self.log.info(
                "放弃优化有副作用的Assertion:{}".format(",".join([str(n) for n in self.abandonedFullyRedundantInvNodes])))

    def __optimizePartiallyRedundantAssertion(self):
        """
        对字节码中部分冗余的assertion进行优化
        :return:
        """
        # 第一步，直接删除原来的exitblock，新构建的函数体从exitblock的位置开始放置
        self.nodes.remove(self.cfg.exitBlockId)
        tempExitBlock = self.blocks[self.cfg.exitBlockId]  # 暂时存下来，后面优化结束之后再放回去
        self.blocks.pop(self.cfg.exitBlockId)
        curLastNode = max(self.nodes)

        # 第二步，使用符号执行，找到程序状态与Invalid执行完之后相同的targetNode和targetAddr
        executor = SymbolicExecutor(self.cfg)
        for invNode in self.partiallyRedundantInvNodes:
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
                        break
                if targetAddr is not None:
                    break
                node = self.domTree[node]

            if targetAddr is None:  # 没有找到程序状态相同的节点，放弃优化
                self.abandonedPartiallyRedundantInvNodes.append(invNode)
                continue

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

        if self.abandonedPartiallyRedundantInvNodes.__len__() != 0:  # 有移除的invalid
            self.log.info(
                "放弃优化有副作用的Assertion:{}".format(",".join([str(n) for n in self.abandonedPartiallyRedundantInvNodes])))

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
                newBlock.removedByte = dict(originalBlock.removedByte)  # 将原函数体中已经存在的完全冗余删除序列信息，添加到新函数体中
                self.nodes.append(beginOffset)
                self.blocks[beginOffset] = newBlock
                self.runtimeDataSegOffset += originalBlock.length  # 数据段后移
                curLastNode = beginOffset

            # 添加部分冗余删除序列信息
            for invNode in invNodes:
                info = func.getRemovedRangeInfo(invNode)
                for node in funcBodyNodes:
                    if info[1] <= node < info[2]:  # 节点中存在要删除的序列
                        beginIndex = max(node, info[0]) - node
                        endIndex = min(node + self.blocks[node].length, info[2]) - node
                        for i in range(beginIndex, endIndex):
                            self.blocks[node + offset].removedByte[i] = True

            # 找出各个冗余函数调用链的，新函数体的调用节点
            callerNodes = []
            for invNode in invNodes:  # 取出一个Invalid
                for callChain in self.invNodeToRedundantCallChain[invNode]:  # 取出相关的调用链路径
                    pathId = callChain[0]  # 在调用链上随意取出一条路径
                    pathNodes = self.invalidPaths[pathId].pathNodes
                    for node in reversed(pathNodes):
                        curNodeFuncId = self.node2FuncId[node]
                        if curNodeFuncId != funcId:  # 出了invalid所在的函数
                            callerNodes.append(node)
                            break
            returnedNodes = [node + self.blocks[node].length for node in callerNodes]  # 应当返回的节点

            # 添加跳转边信息，注意，这些边中与冗余序列相关的边，先不删除，后面在重新生成字节码的时候，会对这些边进行删除
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
            removedEdgeInfo = []  # 需要删除的跳转边信息，即原来调用包含了冗余assertion函数体的调用边信息
            originalFuncRange = range(funcBodyNodes[0],
                                      funcBodyNodes[-1] + self.blocks[funcBodyNodes[-1]].length)  # 原函数体的地址范围
            for info in self.jumpEdgeInfo:
                newInfo = list(info)
                checker = 0  # 将三个信息映射到一个数字
                if info[3] in originalFuncRange:  # push在原函数体的地址范围
                    checker |= 4
                if info[4] in originalFuncRange:  # jump在原函数体的地址范围
                    checker |= 2
                if info[0] in originalFuncRange:  # push的值在原函数体的地址范围
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
                        if info[4] in callerNodes:  # 是部分冗余assertion函数体的调用边
                            removedEdgeInfo.append(info)  # 需要删除旧的调用边
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
            for info in removedEdgeInfo:
                self.jumpEdgeInfo.remove(info)

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
            tempExitBlock.removedByte[i] = False
        tempExitBlock.bytecode = tempBytecode
        self.cfg.exitBlockId = newBlockOffset
        self.blocks[newBlockOffset] = tempExitBlock  # 复用之前的exit block

    def __regenerateRuntimeBytecode(self):
        """
        重新生成运行时的字节码，同时完成重定位
        :return:None
        """

        # 第一步，将codecopy信息转换成jump的信息，方便统一处理
        # 格式: [[offset push的值，offset push的字节数，offset push指令的地址， offset push指令所在的block,
        #          size push的值，size push的字节数，size push指令的地址， size push指令所在的block，codecopy所在的block]]
        # 如果处理的是运行时代码的信息，则转换的方式为：将前四个信息变成jump信息中的前四个，最后将codecopy指令的地址变成jump信息的第五个（即jump所在的block）
        # 如果处理的是构造函数中信息，因为可能涉及到函数体后数据段的访问、运行时代码的复制，此时size会发生剧烈的变化
        # 因此，添加一个长度为7的跳转信息，专门用来处理这种情况：
        # 类型5：该信息是由codecopy中的offset信息修改而来的，在该情况下，push的addr需要加上offset，在第一次处理到这条信息时，会做试填入
        #       填入完成之后，变回成长度为5的普通信息
        # [[push的值，push的字节数，push指令的地址，push指令所在的block，jump所在的block，跳转的type(可选), 新老函数体之间的offset(可选)]]
        for info in self.codeCopyInfo:
            newInfo = list(info[:4])
            newInfo.append(info[8])
            newInfo.append(5)
            newInfo.append(self.runtimeDataSegOffset)
            self.jumpEdgeInfo.append(newInfo)

        # 第二步，对跳转信息去重
        # 在路径搜索器当中，已经对跳转信息进行过去重了
        # 但是因为添加了从codecopy转换而来的跳转信息，而这些新添加的信息
        # 有可能是重复的，因此需要再对跳转信息做一次去重
        # 注意，对后者的去重只能现在做，因为信息中可能包含None，会触发json.loads错误
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
        #   类型5
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
                    case 5:
                        continue
            jumpAddr = jumpBlock + self.blocks[jumpBlock].length - 1
            delPush = self.blocks[pushBlock].removedByte[pushAddr - pushBlock]
            delJump = self.blocks[jumpBlock].removedByte[jumpAddr - jumpBlock]
            assert delPush == delJump  # 如果要删除push，则jump必须也要被删除
            if delPush:  # 确定要删除
                removedInfo.append(info)

        for info in removedInfo:
            self.jumpEdgeInfo.remove(info)  # 删除对应的信息

        # 第四步，对每一个block，删除空指令，同时还要记录旧地址到新地址的映射
        self.nodes.sort()  # 确保是从小到大排序的
        mappedAddr = 0  # 映射后的新地址
        for node in self.nodes:
            blockLen = self.blocks[node].length
            newBlockLen = blockLen  # block的新长度
            isDelete = self.blocks[node].removedByte
            # 重新生成字节码，并计算地址映射
            bytecode = self.blocks[node].bytecode
            newBytecode = bytearray()
            for i in range(blockLen):
                self.originalToNewAddr[i + node] = mappedAddr
                if isDelete[i]:  # 这一个字节是需要被删除的
                    newBlockLen -= 1
                    continue
                newBytecode.append(bytecode[i])
                mappedAddr += 1

            self.blocks[node].length = newBlockLen  # 设置新的block长度
            self.blocks[node].bytecode = newBytecode  # 设置新的block字节码

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
                    assert 0x60 <= newOpcode <= 0x7f
                    self.blocks[pushBlock].bytecode[pushAddr - pushBlockOffset] = newOpcode

                    # 插入足够的位置，但是不填入地址，因为在下一轮试填入一定会填进新的地址
                    for i in range(offset):
                        self.blocks[pushBlock].bytecode.insert(pushAddr - pushBlockOffset + 1, 0x00)

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
        self.blocks[self.cfg.exitBlockId].length = 0  # 此时exitblock不再代表数据段
        self.blocks[self.cfg.exitBlockId].bytecode = bytearray()
        self.newFuncBodyOpcode = deque()  # 效率更高
        for node in self.nodes:  # 有序的
            for bc in self.blocks[node].bytecode:
                self.newFuncBodyOpcode.append(bc)
            tempFuncBodyLen += self.blocks[node].length
        self.runtimeDataSegOffset = tempFuncBodyLen - self.funcBodyLength  # 同时记录数据段的偏移量，用于构造函数中对数据段访问的重定位

    def __processCodecopyInConstructor(self):
        """
        4.24新思路：
        因为实际上，在构造函数里面，只需要处理codecopy即可，不需要过多处理重定位信息
        只在一种情况下，需要对重定位信息进行考虑：新的codecopy的size/offset无法填入原来的位置
        考虑到出现这种情况的概率非常小，同时，构造函数在做完ethersolve分析之后，出现没有入边的情况非常多
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
        # 4.24新发现：和运行时函数一样，如果offset是Untag，且offset为codesize的结果，那么就不需要对其进行处理，相应的删除这一条信息
        # 合约为：0x97492124f65B499b3328A9BC87FEf164D309c9b7
        removeList = []
        for info in self.codeCopyInfo:
            offset, _size = info[0], info[4]
            if offset is None:
                # 检查是否是由codecopy 获取的offset
                index = info[2] - info[3]
                if self.blocks[info[3]].bytecode[index] == 0x38:  # codesize
                    removeList.append(info)
                    continue
                else:
                    self.log.fail("构造函数的codecopy无法进行分析: offset为{}，size为{}".format(info[0], info[4]))
                    exit(0)
            elif offset in range(self.constructorFuncBodyLength,
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
                exit(0)
        for info in removeList:
            self.codeCopyInfo.remove(info)

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
                    exit(0)
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
                    exit(0)
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
        self.log.info("正在将优化后的字节码写入到文件: {}".format(self.outputPath + self.outputName))
        with open(self.outputPath + self.outputName, "w+") as f:
            f.write(
                constructorStr + self.constructorDataSegStr + newFuncBodyStr + self.dataSegStr)

    def __resCollector(self, resQueue):
        '''
        多线程收集求解结果
        :param resQueue: 结果队列，用来接收子进程的求解结果
        :return:
        '''
        self.log.info("约束收集线程已启动")
        resNum = 0  # 获取到的结果数量
        totalNum = len(self.invalidPaths)
        while resNum < totalNum:
            pathId, reachable, isTimeout = resQueue.get()  # 直接用阻塞的方法去获取

            if isTimeout:
                # 出现了超时，该invalid会被置为不分析状态，它的所有路径都会被置为可达，因此不会被当做冗余
                invNode = self.invalidPaths[pathId].getInvNode()
                if self.checkInvNode[invNode]:  # 还没有设置为不分析
                    self.checkInvNode[invNode] = False
                    for pathId in self.invalidNode2PathIds[invNode]:
                        self.pathReachable[pathId] = True
                        self.invalidPaths[pathId].setUndo()
            else:
                self.pathReachable[pathId] = reachable
            resNum += 1
            if self.outputProcessInfo:  # 需要输出处理信息
                self.log.processing("收集到求解结果:{}/{}".format(resNum, totalNum))

        self.log.info("约束收集线程已关闭")


def strainWorker(cfg: Cfg, pathQueue, pathLock, resQueue, resLock):
    '''

    :param cfg: 控制流程图
    :param pathQueue: 路径队列，传递约束路径
    :param pathLock: 路径队列锁，一次只能有一个子进程对队列进行访问
    :param resQueue: 结果队列，返回结果
    :param resLock: 结果队列锁，一次只能有一个结果子进程传递返回结果
    :return:
    '''
    executor = SymbolicExecutor(cfg)
    reachable = False  # 路径是否可达
    isTimeout = False
    timeoutLimit = 10000  # 10s

    while True:
        # 获取路径
        pathLock.acquire()
        if pathQueue.empty():
            pathLock.release()
            time.sleep(1)
            continue
        path = pathQueue.get()
        pathLock.release()

        # 获取路径信息
        nodeList = path.getPathNodes()
        pathId = path.getId()
        if pathId == -1:  # 所有路径约束已经求解完毕，可以结束子进程
            break
        if not path.doCheck():  # 这个路径已经被设置为了不分析，直接返回一个timeout的结果给收集器
            resLock.acquire()
            resQueue.put([pathId, True, True])
            resLock.release()
            continue

        # 使用符号执行和求解器进行求解
        executor.clearExecutor()
        isSolve = True  # 默认是做约束求解的。如果发现路径走到了一个不应该到达的节点，则不做check，相当于是优化了过程
        constrains = []  # 路径上的约束
        for nodeIndex in range(0, len(nodeList) - 1):  # invalid节点不计入计算
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
                    expectedTarget = cfg.blocks[curNode].jumpiDest[jumpCond]
                    if nextNode != expectedTarget:  # 不匹配，直接置为不可达，后续不做check
                        reachable = False
                        isSolve = False  # 不对这一条路径使用约束求解了
                        break
                else:  # 不是确定的跳转地址
                    if nextNode == cfg.blocks[curNode].jumpiDest[True]:
                        constrains.append(executor.getJumpCond(True))
                    elif nextNode == cfg.blocks[curNode].jumpiDest[False]:
                        constrains.append(executor.getJumpCond(False))
                    else:
                        assert 0
        if isSolve:
            s = Solver()
            s.set("timeout", timeoutLimit)
            res = s.check(constrains)
            if res == sat:  # 约束可满足
                reachable = True
                isTimeout = False
            elif res == unknown:  # 约束求解超时
                reachable = True
                isTimeout = True
            else:  # 约束不可满足
                reachable = False
                isTimeout = False

        # 返回可达性信息
        # 格式为：[pathId,是否可达,是否超时]
        resLock.acquire()
        resQueue.put([pathId, reachable, isTimeout])
        resLock.release()
