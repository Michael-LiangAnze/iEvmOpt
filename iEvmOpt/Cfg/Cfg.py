from Cfg.BasicBlock import BasicBlock


class Cfg:

    def __init__(self):
        self.edges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.rEdges = {}  # 存储入边表，格式为 to:[from1,from2...]
        self.blocks = {}  # 存储基本块，格式为 起始offset:BasicBlock
        self.initBlockId = 0
        self.exitBlockId = 0

    def addBasicBlock(self, block: BasicBlock):
        self.blocks[int(block.offset)] = block

    def addEdge(self, edge: dict):
        _from = int(edge["from"])
        if _from not in self.rEdges.keys():  # 起始块可能会不在入边表
            self.rEdges[_from] = []
        self.edges[_from] = []
        # 可能存在重复的出边
        _toBlocks = list(set(edge["to"]))
        for t in _toBlocks:
            _to = int(t)
            self.edges[_from].append(_to)
            if _to not in self.rEdges.keys():
                self.rEdges[_to] = []
            self.rEdges[_to].append(_from)

    def output(self):
        print("blocks:")
        for key, value in self.blocks.items():
            value.printBlockInfo()
        print("edges:")
        for key, value in self.edges.items():
            print('{f}->{t}'.format(f=key, t=value))
        print("\nredges:")
        for key, value in self.rEdges.items():
            print('{t}->{f}'.format(t=key, f=value))
