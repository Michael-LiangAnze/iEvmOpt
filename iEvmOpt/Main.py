import os
import sys

from Cfg import *
from AssertionOptimizer.AssertionOptimizer import AssertionOptimizer
from Utils.Helper import Helper

if __name__ == '__main__':
    """
    argv参数：
    argv[1]: 输入字节码文件
    argv[2]: 输出目录
    argv[3]: 输出文件名
    """

    h = Helper()
    for arg in sys.argv:  # 如果用于输出帮助信息或者版本信息，则不进行优化
        if arg in ['-h', "--help"]:
            print(h.getHelpInfo())
            exit(-1)
        elif arg in ['-v', "--version"]:
            print(h.getVersion())
            exit(-1)

    if len(sys.argv) < 4:
        print("请输入完整的参数")
        exit(-1)

    if len(sys.argv) > 6:
        print("参数过多")
        exit(-1)

    # 对可选参数进行检查
    printProcessInfo = False
    generateHtml = False
    for i in range(4,len(sys.argv)):
        arg = sys.argv[i]
        if arg in ['-pd','--process-detail'] :
            printProcessInfo = True
        elif arg in ['-H','--html']:
            generateHtml = True
        else:
            print("错误的参数:{}".format(arg))
            exit(-1)

    ao = AssertionOptimizer(inputFile=sys.argv[1],
                            outputPath=sys.argv[2],
                            outputName=sys.argv[3],
                            outputProcessInfo=printProcessInfo,
                            outputHtml=generateHtml)
    ao.optimize()
