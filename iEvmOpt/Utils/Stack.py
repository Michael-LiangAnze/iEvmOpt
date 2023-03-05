from collections import deque
from z3 import *


class Stack:
    def __init__(self):
        self.__stack = deque()

    def push(self, a):
        self.__stack.append(a)

    def pop(self):
        if len(self.__stack) > 0:
            return self.__stack.pop()
        else:
            assert 0, "stack is empty!"

    def size(self):
        return len(self.__stack)

    def swap(self, pos1: int, pos2: int):
        temp = self.__stack[pos1]
        self.__stack[pos1] = self.__stack[pos2]
        self.__stack[pos2] = temp

    def getItem(self, pos: int):
        return self.__stack.__getitem__(pos)

    def clear(self):
        self.__stack.clear()

    def getStack(self, isHex: bool = False):
        if not isHex:
            return list(self.__stack)
        else:
            hexStack = deque()
            for i in range(len(self.__stack)):
                if is_bv_value(self.__stack[i]):
                    hexStack.append(hex(int(self.__stack[i].__str__())))
                else:
                    hexStack.append(self.__stack[i].__str__())
            return list(hexStack)
