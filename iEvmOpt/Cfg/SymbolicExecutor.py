from collections import deque
from Cfg.BasicBlock import BasicBlock


class SymbolicExecutor:
    def __init__(self):
        self.curBlock: BasicBlock = None  # 当前执行的基本块
        self.PC = 0  # 当前执行指令的指针
        self.stack = Stack()  # 符号执行栈，重新封装一次
        self.storage = dict()  # 使用字典存储，格式为  addr:data
        self.memory = dict()  # 使用字典存储，格式为  addr:data

    def setBeginBlock(self, curBlock: BasicBlock):
        """ 设置起始执行块，同时设置PC为块的偏移量
        :param curBlock: 起始块
        """
        self.curBlock = curBlock
        self.PC = self.curBlock.offset

    def printState(self,printBlock:bool = True):
        """ 输出当前程序状态
        :param printBlock:是否输出基本块信息
        """
        if printBlock:
            self.curBlock.printBlockInfo()
        print("Current PC is:{}".format(self.PC))
        print("Current stack:{}".format(list(self.stack.getStack())))
        print("Current storage:{}".format(self.storage))
        print("Current memory:{}\n".format(self.memory))


    def execNextOpCode(self):
        """ 从当前PC开始，执行下一条指令
        规定执行完当前指令之后，PC指向下一条指令的第一个字节
        """
        assert self.PC >= self.curBlock.offset
        assert self.PC <= self.curBlock.offset + self.curBlock.length
        index = self.PC - self.curBlock.offset
        opCode = self.curBlock.bytecode[index]
        match opCode:
            case 0x01:  # add
                self.__execAdd(opCode)
            case i if 0x60 <= opCode <= 0x7f:  # push
                self.__execPush(opCode)
            case 7:
                print(5)
            case _:  # Pattern not attempted
                print('Opcode {} is not found!'.format(opCode))
                assert False
        self.PC += 1

    def __execAdd(self, opCode):
        assert self.stack.size() >= 2
        a = self.stack.pop()
        b = self.stack.pop()
        res = self.stack.push(a + b)
        assert res

    def __execPush(self, opCode):  # 执行push指令
        byteNum = opCode - 0x5f  # push的字节数
        num = 0
        for i in range(byteNum):
            num <<= 1
            self.PC += 1  # 指向最高位的字节
            num |= self.curBlock.bytecode[self.PC - self.curBlock.offset]  # 低位加上相应的字节
        res = self.stack.push(num)
        assert res


class Stack:
    def __init__(self):
        self.__stack = deque()

    def push(self, a):  # push成功返回True
        if len(self.__stack) < 16:
            self.__stack.append(a)
            return True
        else:
            return False

    def pop(self):
        return self.__stack.pop()  # 不做检查，使用deque的error

    def size(self):
        return len(self.__stack)

    def getStack(self):
        return self.__stack
