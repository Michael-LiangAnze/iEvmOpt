from Cfg.BasicBlock import BasicBlock
from z3 import *

from Cfg.Cfg import Cfg
from Utils import Stack
from Utils.Logger import Logger


class SimplifiedExecutor:
    """
    为修复边关系打造的版本，区别为：
    1.只在确定的值之间做符号执行
    2.一旦None参与了运算，则置为None
    3.栈中所有的元素，要么是None，要么是数值
    4.只对地址参与的指令进行了设计，包括op1、op2,其余指令一律将结果置为None
    """

    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.curBlock: BasicBlock = None  # 当前执行的基本块
        self.PC = 0  # 当前执行指令的指针
        self.stack = Stack(enableUnderFlow=True)
        self.log = Logger()
        self.gasOpcCnt = 0  # 统计gas指令被调用的次数
        self.mSizeCnt = 0  # 统计msize指令被调用的次数
        self.callCnt = 0  # call指令调用计数
        self.sha3Cnt = 0  # sha指令调用计数
        self.createCnt = 0  # create指令调用计数

        # 辅助信息
        self.lastInstrAddrOfBlock = 0  # block内最后一个指令的地址

    def clear(self):
        '''
        清空符号执行器
        :return: None
        '''
        self.curBlock = None
        self.PC = 0
        self.stack.clear()

    def allInstrsExecuted(self):
        return self.PC > self.lastInstrAddrOfBlock

    def isLastInstr(self):
        return self.PC == self.lastInstrAddrOfBlock

    def getExecutorState(self):
        return self.stack.getStack()

    def setExecutorState(self, stackInfo: list):
        self.stack.setStack(stackInfo)

    def setBeginBlock(self, curBlockId: int):
        """ 设置执行块，同时设置PC为块的偏移量
        :param curBlockId: 起始块的id(offset)
        """
        self.curBlock = self.cfg.blocks[curBlockId]
        self.PC = self.curBlock.offset
        self.lastInstrAddrOfBlock = self.curBlock.offset + self.curBlock.length - 1  # 最后一条指令是一个字节的

    def getTagStackTop(self):
        return self.stack.getTop()

    def getTagStackItem(self, depth: int):
        tmpSize = self.stack.size()
        # if depth >= tmpSize:  # 不能超出栈深度
        #     return None
        return self.stack.getItem(tmpSize - 1 - depth)

    def printState(self, printBlock: bool = True):
        """ 输出当前程序状态
        :param printBlock:是否输出基本块信息
        """
        if printBlock:
            self.curBlock.printBlockInfo()
        print("Current PC is:{}".format(self.PC))
        print("Current tag stack:{}<-top".format(list(self.stack.getStack())))

    def getOpcode(self):
        '''
        获取当前PC处的操作码
        :return:opcode
        '''
        index = self.PC - self.curBlock.offset
        return self.curBlock.bytecode[index]

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
            case 0x0a:
                self.__execExp()
            case 0x0b:
                self.__execSignExtend()
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
            case 0x1a:
                self.__execByte()
            case 0x1b:
                self.__execShl()
            case 0x1c:
                self.__execShr()
            case 0x1d:
                self.__execSar()
            case 0x1f:
                self.__execNonOp()
            case 0x20:
                self.__execSha3()
            case 0x30:
                self.__execAddress()
            case 0x31:
                self.__execBalance()
            case 0x32:
                self.__execOrigin()
            case 0x33:
                self.__execCaller()
            case 0x34:
                self.__execCallValue()
            case 0x35:
                self.__execCallDataLoad()
            case 0x36:
                self.__execCallDataSize()
            case 0x37:
                self.__execCallDataCopy()
            case 0x38:
                self.__execCodesize()
            case 0x39:
                self.__execCodecopy()
            case 0x3a:
                self.__execGasPrice()
            case 0x3b:
                self.__execExtCodeSize()
            case 0x3c:
                self.__execExtCodeCopy()
            case 0x3d:
                self.__execReturnDataSize()
            case 0x3e:
                self.__execReturnDataCopy()
            case 0x3f:
                self.__execExtCodeHash()
            case 0x40:
                self.__execBlockHash()
            case 0x41:
                self.__execCoinBase()
            case 0x42:
                self.__execTimeStamp()
            case 0x43:
                self.__execNumber()
            case 0x44:
                self.__execPrevrandao()
            case 0x45:
                self.__execGasLimit()
            case 0x46:
                self.__execChainId()
            case 0x47:
                self.__execSelfBalance()
            case 0x48:
                self.__execBaseFee()
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
            case 0x59:
                self.__execMSize()
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
            case i if 0xa0 <= opCode <= 0xa4:  # log
                self.__execLog(opCode)
            case 0xf0:
                self.__execCreate()
            case 0xf1:
                self.__execCall()
            case 0xf2:
                self.__execCallCode()
            case 0xf3:
                self.__execReturn()
            case 0xf4:
                self.__execDelegateCall()
            case 0xf5:
                self.__execCreate2()
            case 0xfa:
                self.__execStaticCall()
            case 0xfd:
                self.__execRevert()
            case 0xfe:
                self.__execInvalid()
            case 0xff:
                self.__execSelfDestruct()
            case _:  # Pattern not attempted
                err = 'Opcode {} is not found!'.format(hex(opCode))
                assert 0, err
        self.PC += 1

    def __execAdd(self):  # 0x01
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a+b)

    def __execMul(self):  # 0x02
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a * b)

    def __execSub(self):  # 0x03
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a - b)

    def __execDiv(self):  # 0x04
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a / b)

    def __execSDiv(self):  # 0x05
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execMod(self):  # 0x06
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execSMod(self):  # 0x07
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execAddMod(self):  # 0x08
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execMulMod(self):  # 0x09
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execExp(self):  # 0x0a
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execSignExtend(self):  # 0x0b
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execLT(self):  # 0x10
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execGt(self):  # 0x11
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execSlt(self):  # 0x12
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execSgt(self):  # 0x13
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execEq(self):  # 0x14
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execIsZero(self):  # 0x15
        self.stack.pop()
        self.stack.push(None)

    def __execAnd(self):  # 0x16
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a & b)

    def __execOr(self):  # 0x17
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a | b)

    def __execXor(self):  # 0x18
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(a ^ b)

    def __execNot(self):  # 0x19
        self.stack.pop()
        self.stack.push(None)

    def __execByte(self):  # 0x1a
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execShl(self):  # 0x1b
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(b << a)

    def __execShr(self):  # 0x1c
        a, b = self.stack.pop(), self.stack.pop()
        if a is None or b is None:
            self.stack.push(None)
        else:
            self.stack.push(b >> a)

    def __execSar(self):  # 0x1d
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execNonOp(self):  # 0x1f 空指令
        pass

    def __execSha3(self):  # 0x20
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)

    def __execAddress(self):  # 0x30
        self.stack.push(None)

    def __execBalance(self):  # 0x31
        self.stack.pop()
        self.stack.push(None)

    def __execOrigin(self):  # 0x32
        self.stack.push(None)

    def __execCaller(self):  # 0x33
        self.stack.push(None)

    def __execCallValue(self):  # 0x34
        self.stack.push(None)

    def __execCallDataLoad(self):  # 0x35
        self.stack.pop()
        self.stack.push(None)

    def __execCallDataSize(self):  # 0x36
        self.stack.push(None)

    def __execCallDataCopy(self):  # 0x37
        for i in range(3):
            self.stack.pop()

    def __execCodesize(self):  # 0x38
        self.stack.push(None)

    def __execCodecopy(self):  # 0x39
        # 这里不对其进行分析，因为符号执行只在冗余分析的时候做
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execGasPrice(self):  # 0x3a
        self.stack.push(None)

    def __execExtCodeSize(self):  # 0x3b
        self.stack.pop()
        self.stack.push(None)

    def __execExtCodeCopy(self):  # 0x3c
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execReturnDataSize(self):  # 0x3d
        self.stack.push(None)

    def __execReturnDataCopy(self):  # 0x3e
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execExtCodeHash(self):  # 0x3f
        self.stack.pop()
        self.stack.push(None)

    def __execBlockHash(self):  # 0x40
        self.stack.pop()
        self.stack.push(None)

    def __execCoinBase(self):  # 0x41
        self.stack.push(None)

    def __execTimeStamp(self):  # 0x42
        self.stack.push(None)

    def __execNumber(self):  # 0x43
        self.stack.push(None)

    def __execPrevrandao(self):  # 0x44
        self.stack.push(None)

    def __execGasLimit(self):  # 0x45
        self.stack.push(None)

    def __execChainId(self):  # 0x46
        self.stack.push(None)

    def __execSelfBalance(self):  # 0x47
        self.stack.push(None)

    def __execBaseFee(self):  # 0x48
        self.stack.push(None)

    def __execPop(self):  # 0x50
        self.stack.pop()

    def __execMLoad(self):  # 0x51
        self.stack.pop()
        self.stack.push(None)

    def __execMStore(self):  # 0x52
        self.stack.pop()
        self.stack.pop()


    def __execMStore8(self):  # 0x53
        self.stack.pop()
        self.stack.pop()

    def __execSLoad(self):  # 0x54
        self.stack.pop()
        self.stack.push(None)

    def __execSStore(self):  # 0x55
        self.stack.pop()
        self.stack.pop()

    def __execJump(self):  # 0x56
        self.stack.pop()

    def __execJumpi(self):  # 0x57
        self.stack.pop()
        self.stack.pop()

    def __execPc(self):  # 0x58
        self.stack.push(None)

    def __execMSize(self):  # 0x59
        self.stack.push(None)
        self.mSizeCnt += 1

    def __execGas(self):  # 0x5a
        self.gasOpcCnt += 1
        self.stack.push(None)

    def __execJumpDest(self):  # 0x5b
        pass

    def __execPush(self, opCode):  # 0x60 <= opCode <= 0x7f
        byteNum = opCode - 0x5f  # push的字节数
        num = 0
        for i in range(byteNum):
            num <<= 8
            self.PC += 1  # 指向最高位的字节
            num |= self.curBlock.bytecode[self.PC - self.curBlock.offset]  # 低位加上相应的字节
        self.stack.push(num)

    def __execDup(self, opCode):  # 0x80
        pos = opCode - 0x80
        self.stack.push(self.stack.getItem(self.stack.size() - 1 - pos))

    def __execSwap(self, opCode):  # 0x90 <= opCode <= 0x9f
        depth = opCode - 0x90 + 1
        stackSize = self.stack.size()
        pos = stackSize - 1 - depth
        self.stack.swap(stackSize - 1, pos)

    def __execLog(self, opCode):  # 0xa0 <= opCode <= 0xa4
        self.stack.pop()
        self.stack.pop()
        for i in range(0xa0, opCode):
            self.stack.pop()

    def __execCreate(self):  # 0xf0
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.createCnt += 1

    def __execCall(self):  # 0xf1
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.callCnt += 1

    def __execCallCode(self):  # 0xf2
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.callCnt += 1

    def __execReturn(self):  # 0xf3
        # 不分析合约间的跳转关系
        self.stack.pop()
        self.stack.pop()

    def __execDelegateCall(self):  # 0xf4
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.callCnt += 1

    def __execCreate2(self):  # 0xf5
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.createCnt += 1

    def __execStaticCall(self):  # 0xfa
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.push(None)
        self.callCnt += 1

    def __execRevert(self):  # 0xfd
        self.stack.pop()
        self.stack.pop()

    def __execInvalid(self):  # 0xfe
        pass

    def __execSelfDestruct(self):  # 0xff
        self.stack.pop()
