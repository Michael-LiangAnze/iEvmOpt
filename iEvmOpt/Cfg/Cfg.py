from Cfg.BasicBlock import BasicBlock


class Cfg:

    def __init__(self):
        self.edges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.inEdges = {}  # 存储入边表，格式为 to:[from1,from2...]
        self.blocks = {}  # 存储基本块，格式为 起始offset:BasicBlock
        self.initBlockId = 0
        self.exitBlockId = 0

        self.bytecodeLength = 0  # cfg的字节码长度，单位为字节
        self.bytecodeStr = ""

        self.beginIndexInBytecode = 0  # cfg在原字节码中的起始偏移量
        self.jumpDests = set()  # 存储所有jumpdest的offset，用于tagStack

        # 额外的信息
        self.pushedData = set()  # 存储所有push过的数据

    def genBytecodeStr(self):
        # 已经读入了所有的block，将它们拼接为一个长字符串，并设置长度
        nodes = list(self.blocks.keys())
        nodes.sort()
        # print(nodes)
        for node in nodes:
            self.bytecodeStr += self.blocks[node].bytecodeStr

        # 注意，exit block的长度为，实际上并不需要考虑它的长度
        assert self.bytecodeStr.__len__() % 2 == 0
        self.bytecodeLength = self.bytecodeStr.__len__() // 2

    def getBytecodeLen(self):
        return self.bytecodeLength

    def setBeginIndex(self, index: int):
        '''
        设置cfg在原字节码中的起始偏移量
        :param index:cfg在原字节码中的起始偏移量
        :return:None
        '''
        self.beginIndexInBytecode = index

    def getBeginIndex(self):
        '''
        获取cfg在原字节码中的起始偏移量
        :return:cfg在原字节码中的起始偏移量
        '''
        return self.beginIndexInBytecode

    def addBasicBlock(self, block: BasicBlock):
        offset = int(block.offset)
        self.blocks[offset] = block
        if block.length > 0:  # exit的是0
            if block.bytecode[0] == 0x5b:  # jumpdest 开头
                self.jumpDests.add(block.offset)
        if offset not in self.edges.keys():
            self.edges[offset] = []
        if offset not in self.inEdges.keys():
            self.inEdges[offset] = []

    def addEdge(self, edge: dict):
        # 必须先添加完block再添加edge
        _from = int(edge["from"])
        # 可能存在重复的出边
        _toBlocks = list(set(edge["to"]))
        for t in _toBlocks:
            _to = int(t)
            self.edges[_from].append(_to)
            self.inEdges[_to].append(_from)

    def output(self):
        print("blocks:")
        for key, value in self.blocks.items():
            value.printBlockInfo()
        print("edges:")
        for key, value in self.edges.items():
            print('{f}->{t}'.format(f=key, t=value))
        print("\nredges:")
        for key, value in self.inEdges.items():
            print('{t}->{f}'.format(t=key, f=value))
