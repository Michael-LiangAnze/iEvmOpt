from GraphTools import DominatorTreeBuilder

if __name__ == '__main__':
    domTree = DominatorTreeBuilder()
    domTree.initGraph(3, [[1, 3], [2, 3], [1, 2]])
    domTree.buildTreeFrom(1)  # 原图的偏移量为0的block
    idom = domTree.getIdom()
    print(idom)
