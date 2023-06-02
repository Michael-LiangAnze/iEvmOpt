class BasicBlock:

    def __init__(self,
                 blockInfo: dict):
        """ 输出当前程序状态
       :param blockInfo:从Json文件中读取到的node信息
       """
        # 块的基本信息
        self.offset = int(blockInfo["offset"])
        self.length = int(blockInfo["length"])
        self.blockType = blockInfo["type"]
        self.stackBalance = int(blockInfo["stackBalance"])
        self.bytecode = bytearray.fromhex(blockInfo["bytecodeHex"])  # 字节码，存储为字节数组
        self.bytecodeStr = blockInfo["bytecodeHex"]  # 字节码，存储为字符串
        self.instrs = str(blockInfo["parsedOpcodes"]).split('\n')  # 存储的指令汇编码
        self.instrsStr = blockInfo["parsedOpcodes"]  # 指令，存储为字符串
        self.jumpType = ""  # 论文中提及的类型：unconditional、conditional、terminal、fall
        self.instrNum = self.instrs.__len__()  # 指令的数量
        self.isInvalid = False  # 是否为invalid块
        self.couldBeCaller = False

        checker = self.instrs[self.instrNum - 1].split(' ')[1]
        match checker:
            case "JUMP":
                self.jumpType = "unconditional"
                if self.instrs[self.instrNum - 2].split(' ')[1].find("PUSH") != -1:
                    self.couldBeCaller = True
            case "JUMPI":
                self.jumpType = "conditional"
            case "INVALID" | "REVERT" | "RETURN" | "STOP" | "SELFDESTRUCT":  # terminal
                self.jumpType = "terminal"
                if checker == "INVALID":
                    self.isInvalid = True
            case _:
                self.jumpType = "fall"

        # 块的辅助信息
        self.jumpiDest = {}  # 记录jumpi的块条件为True的跳转目标节点的offset，格式为 True:offset,False:offset
        self.jumpDest = []  # 记录jump的块的跳转目标节点的offset，格式为 [offset1,offset2...]
        self.instrAddrs = [int(instr.split(':')[0]) for instr in self.instrs]  # 存储的指令的地址，用于优化时使用
        self.removedByte = dict(
            zip([i for i in range(self.length)], [False for i in range(self.length)]))  # 下标为i的字节是否需要删除，用于删除冗余序列

    def printBlockInfo(self):
        """ 打印基本块的信息
        """
        print("Block'offset:{}".format(self.offset))
        print("Block'length:{}".format(self.length))
        print("Block'block type:{}".format(self.blockType))
        print("Block'jump type:{}".format(self.jumpType))
        print("Block'stackBalance:{}".format(self.stackBalance))
        print("Block'bytecode:{}".format([hex(i) for i in self.bytecode]))
        print("Block'instrutions:{}".format(self.instrs))
        print("Block'instruction number:{}".format(self.instrNum))
        print("Block is INVALID:{}".format(self.isInvalid))
        print("Block jumpDest offset:{}".format(self.jumpDest))
        print("Block jumpiDest offset:{}".format(self.jumpiDest))
