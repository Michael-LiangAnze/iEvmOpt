from graphviz import Digraph
import random
import colorsys


class DotGraphGenerator:
    def __init__(self, nodes: list, edges: dict, group: dict = None, length: dict = None):
        self.edges = edges  # 存储出边表，格式为 from:[to1,to2...]
        self.nodes = nodes  # 存储点，格式为 [n1,n2,n3...]
        self.group = group  # 按组赋颜色，格式为： node:groupId
        self.length = length  # block的长度，格式为： node:length

    def genDotGraph(self, outputPath: str, outName: str):
        # 根据生成的cfg生成点图
        dot = Digraph()
        # 添加点和边
        if self.group is None:
            for i in self.nodes:
                dot.node(str(i), label=str(i))
        else:
            groupToColor = {}
            for id in self.group.values():
                groupToColor[id] = None
            colors = self.ncolors(groupToColor.keys().__len__())  # 随机多生成几个颜色
            i = 0
            for id in groupToColor:
                # color = colors[i]
                # groupToColor[id] = "#" + "".join(['{:02x}'.format(rgb) for rgb in color]) + "78"
                groupToColor[id] = colors[i]
                i += 1
            groupToColor[0] = "#00000000"  # 规定0号是透明
            for i in self.nodes:
                dot.node(str(i), label=str(i) + "\l" + groupToColor[self.group[i]] + "\llen:" + str(self.length[i])+"\l",
                         style='filled',
                         fillcolor=groupToColor[self.group[i]])

        for _from in self.edges:
            for _to in self.edges[_from]:
                dot.edge(str(_from), str(_to))
        dot.render(filename=outputPath + outName + "_graph.gv",
                   outfile=outputPath + outName + "_graph.png", format='png')

    # https://blog.csdn.net/choumin/article/details/90320297
    def get_n_hls_colors(self, num):
        hls_colors = []
        i = 0
        step = 360.0 / num
        while i < 360:
            h = i
            s = 90 + random.random() * 10
            l = 50 + random.random() * 10
            _hlsc = [h / 360.0, l / 100.0, s / 100.0]
            hls_colors.append(_hlsc)
            i += step

        return hls_colors

    def ncolors(self, num):
        rgb_colors = [
            "#ed1299", "#09f9f5", "#246b93", "#cc8e12", "#d561dd", "#c93f00", "#ddd53e",
            "#4aef7b", "#e86502", "#9ed84e", "#39ba30", "#6ad157", "#8249aa", "#99db27", "#e07233", "#ff523f",
            "#ce2523", "#f7aa5d", "#cebb10", "#03827f", "#931635", "#373bbf", "#a1ce4c", "#ef3bb6", "#d66551",
            "#1a918f", "#ff66fc", "#2927c4", "#7149af", "#57e559", "#8e3af4", "#f9a270", "#22547f", "#db5e92",
            "#edd05e", "#6f25e8", "#0dbc21", "#280f7a", "#6373ed", "#5b910f", "#7b34c1", "#0cf29a", "#d80fc1",
            "#dd27ce", "#07a301", "#167275", "#391c82", "#2baeb5", "#925bea", "#63ff4f"
        ]
        # rgb_colors = [
        #     [0xe6, 0x19, 0x4b],
        #     [0x3c, 0xb4, 0x4b],
        #     [0xff, 0xe1, 0x19],
        #     [0x43, 0x63, 0xd8],
        #     [0xf5, 0x82, 0x31],
        #     [0x91, 0x1e, 0xb4],
        #     [0x42, 0xd4, 0xf4],
        #     [0xf0, 0x32, 0xe6],
        #     [0xbf, 0xef, 0x45],
        #     [0xfa, 0xb3, 0xd4],
        #
        #     [0x46, 0x99, 0x90],
        #     [0xdc, 0xbe, 0xff],
        #     [0x9a, 0x63, 0x24],
        #     [0xff, 0xfa, 0xc8],
        #     [0x80, 0x00, 0x00],
        #     [0xaa, 0xff, 0xc3],
        #     [0x80, 0x80, 0x00],
        #     [0xff, 0xd8, 0xb1],
        #     [0x00, 0x00, 0x75],
        #     [0xa9, 0xa9, 0xa9],
        # ]
        # # 颜色还是不够
        # if num < 1:
        #     return rgb_colors
        #
        # hls_colors = self.get_n_hls_colors(num - 20)
        # for hlsc in hls_colors:
        #     _r, _g, _b = colorsys.hls_to_rgb(hlsc[0], hlsc[1], hlsc[2])
        #     r, g, b = [int(x * 255.0) for x in (_r, _g, _b)]
        #     rgb_colors.append([r, g, b])

        return rgb_colors
