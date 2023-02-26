class BasicBlock:

    def __init__(self,
                 blockInfo:dict):
        self.id = int(blockInfo["offset"]) # id使用基本块在字节码中的偏移量
        self.offset = int(blockInfo["offset"])
        # 其他信息


