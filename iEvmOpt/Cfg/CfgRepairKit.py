from AssertionOptimizer.TagStacks.TagStackForCfgRepairKit import TagStackForCfgRepairKit
from Cfg.Cfg import Cfg
from Utils.Logger import Logger


class CfgRepairKit:
    def __init__(self, cfg: Cfg):
        """
        cnmd sb ethersolve，一眼都能看出的跳转边你都分析不出来
        test14 block16 :
        push 0x4a
        push 0x1000...
        mul
        push 0x1000...
        swap1
        div
        jump
        你跟我说跳到exit block？

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

        self.__dfs(0, TagStackForCfgRepairKit(self.cfg))

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

    def __dfs(self, curNode: int, parentTagStack: TagStackForCfgRepairKit):
        """
        进行dfs，使用原有的边，尝试进行修复
        该dfs不会走回头路，不会走已经走过的路
        :param curNode:
        :return:
        """
        if self.visiting[curNode] or curNode == self.cfg.exitBlockId or self.blocks[curNode].jumpType == "terminal":
            return
        # print(curNode)
        self.visiting[curNode] = True

        # 第一步，进行tagstack执行，这一步需要复制父节点的tagstack信息
        curTagStack = TagStackForCfgRepairKit(self.cfg)
        curTagStack.setTagStack(parentTagStack.getTagStack())
        curTagStack.setBeginBlock(curNode)
        jumpInfo = None
        while not curTagStack.allInstrsExecuted():
            if curTagStack.isLastInstr():
                jumpInfo = curTagStack.getTagStackTop()
            curTagStack.execNextOpCode()
            # curTagStack.printState(False)
            # print(jumpInfo)

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

        # 继续dfs
        # 因为出边的数量可能在遍历的时候增加/减少，因此采用下标的方式遍历
        # i = 0
        # while i < len(self.edges[curNode]):
        #     nextNode = self.edges[curNode][i]
        #     self.__dfs(nextNode, curTagStack)
        #     i += 1

        # 不顾原来的边关系，直接做dfs
        if jumpInfoDigit is None:  # 从栈中无法找到地址
            assert self.blocks[curNode].jumpType not in ["conditional", "unconditional"]
            if self.blocks[curNode].jumpType == "fall":
                self.__dfs(curNode + self.blocks[curNode].length, curTagStack)
        else:
            if self.blocks[curNode].jumpType == "conditional":  # fall 边
                self.__dfs(jumpInfoDigit, curTagStack)
                self.__dfs(curNode + self.blocks[curNode].length, curTagStack)
            elif self.blocks[curNode].jumpType == "unconditional":
                self.__dfs(jumpInfoDigit, curTagStack)
            elif self.blocks[curNode].jumpType == "fall":
                self.__dfs(curNode + self.blocks[curNode].length, curTagStack)
            else:  # terminal only
                assert 0  # 返回
        # if curNode in [587,785]:
        #     print(curNode,jumpInfoDigit)

        self.visiting[curNode] = False
