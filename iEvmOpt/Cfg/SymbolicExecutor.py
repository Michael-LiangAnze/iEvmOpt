from collections import deque
from Cfg.BasicBlock import BasicBlock
from z3 import *


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

    def printState(self, printBlock: bool = True):
        """ 输出当前程序状态
        :param printBlock:是否输出基本块信息
        """
        if printBlock:
            self.curBlock.printBlockInfo()
        print("Current PC is:{}".format(self.PC))
        # print("Current stack:{}<-top".format(list(self.stack.getStack())))
        print("Current stack:{}<-top".format(list(self.stack.getStack(True))))
        print("Current storage:{}".format(self.storage))
        print("Current memory:{}\n".format(self.memory))

    def execNextOpCode(self):
        """ 从当前PC开始，执行下一条指令
        规定执行完当前指令之后，PC指向下一条指令的第一个字节
        """
        assert self.curBlock.offset <= self.PC <= self.curBlock.offset + self.curBlock.length
        index = self.PC - self.curBlock.offset
        opCode = self.curBlock.bytecode[index]
        '''
        每个函数的执行思路：需要先判断操作数是否为bool表达式，如果是的话就用If(exp,a,b)来代替
        例子：
            a = BitVec('a', 2)
            b = BitVec('b', 2)
            c = a > b
            if is_bool(c):
                print('c is bool')
                c = If(c, BitVecVal(1,2), BitVecVal(0,2))
            d = BitVec('d', 2)
            mod = c * d == 2
            s = Solver()
            s.add(mod)
            print(s.check())
            solve(mod)
        '''
        match opCode:
            case 0x00:  # stop
                pass
            case 0x01:  # add
                self.__execAdd()
            case 0x02:  # mul
                self.__execMul()
            case 0x03:
                self.__execSub()
            case 0x04:
                self.__execDiv()
            case 0x05:
                self.__execSdiv()
            case 0x06:
                self.__execMod()
            case 0x07:
                self.__execSmod()
            case 0x08:
                self.__execAddMod()
            case 0x09:
                self.__execMulMod()
            case i if 0x60 <= opCode <= 0x7f:  # push
                self.__execPush(opCode)
            case _:  # Pattern not attempted
                err = 'Opcode {} is not found!'.format(hex(opCode))
                assert 0, err
        self.PC += 1

    def __execAdd(self):  # 0x01
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a + b))

    def __execMul(self):  # 0x02
        a = self.stack.pop()
        b = self.stack.pop()
        if is_bool(a):  # a是一个逻辑表达式
            a = If(a, BitVecVal(1, 256), BitVecVal(0, 256))
        if is_bool(b):  # b是一个逻辑表达式
            b = If(b, BitVecVal(1, 256), BitVecVal(0, 256))
        self.stack.push(simplify(a * b))

    def __execSub(self):  # 0x03
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a - b))

    def __execDiv(self):  # 0x04
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(UDiv(a, b)))

    def __execSdiv(self):  # 0x05
        # 两个例子
        #     结果为2：
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFE
        #         SDIV
        #     结果为-2(0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe)：
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #         PUSH32 0x0000000000000000000000000000000000000000000000000000000000000002
        #         SDIV
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a / b))

    def __execMod(self):  # 0x06
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(If(b == 0, BitVecVal(0, 256), URem(a, b))))

    def __execSmod(self):  # 0x07
        a = self.stack.pop()
        b = self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(If(b == 0, BitVecVal(0, 256), SRem(a, b))))

    def __execAddMod(self):  # 0x08
        a = self.stack.pop()
        b = self.stack.pop()
        c = self.stack.pop()
        assert not is_bool(a) and not is_bool(b) and not is_bool(c)  # abc都不能是条件表达式
        zero = BitVecVal(0, 1)  # a+b可能超出2^256-1，需要先调整为257位的比特向量
        a = Concat(zero, a)
        b = Concat(zero, b)
        c = Concat(zero, c)
        res = simplify(a + b)  # 先计算出a+b
        res = simplify(If(c == 0, BitVecVal(0, 257), URem(res, c)))  # 再计算(a+b) % c
        self.stack.push(simplify(Extract(255, 0, res)))  # 先做截断再push

    def __execMulMod(self):  # 0x09
        a = self.stack.pop()
        b = self.stack.pop()
        c = self.stack.pop()
        assert not is_bool(a) and not is_bool(b) and not is_bool(c)  # abc都不能是条件表达式
        zero = BitVecVal(0, 256)  # a*b可能超出范围，需要先调整为512位的比特向量
        a = Concat(zero, a)
        b = Concat(zero, b)
        c = Concat(zero, c)
        res = simplify(a * b)  # 先计算出a*b
        res = simplify(If(c == 0, BitVecVal(0, 512), URem(res, c)))  # 再计算(a*b) % c
        self.stack.push(simplify(Extract(255, 0, res)))  # 先做截断再push

    def __execPush(self, opCode):  # 0x60 <= opCode <= 0x7f
        byteNum = opCode - 0x5f  # push的字节数
        num = 0
        for i in range(byteNum):
            num <<= 8
            self.PC += 1  # 指向最高位的字节
            num |= self.curBlock.bytecode[self.PC - self.curBlock.offset]  # 低位加上相应的字节
        # print("push num:{},byte num:{}".format(hex(num), byteNum))
        num = BitVecVal(num, 256)
        self.stack.push(num)


class Stack:
    def __init__(self):
        self.__stack = deque()

    def push(self, a):
        if len(self.__stack) < 16:
            self.__stack.append(a)
        else:
            assert 0, "stack is full!"

    def pop(self):
        if len(self.__stack) > 0:
            return self.__stack.pop()
        else:
            assert 0, "stack is empty!"

    def size(self):
        return len(self.__stack)

    def getStack(self, isHex: bool = False):
        if not isHex:
            return self.__stack
        else:
            hexStack = deque()
            for i in range(len(self.__stack)):
                hexStack.append(hex(int(self.__stack[i].__str__())))
            return hexStack
