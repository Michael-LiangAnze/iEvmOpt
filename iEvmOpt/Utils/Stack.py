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
        return self.__stack.__len__()

    def swap(self, pos1: int, pos2: int):
        temp = self.__stack[pos1]
        self.__stack[pos1] = self.__stack[pos2]
        self.__stack[pos2] = temp

    def getItem(self, pos: int):
        return self.__stack.__getitem__(pos)

    def clear(self):
        self.__stack.clear()

    def empty(self):
        if self.__stack.__len__() == 0:
            return True
        else:
            return False

    def getTop(self):
        if self.__stack.__len__() != 0:
            return self.__stack[self.__stack.__len__()-1]
        else:
            return None

    def hasItem(self,item):
        return self.__stack.__contains__(item)

    def setStack(self,stackItems:list):
        self.__stack = deque(stackItems)

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
