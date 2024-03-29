from AssertionOptimizer.TagStacks.SimplifiedExecutor import SimplifiedExecutor
from AssertionOptimizer.SymbolicExecutor import SymbolicExecutor
from Cfg.Cfg import Cfg
from Utils.Logger import Logger


class CfgRepairKit:
    def __init__(self, cfg: Cfg):
        """
        :param cfg:
        """
        self.cfg = cfg
        self.inEdge = cfg.inEdges
        self.edges = cfg.edges
        self.nodes = list(cfg.blocks.keys())
        self.blocks = cfg.blocks
        self.todoNodes = set()  # 没有入边的节点
        self.fixNeeded = False  # 是否需要修复
        self.visiting = dict(zip(self.nodes, [False for i in self.nodes]))
        self.log = Logger()

    def fix(self):
        """
        开始修复工作
        :return:
        """
        # print(self.edges)
        # 首先检查是否需要做修复
        self.__check()
        if not self.fixNeeded:
            return

        # 从起始节点开始，使用tagStack，进行简单的dfs遍历，尝试进行修复

        # self.__dfs(0, SimplifiedExecutor(self.cfg))
        self.__dfs(0, SimplifiedExecutor(self.cfg))

    def __check(self):
        """
        检查是否存在没有入边的非起始节点，若是则需要进行修复
        :return:
        """
        for node, _froms in self.inEdge.items():
            if node != 0 and _froms.__len__() == 0:  # 没有入边的非起始节点
                self.todoNodes.add(node)
        if self.todoNodes.__len__() != 0:
            self.fixNeeded = True

    def isFixed(self):
        """
        是否修复成功
        :return:
        """
        isFixed = True
        for node, _froms in self.inEdge.items():
            if node != 0 and _froms.__len__() == 0:  # 没有入边的非起始节点
                isFixed = False
        return isFixed

    def getRepairedEdges(self):
        """
        获取修复后的cfg
        :return: fixed cfg
        """
        return self.edges, self.inEdge

    def __dfs(self, curNode: int, parentExecutor: SimplifiedExecutor):
        """
        进行dfs，使用原有的边，尝试进行修复
        该dfs不会走回头路，不会走已经走过的路
        :param curNode:
        :return:
        """
        if self.visiting[curNode] or curNode == self.cfg.exitBlockId or self.blocks[curNode].jumpType == "terminal":
            return
        self.visiting[curNode] = True

        # 第一步，进行tagstack执行，这一步需要复制父节点的符号执行信息
        curExecutor = SimplifiedExecutor(self.cfg)
        curExecutor.setExecutorState(parentExecutor.getExecutorState())
        curExecutor.setBeginBlock(curNode)
        jumpInfo = None
        while not curExecutor.allInstrsExecuted():
            if curExecutor.isLastInstr():
                jumpInfo = curExecutor.getTagStackTop()
            curExecutor.execNextOpCode()

        # 第二步，查看是否跳到一个没有入边的节点，是则:
        # 若原来只是跳到exit block，则删除这条边
        # 添加新跳转边
        jumpInfoDigit = None
        jumpInfoStr = jumpInfo.__str__()
        if jumpInfoStr.isdigit():  # 是一个数字，检查是否跳到了没有入边的点
            jumpInfoDigit = int(jumpInfoStr)

        if self.blocks[curNode].jumpType == "unconditional":
            if jumpInfo is None:  # underflow会导致None
                self.visiting[curNode] = False
                return
            if jumpInfoDigit is not None:  # 是一个数字，检查是否跳到了没有入边的点
                if jumpInfoDigit in self.todoNodes and jumpInfoDigit not in self.edges[curNode]:
                    if len(self.edges[curNode]) == 1 and self.edges[curNode][0] == self.cfg.exitBlockId:  # 原来只是跳到Exit
                        self.edges[curNode] = []
                        self.inEdge[self.cfg.exitBlockId].remove(curNode)
                    self.log.info("修复缺失的入边：{}->{}".format(curNode, jumpInfoDigit))
                    self.edges[curNode].append(jumpInfoDigit)
                    self.inEdge[jumpInfoDigit].append(curNode)

        # 不顾原来的边关系，直接做dfs
        if jumpInfoDigit is None:  # 从栈中无法找到地址
            assert self.blocks[curNode].jumpType not in ["conditional", "unconditional"]
            if self.blocks[curNode].jumpType == "fall":
                self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
        else:
            if self.blocks[curNode].jumpType == "conditional":  # fall 边
                self.__dfs(jumpInfoDigit, curExecutor)
                self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
            elif self.blocks[curNode].jumpType == "unconditional":
                self.__dfs(jumpInfoDigit, curExecutor)
            elif self.blocks[curNode].jumpType == "fall":
                self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
            else:  # terminal only
                assert 0  # 返回

        self.visiting[curNode] = False


    # def __dfs(self, curNode: int, parentTagStack: SimplifiedExecutor):
    #     """
    #     进行dfs，使用原有的边，尝试进行修复
    #     该dfs不会走回头路，不会走已经走过的路
    #     :param curNode:
    #     :return:
    #     """
    #     if self.visiting[curNode] or curNode == self.cfg.exitBlockId or self.blocks[curNode].jumpType == "terminal":
    #         return
    #     # print(curNode)
    #     self.visiting[curNode] = True
    #
    #     # 第一步，进行tagstack执行，这一步需要复制父节点的符号执行信息
    #     curExecutor = SimplifiedExecutor(self.cfg)
    #     curExecutor.setExector(parentTagStack.getExecutor())
    #     curExecutor.setBeginBlock(curNode)
    #     jumpInfo = None
    #     while not curExecutor.allInstrsExecuted():
    #         if curExecutor.isLastInstr():
    #             jumpInfo = curExecutor.getTagStackTop()
    #         curExecutor.execNextOpCode()
    #         # curTagStack.printState(False)
    #         # print(jumpInfo)
    #
    #     # 第二步，查看是否跳到一个没有入边的节点，是则:
    #     # 若原来只是跳到exit block，则删除这条边
    #     # 添加新跳转边
    #     jumpInfoDigit = None
    #     jumpInfoStr = jumpInfo.__str__()
    #     if jumpInfoStr.isdigit():  # 是一个数字，检查是否跳到了没有入边的点
    #         jumpInfoDigit = int(jumpInfoStr)
    #
    #     if self.blocks[curNode].jumpType == "unconditional":
    #         if jumpInfo is None:  # underflow会导致None
    #             self.visiting[curNode] = False
    #             return
    #         if jumpInfoDigit is not None:  # 是一个数字，检查是否跳到了没有入边的点
    #             if jumpInfoDigit in self.todoNodes and jumpInfoDigit not in self.edges[curNode]:
    #                 if len(self.edges[curNode]) == 1 and self.edges[curNode][0] == self.cfg.exitBlockId:  # 原来只是跳到Exit
    #                     self.edges[curNode] = []
    #                     self.inEdge[self.cfg.exitBlockId].remove(curNode)
    #                 self.log.info("修复缺失的入边：{}->{}".format(curNode, jumpInfoDigit))
    #                 self.edges[curNode].append(jumpInfoDigit)
    #                 self.inEdge[jumpInfoDigit].append(curNode)
    #
    #     # 不顾原来的边关系，直接做dfs
    #     if jumpInfoDigit is None:  # 从栈中无法找到地址
    #         assert self.blocks[curNode].jumpType not in ["conditional", "unconditional"]
    #         if self.blocks[curNode].jumpType == "fall":
    #             self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
    #     else:
    #         if self.blocks[curNode].jumpType == "conditional":  # fall 边
    #             self.__dfs(jumpInfoDigit, curExecutor)
    #             self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
    #         elif self.blocks[curNode].jumpType == "unconditional":
    #             self.__dfs(jumpInfoDigit, curExecutor)
    #         elif self.blocks[curNode].jumpType == "fall":
    #             self.__dfs(curNode + self.blocks[curNode].length, curExecutor)
    #         else:  # terminal only
    #             assert 0  # 返回
    #
    #     self.visiting[curNode] = False
