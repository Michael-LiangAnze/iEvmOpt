# https://www.luogu.com.cn/problem/solution/P5180

class side:
    def __init__(self):
        self.y = 0
        self.next = 0


class DominatorTreeBuilder:
    """用于生成支配树，需要注意的是，在该类当中，图的点是用从1开始的连续数字来表示，返回值也是
    """

    def __init__(self):
        self.n = 0
        self.m = 0
        self.cs = 0
        self.co = 0

        self.e = []
        self.lin = []
        self.dfn = []
        self.ord = []
        self.fa = []
        self.idom = []
        self.sdom = []
        self.uni = []
        self.mn = []
        self.ans = []

    def __ins(self, _id: int, x: int, y: int):
        self.cs += 1
        self.e[self.cs].y = y
        self.e[self.cs].next = self.lin[_id][x]
        self.lin[_id][x] = self.cs

    def initGraph(self, nodeNum: int, edges: list):
        """用于初始化构造支配树所需要的信息
        :param nodeNum:图的节点数量，因为只记录了数量，因此图的节点是用 1~nodeNum之间的数字来标识
        :param edges: 图的边，格式为[[n1,n2],[n3,n4]......]
        """
        self.n = nodeNum
        self.m = len(edges)

        self.e = [side() for _ in range(2 * self.m + self.n + 9)]
        for _ in range(3):
            self.lin.append([0 for _ in range(self.n + 9)])
        self.dfn = [0 for _ in range(self.n + 9)]
        self.ord = [0 for _ in range(self.n + 9)]
        self.fa = [0 for _ in range(self.n + 9)]
        self.idom = [0 for _ in range(self.n + 9)]
        self.sdom = [0 for _ in range(self.n + 9)]
        self.uni = [0 for _ in range(self.n + 9)]
        self.mn = [0 for _ in range(self.n + 9)]
        self.ans = [0 for _ in range(self.n + 9)]

        for i in range(0, self.m):
            x, y = edges[i][0], edges[i][1]
            self.__ins(0, x, y)
            self.__ins(1, y, x)

    def __tarjan(self, k: int):
        self.co += 1
        self.dfn[k] = self.co
        self.ord[self.co] = k
        i = self.lin[0][k]
        while i != 0:
            if self.dfn[self.e[i].y] == 0:
                self.fa[self.e[i].y] = k
                self.__tarjan(self.e[i].y)
            i = self.e[i].next

    def __queryNni(self, k: int):
        if k == self.uni[k]:
            return k
        res = self.__queryNni(self.uni[k])
        if self.dfn[self.sdom[self.mn[self.uni[k]]]] < self.dfn[self.sdom[self.mn[k]]]:
            self.mn[k] = self.mn[self.uni[k]]
        self.uni[k] = res
        return res

    def buildTreeFrom(self, beginNode: int):
        """ 返回值为支配树的直接支配节点关系，格式为 {n:n的直接支配节点}
        :param beginNode:图的起始节点
        """
        self.__tarjan(beginNode)
        for i in range(1, self.n + 1):
            self.sdom[i] = i
            self.uni[i] = i
            self.mn[i] = i

        for i in range(self.co, 1, -1):
            t = self.ord[i]

            j = self.lin[1][t]
            while j != 0:
                y = self.e[j].y
                if self.dfn[y] == 0:
                    continue
                self.__queryNni(y)
                if self.dfn[self.sdom[self.mn[y]]] < self.dfn[self.sdom[t]]:
                    self.sdom[t] = self.sdom[self.mn[y]]
                j = self.e[j].next

            self.uni[t] = self.fa[t]
            self.__ins(2, self.sdom[t], t)

            t = self.fa[t]
            j = self.lin[2][t]
            while j != 0:
                y = self.e[j].y
                self.__queryNni(y)
                self.idom[y] = t if t == self.sdom[self.mn[y]] else self.mn[y]
                j = self.e[j].next

            self.lin[2][t] = 0

        for i in range(2, self.co + 1):
            t = self.ord[i]
            if self.idom[t] != self.sdom[t]:
                self.idom[t] = self.idom[self.idom[t]]

    def getIdom(self):
        """ 返回值为支配树的直接支配节点关系，格式为{n:n的直接支配节点}
        """
        return {i:self.idom[i] for i in range(1, self.n + 1)}

    def outputIdom(self):
        for i in range(1, self.n + 1):
            print(self.idom[i])
