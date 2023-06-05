import os
import json
import pickle
import re
import shutil
import subprocess
import sys

"""
在数据集中寻找特定的输出
"""
if __name__ == "__main__":

    dataPath = 'contracts1'
    dataFileList = os.listdir(dataPath)
    targetFile = []
    sizeList = []
    # limit = 12000
    total = 0
    limit = 9999999999999

    for dataDir in dataFileList:
        # 读取info，获取对应的bin文件
        total += 1
        dataDirPath = dataPath + "/" + dataDir
        infoPath = dataDirPath + '/info'
        with open(infoPath, 'r') as f:
            jsonInfo = json.load(f)
        targetBinFile = jsonInfo['name'] + '.bin'

        binPath = dataPath + '/' + dataDir + '/bin'
        outputPath = dataPath + '/' + dataDir + '/iEvmOptRes'
        success = False
        for f in os.listdir(outputPath):
            # if f.find("newBin") != -1:  # 生成了报告

            #             targetFile.append(dataDir)
            #             sizeList.append(tempSize)
            if f.find("_report.txt") != -1:  # 生成了报告
                with open(outputPath + "/" + f, "r", encoding='utf-8') as rp:
                    s = rp.read()
                    # c = s.find("运行时函数边修复失败") != -1 or s.find("未能找全函数节点，放弃优化") != -1 or s.find("构造函数边修复失败") != -1 \
                    #     or s.find("正在将优化后的字节码写入到文件") != -1 \
                    #     or s.find("不存在可优化的Assertion") != -1\
                    #     or s.find("没有找到Assertion") != -1
                    # if not c:
                    if s.find("RecursionError: maximum recursion depth exceeded while calling a Python object") != -1:
                        tempSize = os.path.getsize(binPath + '/' + targetBinFile)
                        if tempSize < limit:
                            targetFile.append(dataDir)
                            sizeList.append(tempSize)


    sizeList.sort()
    print("total:{}".format(total))
    print("target:{}".format(targetFile.__len__()))
    # print(sizeList)
    # for t in targetFile:
    #     print(t)

