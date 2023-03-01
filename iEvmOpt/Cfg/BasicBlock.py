class BasicBlock:

    def __init__(self,
                 blockInfo: dict):
        """ 输出当前程序状态
       :param blockInfo:从Json文件中读取到的node信息
       """
        self.offset = int(blockInfo["offset"])
        self.length = int(blockInfo["length"])
        self.bType = blockInfo["type"]
        self.stackBalance = int(blockInfo["stackBalance"])  # 这是什么？
        self.bytecode = bytearray.fromhex(blockInfo["bytecodeHex"])  # 字节码，存储为字节数组

    def printBlockInfo(self):
        """ 打印基本块的信息
       """
        print("Block offset:{}".format(self.offset))
        print("Block length:{}".format(self.length))
        print("Block type:{}".format(self.bType))
        print("Block stackBalance:{}".format(self.stackBalance))
        print("Block bytecode:{}".format(self.bytecode))
