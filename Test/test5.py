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

        dataDirPath = dataPath + "/" + dataDir
        infoPath = dataDirPath + '/info'
        with open(infoPath, 'r') as f:
            jsonInfo = json.load(f)
        targetBinFile = jsonInfo['name'] + '.bin'

        binPath = dataPath + '/' + dataDir + '/bin'
        outputPath = dataPath + '/' + dataDir + '/iEvmOptRes'
        success = False

        with open(outputPath + "/" + targetBinFile+"_report.txt", "r", encoding='utf-8') as rp:
            try:
                s = rp.read()
            except:
                print(dataDir)
                continue
            total += 1
            # c = s.find("运行时函数边修复失败") != -1 or s.find("未能找全函数节点，放弃优化") != -1 or s.find("构造函数边修复失败") != -1 \
            #     or s.find("正在将优化后的字节码写入到文件") != -1 \
            #     or s.find("不存在可优化的Assertion") != -1\
            #     or s.find("没有找到Assertion") != -1
            # if not c:
            if s.find("路径搜索超时") != -1:
                tempSize = os.path.getsize(binPath + '/' + targetBinFile)
                if tempSize < limit:
                    targetFile.append(dataDir)
                    sizeList.append(tempSize)


    sizeList.sort()
    # print("total:{}".format(total))
    # print("target:{}".format(targetFile.__len__()))

    # for t in targetFile:
    #     print(t)

