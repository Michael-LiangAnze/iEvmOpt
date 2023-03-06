from graphviz import Digraph


class DotGraph:
    def __init__(self, edges: dict, nodes: list, outputPath: str, outName: str):
        self.edges = edges  # 存储出边表，格式为 from:[to1,to2...]
        self.nodes = nodes  # 存储点，格式为 [n1,n2,n3...]
        self.outputPath = outputPath
        self.outName = outName

    def genDotGraph(self):
        # 根据生成的cfg生成点图
        dot = Digraph()
        # 添加点和边
        for i in self.nodes:
            dot.node(str(i), str(i))
        for _from in self.edges:
            for _to in self.edges[_from]:
                dot.edge(str(_from), str(_to))
        dot.render(filename=self.outputPath + self.outName + "_graph.gv",
                   outfile=self.outputPath + self.outName + "_graph.png", format='png')
