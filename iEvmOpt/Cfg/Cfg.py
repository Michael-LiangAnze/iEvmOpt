from Cfg.BasicBlock import BasicBlock


class Cfg:

    def __init__(self):
        self.edges = {}  # 存储出边表，格式为 id:[n1,n2...]
        self.blocks = {}  # 存储基本块，格式为 id:BasicBlock
        self.initBlockId = 0
        self.exitBlockId = 0

    def addBasicBlock(self, block: BasicBlock):
        self.blocks[int(block.offset)] = block

    def addEdge(self, edge: dict):
        _from = int(edge["from"])
        self.edges[_from] = []
        for _to in edge["to"]:
            self.edges[_from].append(int(_to))

    def output(self):
        for key, value in self.blocks.items():
            print('{key}:{value}'.format(key=key, value=value))
        for key, value in self.edges.items():
            print('{f}->{t}'.format(f=key, t=value))
