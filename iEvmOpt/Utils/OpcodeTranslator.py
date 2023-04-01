from Cfg.BasicBlock import BasicBlock


class OpcodeTranslator:

    def __init__(self, exitNode: int):
        self.exitNode = exitNode

    def translate(self, block: BasicBlock):
        #  将字节码翻译回字符串
        offset = block.offset
        if offset == self.exitNode:
            block.instrs = ["{}:EXIT BLOCK".format(block.offset)]
            return block.instrs
        addrToContent = {}  # 地址：内容
        bytecode = block.bytecode
        blockLen = block.length
        PC = 0
        while PC < blockLen:
            tempPc = PC
            opcode = bytecode[PC]
            match opcode:
                case 0x00:  # stop
                    addrToContent[tempPc] = "STOP"
                case 0x01:  # add
                    addrToContent[tempPc] = "ADD"
                case 0x02:  # mul
                    addrToContent[tempPc] = "MUL"
                case 0x03:
                    addrToContent[tempPc] = "SUB"
                case 0x04:
                    addrToContent[tempPc] = "DIV"
                case 0x05:
                    addrToContent[tempPc] = "SDIV"
                case 0x06:
                    addrToContent[tempPc] = "MOD"
                case 0x07:
                    addrToContent[tempPc] = "SMOD"
                case 0x08:
                    addrToContent[tempPc] = "ADDMOD"
                case 0x09:
                    addrToContent[tempPc] = "MULMOD"
                case 0x0a:
                    addrToContent[tempPc] = "EXP"
                case 0x0b:
                    addrToContent[tempPc] = "SIGNEXTEND"
                case 0x10:
                    addrToContent[tempPc] = "LT"
                case 0x11:
                    addrToContent[tempPc] = "GT"
                case 0x12:
                    addrToContent[tempPc] = "SLT"
                case 0x13:
                    addrToContent[tempPc] = "SGT"
                case 0x14:
                    addrToContent[tempPc] = "EQ"
                case 0x15:
                    addrToContent[tempPc] = "ISZERO"
                case 0x16:
                    addrToContent[tempPc] = "AND"
                case 0x17:
                    addrToContent[tempPc] = "OR"
                case 0x18:
                    addrToContent[tempPc] = "XOR"
                case 0x19:
                    addrToContent[tempPc] = "NOT"
                case 0x1a:
                    addrToContent[tempPc] = "BYTE"
                case 0x1b:
                    addrToContent[tempPc] = "SHL"
                case 0x1c:
                    addrToContent[tempPc] = "SHR"
                case 0x1d:
                    addrToContent[tempPc] = "SAR"
                case 0x1f:
                    addrToContent[tempPc] = "NONOP"
                case 0x20:
                    addrToContent[tempPc] = "SHA3"
                case 0x30:
                    addrToContent[tempPc] = "ADDRESS"
                case 0x31:
                    addrToContent[tempPc] = "BALANCE"
                case 0x32:
                    addrToContent[tempPc] = "ORIGIN"
                case 0x33:
                    addrToContent[tempPc] = "CALLER"
                case 0x34:
                    addrToContent[tempPc] = "CALLVALUE"
                case 0x35:
                    addrToContent[tempPc] = "CALLDATALOAD"
                case 0x36:
                    addrToContent[tempPc] = "CALLDATASIZE"
                case 0x38:
                    addrToContent[tempPc] = "CODESIZE"
                case 0x3a:
                    addrToContent[tempPc] = "GASPRICE"
                case 0x40:
                    addrToContent[tempPc] = "BLOCKHASH"
                case 0x41:
                    addrToContent[tempPc] = "COINBASE"
                case 0x42:
                    addrToContent[tempPc] = "TIMESTAMP"
                case 0x43:
                    addrToContent[tempPc] = "NUMBER"
                case 0x44:
                    addrToContent[tempPc] = "PREVRANDAO"
                case 0x45:
                    addrToContent[tempPc] = "GASLIMIT"
                case 0x46:
                    addrToContent[tempPc] = "CHAINID"
                case 0x47:
                    addrToContent[tempPc] = "SELFBALANCE"
                case 0x48:
                    addrToContent[tempPc] = "BASEFEE"
                case 0x50:
                    addrToContent[tempPc] = "POP"
                case 0x51:
                    addrToContent[tempPc] = "MLOAD"
                case 0x52:
                    addrToContent[tempPc] = "MSTORE"
                case 0x53:
                    addrToContent[tempPc] = "MSTORE8"
                case 0x54:
                    addrToContent[tempPc] = "SLOAD"
                case 0x55:
                    addrToContent[tempPc] = "SSTORE"
                case 0x56:
                    addrToContent[tempPc] = "JUMP"
                case 0x57:
                    addrToContent[tempPc] = "JUMPI"
                case 0x58:
                    addrToContent[tempPc] = "PC"
                case 0x5a:
                    addrToContent[tempPc] = "GAS"
                case 0x5b:
                    addrToContent[tempPc] = "JUMPDEST"
                case i if 0x60 <= opcode <= 0x7f:  # push
                    byteNum = opcode - 0x5f  # push的字节数
                    numStr = " 0x"
                    for i in range(byteNum):
                        PC += 1  # 指向最高位的字节
                        numStr += '{:02x}'.format(bytecode[PC])
                    addrToContent[tempPc] = "PUSH" + str(byteNum) + numStr
                case i if 0x80 <= opcode <= 0x8f:  # dup
                    pos = opcode - 0x80 + 1
                    addrToContent[tempPc] = "DUP" + str(pos)
                case i if 0x90 <= opcode <= 0x9f:  # swap
                    depth = opcode - 0x90 + 1
                    addrToContent[tempPc] = "SWAP" + str(depth)
                case i if 0xa0 <= opcode <= 0xa4:  # log
                    x = opcode - 0xa0
                    addrToContent[tempPc] = "LOG" + str(x)
                case 0xf3:
                    addrToContent[tempPc] = "RETURN"
                case 0xfd:
                    addrToContent[tempPc] = "REVERT"
                case 0xfe:
                    addrToContent[tempPc] = "INVALID"
                case _:  # Pattern not attempted
                    err = 'Opcode {} is not found!'.format(hex(opcode))
                    assert 0, err
            PC += 1
        contentList = ["{}:{}".format(block.offset + addr, c) for addr, c in addrToContent.items()]
        block.instrs = contentList
        return block.instrs
