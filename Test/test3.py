import os
import json
import shutil
import signal
import subprocess
import sys
import time

# 测试用
if __name__ == "__main__":

    dataPath = 'testContracts'
    dataFileList = os.listdir(dataPath)
    timeoutTime = 1200 # 20min
    totalContract = 0  # 合约数
    successCnt = 0  # 返回0
    sucessFile = []
    timeoutCnt = 0  # 超时的
    timeOutList = []
    failCnt = 0
    failList = []
    totalTime = 0

    for dataDir in dataFileList:
        totalContract += 1
        processInfo = {}
        binPath = dataPath + '/' + dataDir + '/bin'
        outputPath = dataPath + '/' + dataDir + '/iEvmOptRes'

        if os.path.exists(outputPath):
            shutil.rmtree(outputPath)
        os.mkdir(outputPath)

        assert len(os.listdir(binPath)) == 1
        binFile = os.listdir(binPath)[0]

        cmd = "python3 ../iEvmOpt/Main.py " + binPath + "/" + binFile + " " + outputPath + " newBin -pd"
        print(time.strftime('%Y-%m-%d %H:%M:%S - : ', time.localtime()) + str(totalContract) + cmd)
        reportFile = outputPath + "/" + binFile + "_report.json"
        if os.path.exists(reportFile):
            os.remove(reportFile)

        p = subprocess.Popen(cmd, shell=True, close_fds=True, preexec_fn=os.setsid)

        returnCode = 0
        start = time.perf_counter()
        try:
            p.wait(timeout=timeoutTime)
            returnCode = p.returncode
            if returnCode != 0:
                failCnt += 1
                failList.append(dataDir)
        except Exception as ex:
            print("Timeout: " + cmd)

            # os.killpg(p.pid, signal.SIGKILL)
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            returnCode = -1
            timeoutCnt += 1
            timeOutList.append(dataDir)
        end = time.perf_counter()

        processInfo[binFile] = str(returnCode)
        if returnCode == 0:
            sucessFile.append(dataDir)
            successCnt += 1
            totalTime += end - start
        else:
            print("error occurs!")

    jsonFile = outputPath + "/return_code.json"
    if os.path.exists(jsonFile):
        os.remove(jsonFile)
    with open(jsonFile, "w") as f:
        json.dump(processInfo, f, indent=2)

resString = "总合约数：{} 返回正常：{} 返回异常：{} 超时：{} 返回正常合约总用时：{}\n\n返回正常的合约有:\n".format(totalContract, successCnt, failCnt,
                                                                               timeoutCnt, totalTime)
for f in sucessFile:
    resString += f + '\n'

resString += "\n返回异常的合约有:\n"
for f in failList:
    resString += f + '\n'

resString += "\n超时的合约有:\n"
for f in timeOutList:
    resString += f + '\n'
with open(dataPath + "_processinfo.txt", "w") as f:
    f.write(resString)
print(resString)
