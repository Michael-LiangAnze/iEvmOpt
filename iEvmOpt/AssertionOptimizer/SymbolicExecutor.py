from Cfg.BasicBlock import BasicBlock
from z3 import *

from Cfg.Cfg import Cfg
from Utils import Stack


class SymbolicExecutor:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.curBlock: BasicBlock = None  # 当前执行的基本块
        self.PC = 0  # 当前执行指令的指针
        self.stack = Stack()  # 符号执行栈
        self.storage = dict()  # 使用字典存储，格式为  addr:data
        self.memory = dict()  # 使用字典存储，格式为  addr:data
        self.gasOpcCnt = 0  # 统计gas指令被调用的次数
        self.mSizeCnt = 0  # 统计msize指令被调用的次数

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
        self.stack.clear()
        self.storage.clear()
        self.memory.clear()
        self.gasOpcCnt = 0
        self.jumpCond = None  # 记录jumpi的跳转条件，详见jumpi的实现

    def checkIsCertainJumpDest(self):
        '''
        检查是否为固定的跳转地址
        :return:[是否为固定的跳转地址,跳转的条件]
        '''
        if is_bool(self.jumpCond):  # 是bool类型，但是不知道是不是value
            if is_true(self.jumpCond) or is_false(self.jumpCond):  # 是一个value
                return True, is_true(self.jumpCond)
            else:
                return False, None
        elif is_bv_value(self.jumpCond):  # 是bitvecval类型
            return True, simplify(self.jumpCond != 0)
        else:
            return False, None

    def getJumpCond(self, jumpOrNot: bool):
        '''
        获取跳转条件
        :param jumpOrNot:当前block的跳转出口为true时Jump还是false时jump
        :return:跳转条件的z3表达式
        '''
        if jumpOrNot:  # 走的是true的边
            if is_bool(self.jumpCond):
                return simplify(self.jumpCond)
            elif is_bv(self.jumpCond):
                return simplify(self.jumpCond != 0)
            else:
                assert 0
        else:  # 走的是false的边
            if is_bool(self.jumpCond):
                return simplify(Not(self.jumpCond))
            elif is_bv(self.jumpCond):
                return simplify(self.jumpCond == 0)
            else:
                assert 0

    def allInstrsExecuted(self):
        return self.PC > self.lastInstrAddrOfBlock

    def getBlockJumpType(self):
        '''
        返回当前节点的跳转类型
        :return:跳转类型，包括：unconditional、conditional、terminal、fall
        '''
        return self.curBlock.jumpType

    def setBeginBlock(self, curBlockId: int):
        """ 设置执行块，同时设置PC为块的偏移量
        :param curBlockId: 起始块的id(offset)
        """
        self.curBlock = self.cfg.blocks[curBlockId]
        self.PC = self.curBlock.offset
        self.lastInstrAddrOfBlock = int(self.curBlock.instrs[self.curBlock.instrNum - 1].split(":")[0])

    def getCurState(self):
        '''
        获取程序当前的执行状态
        :return:一个PC；一个字符串，分别包含了栈、memory、storage的状态
        '''
        state = self.stack.getStack().__str__() + "<=>" + self.memory.__str__() + "<=>" + self.storage.__str__()
        return self.PC, state

    def printState(self, printBlock: bool = True):
        """ 输出当前程序状态
        :param printBlock:是否输出基本块信息
        """
        if printBlock:
            self.curBlock.printBlockInfo()
        print("Current PC is:{}".format(self.PC))
        # print("Current stack:{}<-top".format(list(self.stack.getStack())))
        print("Current stack:{}<-top".format(list(self.stack.getStack(isHex=True))))
        print("Current storage:{}".format(self.storage))
        print("Current memory:{}\n".format(self.memory))

    def execNextOpCode(self):
        ''' 从当前PC开始，执行下一条指令
        规定执行完当前指令之后，PC指向下一条指令的第一个字节
        :return:None
        '''
        assert self.curBlock.offset <= self.PC <= self.curBlock.offset + self.curBlock.length
        index = self.PC - self.curBlock.offset
        assert index < len(self.curBlock.bytecode)
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
            case 0xf3:
                self.__execReturn()
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
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a + b))

    def __execMul(self):  # 0x02
        a, b = self.stack.pop(), self.stack.pop()
        if is_bool(a):  # a是一个逻辑表达式
            a = If(a, BitVecVal(1, 256), BitVecVal(0, 256))
        if is_bool(b):  # b是一个逻辑表达式
            b = If(b, BitVecVal(1, 256), BitVecVal(0, 256))
        self.stack.push(simplify(a * b))

    def __execSub(self):  # 0x03
        a, b = self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a - b))

    def __execDiv(self):  # 0x04
        a, b = self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(UDiv(a, b)))

    def __execSDiv(self):  # 0x05
        # 两个例子
        #     结果为2：
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFE
        #         SDIV
        #     结果为-2(0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe)：
        #         PUSH32 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #         PUSH32 0x0000000000000000000000000000000000000000000000000000000000000002
        #         SDIV
        a, b = self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(a / b))

    def __execMod(self):  # 0x06
        a, b = self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(If(b == 0, BitVecVal(0, 256), URem(a, b))))

    def __execSMod(self):  # 0x07
        a, b = self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b)
        self.stack.push(simplify(If(b == 0, BitVecVal(0, 256), SRem(a, b))))

    def __execAddMod(self):  # 0x08
        a, b, c = self.stack.pop(), self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b) and not is_bool(c)  # abc都不能是条件表达式
        zero = BitVecVal(0, 1)  # a+b可能超出2^256-1，需要先调整为257位的比特向量
        a = Concat(zero, a)
        b = Concat(zero, b)
        c = Concat(zero, c)
        res = simplify(a + b)  # 先计算出a+b
        res = simplify(If(c == 0, BitVecVal(0, 257), URem(res, c)))  # 再计算(a+b) % c
        self.stack.push(simplify(Extract(255, 0, res)))  # 先做截断再push

    def __execMulMod(self):  # 0x09
        a, b, c = self.stack.pop(), self.stack.pop(), self.stack.pop()
        assert not is_bool(a) and not is_bool(b) and not is_bool(c)  # abc都不能是条件表达式
        zero = BitVecVal(0, 256)  # a*b可能超出范围，需要先调整为512位的比特向量
        a = Concat(zero, a)
        b = Concat(zero, b)
        c = Concat(zero, c)
        res = simplify(a * b)  # 先计算出a*b
        res = simplify(If(c == 0, BitVecVal(0, 512), URem(res, c)))  # 再计算(a*b) % c
        self.stack.push(simplify(Extract(255, 0, res)))  # 先做截断再push

    def __execExp(self):  # 0x0a
        a, b = self.stack.pop(), self.stack.pop()
        assert (not is_bool(a)) and (not is_bool(b))
        if is_bv_value(a) and is_bv_value(b):
            res = BitVecVal(pow(int(a.__str__()), int(b.__str__())), 256)
            self.stack.push(res)
        else:
            res = BitVec("exp#" + a.__str__() + "#" + b.__str__(), 256)
            self.stack.push(res)

    def __execSignExtend(self):  # 0x0b
        a, b = self.stack.pop(), self.stack.pop()
        assert (not is_bool(a)) and (not is_bool(b))
        if is_bv_value(a) and is_bv_value(b):  # 两个都是值
            a = int(a.__str__())
            if a < 0 or a >= 32:  # 原数字保持不变
                self.stack.push(b)
            else:
                b = int(b.__str__())
                flag = 1 << (8 * a + 7)
                sign = flag & b
                if sign == 0:  # 高位全是0，低位取原数
                    mask = flag - 1
                    tmp = BitVecVal(mask & b, 256)
                    self.stack.push(tmp)
                else:  # 高位全是1，低位取原数
                    mask = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff  # 2 ^ 256 - 1
                    mask &= flag - 1
                    mask = ~mask
                    tmp = BitVecVal(mask | b, 256)
                    self.stack.push(tmp)
        else:
            tmp = BitVec("signextend#" + a.__str__() + "#" + b.__str__(), 256)
            self.stack.push(tmp)

    def __execLT(self):  # 0x10
        a, b = self.stack.pop(), self.stack.pop()
        # 就算a,b是具体的数值，存储的也是一个bool表达式(z3.z3.BoolRef)，而不是基本变量True
        self.stack.push(simplify(ULT(a, b)))

    def __execGt(self):  # 0x11
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(UGT(a, b)))

    def __execSlt(self):  # 0x12
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(a < b))

    def __execSgt(self):  # 0x13
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(a > b))

    def __execEq(self):  # 0x14
        a, b = self.stack.pop(), self.stack.pop()
        if (is_bool(a) and is_bool(b)) or (is_bv(a) and is_bv(b)):
            self.stack.push(simplify(a == b))
        else:
            if is_bool(a):
                a = If(a, BitVecVal(1, 256), BitVecVal(0, 256))
            elif is_bool(b):
                b = If(b, BitVecVal(1, 256), BitVecVal(0, 256))
            else:
                assert 0
            self.stack.push(simplify(a == b))

    def __execIsZero(self):  # 0x15
        a = self.stack.pop()
        if is_bool(a):
            self.stack.push(simplify(Not(a)))
        elif is_bv(a):
            self.stack.push(simplify(a == 0))
        else:
            assert 0

    def __execAnd(self):  # 0x16
        a, b = self.stack.pop(), self.stack.pop()
        assert (is_bv(a) and is_bv(b)) or (is_bool(a) and is_bool(b))
        if is_bv(a):
            self.stack.push(simplify(a & b))
        else:  # bool
            self.stack.push(simplify(And(a, b)))

    def __execOr(self):  # 0x17
        a, b = self.stack.pop(), self.stack.pop()
        aIsBool, aIsBV = is_bool(a), is_bv(a)
        bIsBool, bIsBV = is_bool(b), is_bv(b)
        if aIsBV and bIsBV:
            self.stack.push(simplify(a | b))
        elif aIsBool and bIsBool:
            self.stack.push(simplify(Or(a, b)))
        elif aIsBV and bIsBool:
            self.stack.push(simplify(a | If(b, BitVecVal(1, 256), BitVecVal(0, 256))))
        elif aIsBool and bIsBV:
            self.stack.push(simplify(If(a, BitVecVal(1, 256), BitVecVal(0, 256) | b)))
        else:
            assert 0

    def __execXor(self):  # 0x18
        a, b = self.stack.pop(), self.stack.pop()
        assert is_bv(a) and is_bv(b)
        self.stack.push(simplify(a ^ b))

    def __execNot(self):  # 0x19
        a = self.stack.pop()
        self.stack.push(simplify(~a))

    def __execByte(self):  # 0x1a
        a, b = self.stack.pop(), self.stack.pop()
        assert is_bv(a) and is_bv(b)
        mask = BitVecVal(0xff, 256)
        self.stack.push(simplify(mask & (b >> (31 - a) * 8)))

    def __execShl(self):  # 0x1b
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(b << a))

    def __execShr(self):  # 0x1c
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(LShR(b, a)))

    def __execSar(self):  # 0x1d
        a, b = self.stack.pop(), self.stack.pop()
        self.stack.push(simplify(b >> a))

    def __execNonOp(self):  # 0x1f 空指令
        pass

    def __execSha3(self):  # 0x20
        assert 0

    def __execAddress(self):  # 0x30
        tmp = BitVec("ADDRESS", 256)
        self.stack.push(tmp)

    def __execBalance(self):  # 0x31
        a = self.stack.pop()
        tmp = BitVec("balance#" + a.__str__(), 256)
        self.stack.push(tmp)

    def __execOrigin(self):  # 0x32
        tmp = BitVec("ORIGIN", 256)
        self.stack.push(tmp)

    def __execCaller(self):  # 0x33
        tmp = BitVec("CALLER", 256)
        self.stack.push(tmp)

    def __execCallValue(self):  # 0x34
        tmp = BitVec("CALLVALUE", 256)
        self.stack.push(tmp)

    def __execCallDataLoad(self):  # 0x35
        a = self.stack.pop()
        tmp = BitVec("CALLDATALOAD_" + a.__str__(), 256)
        self.stack.push(tmp)

    def __execCallDataSize(self):  # 0x36
        tmp = BitVec("CALLDATASIZE", 256)
        self.stack.push(tmp)

    def __execCallDataCopy(self):  # 0x37
        for i in range(3):
            self.stack.pop()

    def __execCodesize(self):  # 0x38
        tmp = BitVec("CODESIZE", 256)
        self.stack.push(tmp)

    def __execCodecopy(self):  # 0x39
        # 这里不对其进行分析，因为符号执行只在冗余分析的时候做
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execGasPrice(self):  # 0x3a
        tmp = BitVec("GASPRICE", 256)
        self.stack.push(tmp)

    def __execExtCodeSize(self):  # 0x3b
        a = self.stack.pop()
        tmp = BitVec("EXTCODESIZE_" + a.__str__(), 256)
        self.stack.push(tmp)

    def __execExtCodeCopy(self):  # 0x3c
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execReturnDataSize(self):  # 0x3d
        assert 0

    def __execReturnDataCopy(self):  # 0x3e
        self.stack.pop()
        self.stack.pop()
        self.stack.pop()

    def __execExtCodeHash(self):  # 0x3f
        a = self.stack.pop()
        tmp = BitVec("CODEHASH_" + a.__str__(), 256)
        self.stack.push(tmp)

    def __execBlockHash(self):  # 0x40
        a = self.stack.pop()
        tmp = BitVec("BLOCKHASH_" + a.__str__(), 256)
        self.stack.push(tmp)

    def __execCoinBase(self):  # 0x41
        tmp = BitVec("COINBASE", 256)
        self.stack.push(tmp)

    def __execTimeStamp(self):  # 0x42
        tmp = BitVec("TIMESTAMP", 256)
        self.stack.push(tmp)

    def __execNumber(self):  # 0x43
        tmp = BitVec("BLOCK_NUMBER", 256)
        self.stack.push(tmp)

    def __execPrevrandao(self):  # 0x44
        tmp = BitVec("PREVRANDAO", 256)
        self.stack.push(tmp)

    def __execGasLimit(self):  # 0x45
        tmp = BitVec("GAS_LIMIT", 256)
        self.stack.push(tmp)

    def __execChainId(self):  # 0x46
        tmp = BitVec("CHAIN_ID", 256)
        self.stack.push(tmp)

    def __execSelfBalance(self):  # 0x47
        tmp = BitVec("SELF_BALANCE", 256)
        self.stack.push(tmp)

    def __execBaseFee(self):  # 0x48
        tmp = BitVec("BASE_FEE", 256)
        self.stack.push(tmp)

    def __execPop(self):  # 0x50
        self.stack.pop()

    def __execMLoad(self):  # 0x51
        startAddr = self.stack.pop()
        endAddr = simplify(startAddr + 32)
        addr = startAddr.__str__() + '$' + endAddr.__str__()
        if addr in self.memory.keys():
            self.stack.push(self.memory[addr])
        else:
            self.stack.push(BitVec("MLOAD_" + addr, 256))

    def __execMStore(self):  # 0x52
        # 将存储地址写为 起始地址$终止地址
        startAddr = self.stack.pop()
        endAddr = simplify(startAddr + 32)
        addr = startAddr.__str__() + '$' + endAddr.__str__()
        data = self.stack.pop()
        if is_bool(data):  # 存储的是bool类型的数据
            data = If(data, BitVecVal(1, 256), BitVecVal(0, 256))
        self.memory[addr] = data

    def __execMStore8(self):  # 0x53
        # 将存储地址写为 起始地址$终止地址
        startAddr = self.stack.pop()
        endAddr = simplify(startAddr + 1)
        addr = startAddr.__str__() + '$' + endAddr.__str__()
        data = self.stack.pop()
        assert not is_bool(data)  # 存储的不是bool类型的数据
        temp = BitVecVal(0xff, 256)
        self.memory[addr] = simplify(data & temp)

    def __execSLoad(self):  # 0x54
        addr = self.stack.pop()
        addr = addr.__str__()
        if addr in self.storage.keys():
            self.stack.push(self.storage[addr])
        else:
            tmp = BitVec("SLOAD_" + addr, 256)
            self.stack.push(tmp)

    def __execSStore(self):  # 0x55
        addr = self.stack.pop()
        addr = addr.__str__()
        data = self.stack.pop()
        self.storage[addr] = data

    def __execJump(self):  # 0x56
        self.stack.pop()

    def __execJumpi(self):  # 0x57
        self.stack.pop()
        cond = self.stack.pop()
        if is_bv(cond):
            self.jumpCond = simplify(cond != 0)
        else:
            assert is_bool(cond)
            self.jumpCond = cond

    def __execPc(self):  # 0x58
        self.stack.push(BitVecVal(self.PC, 256))

    def __execMSize(self):  # 0x59
        tmp = BitVec("MSIZE_" + self.mSizeCnt, 256)
        self.stack.push(tmp)
        self.mSizeCnt += 1

    def __execGas(self):  # 0x5a
        self.gasOpcCnt += 1
        self.stack.push(BitVec("GAS_" + str(self.gasOpcCnt), 256))

    def __execJumpDest(self):  # 0x5b
        pass

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

    def __execDup(self, opCode):  # 0x80
        pos = opCode - 0x80
        # print(pos)
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
        assert 0

    def __execCall(self):  # 0xf1
        assert 0

    def __execCallCode(self):  # 0xf2
        assert 0

    def __execReturn(self):  # 0xf3
        # 不分析合约间的跳转关系
        self.stack.pop()
        self.stack.pop()

    def __execDelegateCall(self):  # 0xf4
        assert 0

    def __execCreate2(self):  # 0xf5
        assert 0

    def __execStaticCall(self):  # 0xfa
        assert 0

    def __execRevert(self):  # 0xfd
        self.stack.pop()
        self.stack.pop()

    def __execInvalid(self):  # 0xfe
        pass

    def __execSelfDestruct(self):  # 0xff
        self.stack.pop()
