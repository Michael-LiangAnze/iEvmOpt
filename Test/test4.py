import os
import json
import shutil
import signal
import subprocess
import sys
import time

# 跑选定的测试数据集
if __name__ == "__main__":

    dataPath = 'contracts1'
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

        logFile = outputPath + "/" + binFile + "_log.txt"
        fp = open(logFile, "w")
        p = subprocess.Popen(cmd, stdout=fp, stderr=fp, shell=True, close_fds=True, preexec_fn=os.setsid)

        returnCode = 0
        isTimeout = 0
        start = time.perf_counter()
        try:
            p.wait(timeout=timeoutTime)
            returnCode = p.returncode
            if returnCode != 0:
                failCnt += 1
                failList.append(dataDir)
        except Exception as ex:
            print("Timeout: " + cmd)
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            returnCode = -1
            isTimeout = 1
            timeoutCnt += 1
            timeOutList.append(dataDir)
        end = time.perf_counter()

        fp.close()
        processInfo["return code"] = str(returnCode)
        processInfo["time"] = str(int(end - start))
        processInfo["timeout"] = str(isTimeout)
        if returnCode == 0:
            sucessFile.append(dataDir)
            successCnt += 1
            totalTime += end - start
        else:
            print("error occurs!")

        reportFile = outputPath + "/report.json"
        if os.path.exists(reportFile):
            os.remove(reportFile)
        with open(reportFile, "w") as f:
            json.dump(processInfo, f, indent=2)

    resString = "总合约数：{} 运行正常：{} 运行异常：{} 超时：{} 返回正常合约总用时：{}\n\n返回正常的合约有:\n".format(totalContract, successCnt, failCnt,
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
