import sys

from AssertionOptimizer.Function import Function
from Cfg.Cfg import Cfg
from Cfg.BasicBlock import BasicBlock
from AssertionOptimizer.JumpEdge import JumpEdge
from GraphTools.TarjanAlgorithm import TarjanAlgorithm
from GraphTools.PathGenerator import PathGenerator
from GraphTools.SccCompressor import SccCompressor
from Utils import DotGraphGenerator, Stack
import json


class AssertionOptimizer:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        # 函数识别、处理时需要用到的信息
        self.uncondJumpEdge = []  # 存储所有的unconditional jump的边，类型为JumpEdge
        self.nodes = list(self.cfg.blocks.keys())  # 存储点，格式为 [n1,n2,n3...]
        self.edges = dict(self.cfg.edges)  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = dict(self.cfg.inEdges)  # 存储入边表，格式为 to:[from1,from2...]
        self.funcCnt = 0  # 函数计数
        self.funcBodyDict = {}  # 记录找到的所有函数，格式为：  funcId:function
        self.isLoopRelated = dict(zip(self.nodes, [False for i in range(0, len(self.nodes))]))  # 标记各个节点是否为loop-related
        self.newNodeId = max(self.nodes) + 1  # 找到函数内的环之后，需要添加的新节点的id(一个不存在的offset)
        # self.invalidCnt = 0  # 用于标记不同invalid对应的路径集合
        # self.paths = {}  # 用于记录不同invalid对应的路径集合，格式为：  invalidid:[[路径1中的点],[路径2中的点]]

    def optimize(self):
        # 首先识别出所有的函数体，将每个函数体内的强连通分量的所有点压缩为一个点，同时标记为loop-related
        self.__identifyFunctions()

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
        # 一个函数的区间(一个字符串，内容为"[第一条指令所在的block的offset,最后一条指令所在的block的offset]"):[(funcbody调用者的起始node,funcbody返回边的目的node)]
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
                    for node in scc:
                        self.isLoopRelated[node] = True
                    # 压缩为一个点，这个点也需要标记为loop-related
                    self.isLoopRelated[self.newNodeId] = True
                    compressor.setInfo(self.nodes, scc, self.edges, self.inEdges, self.newNodeId)
                    compressor.compress()
                    self.nodes, self.edges, self.inEdges = compressor.getNodes(), compressor.getEdges(), compressor.getInEdges()
                    self.newNodeId += 1
        # g = DotGraphGenerator(self.edges, self.nodes)
        # g.genDotGraph(sys.argv[0], "_removed_scc")

    def __searchPaths(self):
        pass
