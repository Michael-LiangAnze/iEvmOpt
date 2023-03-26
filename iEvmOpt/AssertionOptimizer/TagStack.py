from Cfg.BasicBlock import BasicBlock
from z3 import *

from Cfg.Cfg import Cfg
from Utils import Stack


class TagStack:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.curBlock: BasicBlock = None  # 当前执行的基本块
        self.PC = 0  # 当前执行指令的指针
        self.tagStack = Stack()  # tag栈，记录的格式为：[push的值，push指令的地址，push指令所在的block]，一旦该元素参与了运算，则将运算结果置为none

        # 辅助信息
        self.lastInstrAddrOfBlock = 0  # block内最后一个指令的地址
        self.jumpCond = None  # 如果当前的Block为无条件Jump，记录跳转的条件

    def clearExecutor(self):
        '''
        清空符号执行器
        :return: None
        '''
        self.curBlock = None
        self.PC = 0
        self.jumpCond = None  # 记录jumpi的跳转条件，详见jumpi的实现
        self.tagStack.clear()

    def allInstrsExecuted(self):
        return self.PC > self.lastInstrAddrOfBlock

    def isLastInstr(self):
        return self.PC == self.lastInstrAddrOfBlock

    def getTagStack(self):
        return self.tagStack.getStack()

    def setTagStack(self, stackInfo: list):
        self.tagStack.setStack(stackInfo)

    def setBeginBlock(self, curBlockId: int):
        """ 设置执行块，同时设置PC为块的偏移量
        :param curBlockId: 起始块的id(offset)
        """
        self.curBlock = self.cfg.blocks[curBlockId]
        self.PC = self.curBlock.offset
        self.lastInstrAddrOfBlock = self.curBlock.offset + self.curBlock.length - 1  # 最后一条指令是一个字节的

    def getTagStackTop(self):
        return self.tagStack.getTop()

    def printState(self, printBlock: bool = True):
        """ 输出当前程序状态
        :param printBlock:是否输出基本块信息
        """
        if printBlock:
            self.curBlock.printBlockInfo()
        print("Current PC is:{}".format(self.PC))
        print("Current tag stack:{}<-top".format(list(self.tagStack.getStack())))

    def execNextOpCode(self):
        ''' 从当前PC开始，执行下一条指令
        规定执行完当前指令之后，PC指向下一条指令的第一个字节
        :return:None
        '''
        assert self.curBlock.offset <= self.PC <= self.curBlock.offset + self.curBlock.length
        index = self.PC - self.curBlock.offset
        opCode = self.curBlock.bytecode[index]

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
                self.__execSDiv()
            case 0x06:
                self.__execMod()
            case 0x07:
                self.__execSMod()
            case 0x08:
                self.__execAddMod()
            case 0x09:
                self.__execMulMod()
            # case 0x0a:
            #     self.__execExp()
            # case 0x0b:
            #     self.__execSignExtend()
            case 0x10:
                self.__execLT()
            case 0x11:
                self.__execGt()
            case 0x12:
                self.__execSlt()
            case 0x13:
                self.__execSgt()
            case 0x14:
                self.__execEq()
            case 0x15:
                self.__execIsZero()
            case 0x16:
                self.__execAnd()
            case 0x17:
                self.__execOr()
            case 0x18:
                self.__execXor()
            case 0x19:
                self.__execNot()
            case 0x1b:
                self.__execShl()
            case 0x1c:
                self.__execShr()
            case 0x1d:
                self.__execSar()
            case 0x1f:
                self.__execNonOp()
            case 0x34:
                self.__execCallValue()
            case 0x35:
                self.__execCallDataLoad()
            case 0x36:
                self.__execCallDataSize()
            case 0x50:
                self.__execPop()
            case 0x51:
                self.__execMLoad()
            case 0x52:
                self.__execMStore()
            case 0x53:
                self.__execMStore8()
            case 0x54:
                self.__execSLoad()
            case 0x55:
                self.__execSStore()
            case 0x56:
                self.__execJump()
            case 0x57:
                self.__execJumpi()
            case 0x58:
                self.__execPc()
            case 0x5a:
                self.__execGas()
            case 0x5b:
                self.__execJumpDest()
            case i if 0x60 <= opCode <= 0x7f:  # push
                self.__execPush(opCode)
            case i if 0x80 <= opCode <= 0x8f:  # dup
                self.__execDup(opCode)
            case i if 0x90 <= opCode <= 0x9f:  # swap
                self.__execSwap(opCode)
            case 0xf3:
                self.__execReturn()
            case 0xfd:
                self.__execRevert()
            case 0xfe:
                self.__execInvalid()
            case _:  # Pattern not attempted
                err = 'Opcode {} is not found!'.format(hex(opCode))
                assert 0, err
        self.PC += 1

    def __execAdd(self):  # 0x01
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execMul(self):  # 0x02
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSub(self):  # 0x03
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execDiv(self):  # 0x04
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSDiv(self):  # 0x05
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execMod(self):  # 0x06
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSMod(self):  # 0x07
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execAddMod(self):  # 0x08
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execMulMod(self):  # 0x09
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execExp(self):  # 0x0a
        assert 0

    def __execSignExtend(self):  # 0x0b
        assert 0

    def __execLT(self):  # 0x10
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execGt(self):  # 0x11
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSlt(self):  # 0x12
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSgt(self):  # 0x13
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execEq(self):  # 0x14
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execIsZero(self):  # 0x15
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execAnd(self):  # 0x16
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execOr(self):  # 0x17
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execXor(self):  # 0x18
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execNot(self):  # 0x19
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execByte(self):  # 0x1a
        assert 0

    def __execShl(self):  # 0x1b
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execShr(self):  # 0x1c
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSar(self):  # 0x1d
        self.tagStack.pop()
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execNonOp(self):  # 0x1f 空指令
        pass

    def __execSha3(self):  # 0x20
        assert 0

    def __execAddress(self):  # 0x30
        assert 0

    def __execBalance(self):  # 0x31
        assert 0

    def __execOrigin(self):  # 0x32
        assert 0

    def __execCaller(self):  # 0x33
        assert 0

    def __execCallValue(self):  # 0x34
        self.tagStack.push(None)

    def __execCallDataLoad(self):  # 0x35
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execCallDataSize(self):  # 0x36
        self.tagStack.push(None)

    def __execCallDataCopy(self):  # 0x37
        for i in range(3):
            self.tagStack.pop()

    def __execCodesize(self):  # 0x38
        assert 0

    def __execCodecopy(self):  # 0x39
        assert 0

    def __execGasPrice(self):  # 0x3a
        assert 0

    def __execExtCodeSize(self):  # 0x3b
        assert 0

    def __execExtCodeCopy(self):  # 0x3c
        assert 0

    def __execReturnDataSize(self):  # 0x3d
        assert 0

    def __execReturnDataCopy(self):  # 0x3e
        assert 0

    def __execExtCodeHash(self):  # 0x3f
        assert 0

    def __execBlockHash(self):  # 0x40
        assert 0

    def __execCoinBase(self):  # 0x41
        assert 0

    def __execTimeStamp(self):  # 0x42
        assert 0

    def __execNumber(self):  # 0x43
        assert 0

    def __execPrevrandao(self):  # 0x44
        assert 0

    def __execGasLimit(self):  # 0x45
        assert 0

    def __execChainId(self):  # 0x46
        assert 0

    def __execSelfBalance(self):  # 0x47
        assert 0

    def __execBaseFee(self):  # 0x48
        assert 0

    def __execPop(self):  # 0x50
        self.tagStack.pop()

    def __execMLoad(self):  # 0x51
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execMStore(self):  # 0x52
        self.tagStack.pop()
        self.tagStack.pop()

    def __execMStore8(self):  # 0x53
        self.tagStack.pop()
        self.tagStack.pop()

    def __execSLoad(self):  # 0x54
        self.tagStack.pop()
        self.tagStack.push(None)

    def __execSStore(self):  # 0x55
        self.tagStack.pop()
        self.tagStack.pop()

    def __execJump(self):  # 0x56
        self.tagStack.pop()

    def __execJumpi(self):  # 0x57
        self.tagStack.pop()
        self.tagStack.pop()

    def __execPc(self):  # 0x58
        self.tagStack.push(None)

    def __execMSize(self):  # 0x59
        assert 0

    def __execGas(self):  # 0x5a
        self.tagStack.push(None)

    def __execJumpDest(self):  # 0x5b
        pass

    def __execPush(self, opCode):  # 0x60 <= opCode <= 0x7f
        jumpOpcodeAddr = self.PC  # 先记录下这一地址
        byteNum = opCode - 0x5f  # push的字节数
        num = 0
        for i in range(byteNum):
            num <<= 8
            self.PC += 1  # 指向最高位的字节
            num |= self.curBlock.bytecode[self.PC - self.curBlock.offset]  # 低位加上相应的字节
        # print("push num:{},byte num:{}".format(hex(num), byteNum))

        # 注意这里不能push一个比特向量，而是一个具体的数
        # num = BitVecVal(num, 256)

        self.tagStack.push([num, jumpOpcodeAddr, self.curBlock.offset])

    def __execDup(self, opCode):  # 0x80
        pos = opCode - 0x80
        self.tagStack.push(self.tagStack.getItem(self.tagStack.size() - 1 - pos))

    def __execSwap(self, opCode):  # 0x90 <= opCode <= 0x9f
        depth = opCode - 0x90 + 1
        stackSize = self.tagStack.size()
        pos = stackSize - 1 - depth
        self.tagStack.swap(stackSize - 1, pos)

    def __execLog(self, opCode):  # 0xa0 <= opCode <= 0xa4
        assert 0

    def __execCreate(self):  # 0xf0
        assert 0

    def __execCall(self):  # 0xf1
        assert 0

    def __execCallCode(self):  # 0xf2
        assert 0

    def __execReturn(self):  # 0xf3
        # 不分析合约间的跳转关系
        self.tagStack.pop()
        self.tagStack.pop()

    def __execDelegateCall(self):  # 0xf4
        assert 0

    def __execCreate2(self):  # 0xf5
        assert 0

    def __execStaticCall(self):  # 0xfa
        assert 0

    def __execRevert(self):  # 0xfd

        self.tagStack.pop()
        self.tagStack.pop()

    def __execInvalid(self):  # 0xfe
        pass

    def __execSelfDestruct(self):  # 0xff
        assert 0
