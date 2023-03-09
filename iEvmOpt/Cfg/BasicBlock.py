class BasicBlock:

    def __init__(self,
                 blockInfo: dict):
        """ 输出当前程序状态
       :param blockInfo:从Json文件中读取到的node信息
       """
        # 块的基本信息
        self.offset = int(blockInfo["offset"])
        self.length = int(blockInfo["length"])
        self.cfgType = blockInfo["type"]
        self.stackBalance = int(blockInfo["stackBalance"])  # 这是什么？
        self.bytecode = bytearray.fromhex(blockInfo["bytecodeHex"])  # 字节码，存储为字节数组
        self.instrs = str(blockInfo["parsedOpcodes"]).split('\n')  # 存储的指令汇编码
        self.blockType = ""  # 论文中提及的类型：unconditional、conditional、terminal、fall
        self.instrNum = len(self.instrs)  # 指令的数量
        self.isInvalid = False  # 是否为invalid块
        # 是否为函数起始节点。有两种判断方法：第一种是直接看dispatcher块的出边，如果有这样一条边：dispatcher->common，则将common
        # 标记为函数起始节点；第二种是看这样的边：common-(unconditional jump)->common，则将后一个common标记为函数起始节点
        # 其实这一个标记并不是严谨的，只是为了方便函数调用链的构建
        self.isFuncBegin = False
        self.isFuncEnd = False

        checker = self.instrs[self.instrNum - 1].split(' ')[1]
        match checker:
            case "JUMP":
                self.blockType = "unconditional"
            case "JUMPI":
                self.blockType = "conditional"
            case "INVALID" | "REVERT" | "RETURN" | "STOP":  # terminal
                self.blockType = "terminal"
                if checker == "INVALID":
                    self.isInvalid = True
            case _:
                self.blockType = "fall"

        # 块的辅助信息
        self.jumpiDest = {}  # 记录jumpi的块条件为True的跳转目标节点的offset，格式为 True:offset,False:offset
        self.jumpDest = []  # 记录jump的块的跳转目标节点的offset，格式为 [offset1,offset2...]

    def printBlockInfo(self):
        """ 打印基本块的信息
       """
        print("Block'offset:{}".format(self.offset))
        print("Block'length:{}".format(self.length))
        print("Block'cfg type:{}".format(self.cfgType))
        print("Block'block type:{}".format(self.blockType))
        print("Block'stackBalance:{}".format(self.stackBalance))
        print("Block'bytecode:{}".format(self.bytecode))
        print("Block'instrutions:{}".format(self.instrs))
        print("Block'instruction number:{}".format(self.instrNum))
        print("Block is INVALID:{}".format(self.isInvalid))
        print("Block is isFuncBegin:{}".format(self.isFuncBegin))
        print("Block jumpiDest offset:{}".format(self.jumpiDest))
        print("Block jumpDest offset:{}\n".format(self.jumpDest))

