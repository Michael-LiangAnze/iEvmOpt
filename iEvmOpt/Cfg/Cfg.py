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
        self.tailOpcodeStr = None  # 结尾的操作码，可能是00，也可能是fe
        self.tailOpcode = 0

    def genBytecodeStr(self, tailOpcodeStr: str):
        # 已经读入了所有的block，将它们拼接为一个长字符串，并设置长度
        nodes = list(self.blocks.keys())
        nodes.sort()
        for node in nodes:
            self.bytecodeStr += self.blocks[node].bytecodeStr
        if tailOpcodeStr == "00":
            self.tailOpcode = 0x00
        elif tailOpcodeStr == "fe":
            self.tailOpcode = 0xfe
        else:
            assert 0
        self.bytecodeStr += tailOpcodeStr  # 结尾的00或者fe
        self.tailOpcodeStr = tailOpcodeStr
        assert self.bytecodeStr.__len__() % 2 == 0
        self.bytecodeLength = self.bytecodeStr.__len__() // 2

    def getTailOpcodeStr(self):
        return self.tailOpcodeStr

    def getTailOpcode(self):
        return self.tailOpcode

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
        self.blocks[int(block.offset)] = block

    def addEdge(self, edge: dict):
        _from = int(edge["from"])
        if _from not in self.inEdges.keys():  # 起始块可能会不在入边表
            self.inEdges[_from] = []
        self.edges[_from] = []
        # 可能存在重复的出边
        _toBlocks = list(set(edge["to"]))
        for t in _toBlocks:
            _to = int(t)
            self.edges[_from].append(_to)
            if _to not in self.inEdges.keys():
                self.inEdges[_to] = []
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
