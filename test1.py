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

    dataPath = 'D:/Projects/iEvmOpt/testContract'
    dataFileList = os.listdir(dataPath)
    targetFile = []
    sizeList = []
    # limit = 12000
    limit = 9999999999999

    for dataDir in dataFileList:
        # 读取info，获取对应的bin文件
        dataDirPath = dataPath + "/" + dataDir
        infoPath = dataDirPath + '/info'
        with open(infoPath, 'r') as f:
            jsonInfo = json.load(f)
        targetBinFile = jsonInfo['name'] + '.bin'

        binPath = dataPath + '/' + dataDir + '/bin'
        success = False
        for f in os.listdir(dataDirPath):
            if f.find("_report.txt") != -1:  # 生成了报告
                with open(dataDirPath + "/" + f, "r", encoding='utf-8') as rp:
                    s = rp.read()
                    if s.find(
                            "assert targetAddr and targetNode") != -1:  # 是assertion error问题
                        tempSize = os.path.getsize(binPath + '/' + targetBinFile)
                        if tempSize < limit:
                            targetFile.append(dataDir+"/bin/"+targetBinFile+"    "+str(tempSize))
                            sizeList.append(tempSize)

            # if f == "return_code.json":
            #     with open(dataDirPath + "/" + f, "r", encoding='utf-8') as rt:
            #         rtJson = json.load(rt)
            #         if rtJson[targetBinFile] == '0':  # 返回正常
            #             success = True
            #             tempSize = os.path.getsize(binPath + '/' + targetBinFile)
            #             targetFile.append(dataDir + "/bin/" + targetBinFile + "    " + str(tempSize))
            #             sizeList.append(tempSize)
            # elif f.find("_report.txt") != -1 and success:
            #     with open(dataDirPath + "/" + f, "r", encoding='utf-8') as rp:
            #         s = rp.read()
            #         s = s.split('\n')
            #         print(f + "   " + s[-1])
            #         print(f + "   " + s[-2])
            #         print(f + "   " + s[-3])
            #         print(f + "   " + s[-4])
            #         print(f + "   " + s[-5])

    sizeList.sort()
    print(sizeList)
    for t in targetFile:
        print(t)
    print(len(targetFile))
