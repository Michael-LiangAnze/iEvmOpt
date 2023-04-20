import os
import json
import pickle
import re
import shutil
import subprocess
import sys

"""
寻找一个asserterror的最小的合约进行分析
"""
if __name__ == "__main__":

    dataPath = 'D:/Projects/iEvmOpt/contracts'
    dataFileList = os.listdir(dataPath)
    targetFile = []
    sizeList = []
    limit = 12000

    for dataDir in dataFileList:
        # 读取info，获取对应的bin文件
        dataDirPath = dataPath + "/" + dataDir
        infoPath = dataDirPath + '/info'
        with open(infoPath, 'r') as f:
            jsonInfo = json.load(f)
        targetBinFile = jsonInfo['name'] + '.bin'

        binPath = dataPath + '/' + dataDir + '/bin'
        isGen = False
        for f in os.listdir(dataDirPath):
            if f.find("_report.txt") != -1:  # 生成了报告
                isGen = True
                with open(dataDirPath + "/" + f, "r", encoding='utf-8') as rp:
                    s = rp.read()
                    if s.find("AssertionError") != -1 and s.find(
                            "没有入边的Block") != -1:  # 是assertion error问题
                        tempSize = os.path.getsize(binPath + '/' + targetBinFile)
                        if tempSize < limit:
                            targetFile.append([targetBinFile, dataDir,tempSize])
                            sizeList.append(tempSize)
    sizeList.sort()
    print(sizeList)
    print(targetFile)
