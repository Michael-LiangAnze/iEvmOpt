from Cfg.BasicBlock import BasicBlock


class JumpEdge:
    '''
    这里给出一个假设：所有的调用都是一条push紧跟一条jump引起的
    同时，所有返回的jump前都不能是push
    '''

    def __init__(self, beginBlock: BasicBlock, targetBlock: BasicBlock):
        self.beginNode = beginBlock.offset
        self.targetNode = targetBlock.offset
        self.beginAddr = beginBlock.offset + beginBlock.length - 1
        self.targetAddr = targetBlock.offset
        self.tetrad = [None, None, None, None]  # 匹配四元组
        self.couldBeCallEdge = beginBlock.couldBeCaller
        if self.couldBeCallEdge:  # 可能是调用边，存储(a,a+1,None,None)
            self.tetrad[0] = self.beginAddr
            self.tetrad[1] = self.beginAddr + 1
        else:  # 不可能是调用边，可能是返回边，存储(None,None,b-1,b)
            self.tetrad[2] = self.targetAddr - 1
            self.tetrad[3] = self.targetAddr

    def output(self):
        print("Edge'beginNode:{}".format(self.beginNode))
        print("Edge'targetNode:{}".format(self.targetNode))
        print("Edge'beginAddr:{}".format(self.beginAddr))
        print("Edge'targetAddr:{}".format(self.targetAddr))
        print("Edge'tetrad:{}".format(self.tetrad))
        print("Edge'couldBeCallEdge:{}\n".format(self.couldBeCallEdge))
