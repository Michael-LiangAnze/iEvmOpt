from Cfg.BasicBlock import BasicBlock


class Cfg:

    def __init__(self):
        self.edges = {}  # 存储出边表，格式为 from:[to1,to2...]
        self.blocks = {}  # 存储基本块，格式为 起始offset:BasicBlock
        self.initBlockId = 0
        self.exitBlockId = 0

    def addBasicBlock(self, block: BasicBlock):
        self.blocks[int(block.offset)] = block

    def addEdge(self, edge: dict):
        _from = int(edge["from"])
        self.edges[_from] = []
        # 可能存在重复的出边
        _toBlocks = list(set(edge["to"]))
        for _to in _toBlocks:
            self.edges[_from].append(int(_to))

    def output(self):
        for key, value in self.blocks.items():
            value.printBlockInfo()

        for key, value in self.edges.items():
            print('{f}->{t}'.format(f=key, t=value))
