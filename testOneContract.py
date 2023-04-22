import os
import json
import shutil
import subprocess
import sys
import time

"""
用ievmopt跑某一个特定合约
"""
if __name__ == "__main__":

    dataPath = 'D:/Projects/iEvmOpt/contracts'
    dataDir = "0x2B6D87F12B106E1D3fA7137494751566329d1045"
    timeoutTime = 60

    processInfo = {}
    binPath = dataPath + '/' + dataDir + '/bin'
    newBinPath = dataPath + '/' + dataDir + '/optimized'

    if os.path.exists(newBinPath):
        shutil.rmtree(newBinPath)
    os.mkdir(newBinPath)

    for f in os.listdir(binPath):
        cmd = "python iEvmOpt/Main.py " + binPath + "/" + f + " " + newBinPath + "/" + f
        print(time.strftime('%Y-%m-%d %H:%M:%S - : ', time.localtime()) + cmd)
        reportFile = dataPath + '/' + dataDir + "/" + f + "_report.json"
        if os.path.exists(reportFile):
            os.remove(reportFile)

        reportFile = dataPath + '/' + dataDir + "/" + f + "_report.txt"
        oldStdOut, oldStdErr = sys.stdout, sys.stderr
        fp = open(reportFile, "w")
        p = subprocess.Popen(cmd, stdout=fp, stderr=fp)

        returnCode = 0
        try:
            p.wait(timeout=timeoutTime)
            returnCode = p.returncode
        except Exception as ex:
            print("Timeout: " + cmd)
            cmd = "taskkill /F /PID " + str(p.pid)
            os.system(cmd)
            returnCode = -1


        fp.close()
        sys.stdout = oldStdOut
        sys.stderr = oldStdErr
        processInfo[f] = str(returnCode)

        jsonFile = dataPath + '/' + dataDir + "/return_code.json"
        if os.path.exists(jsonFile):
            os.remove(jsonFile)
        if os.path.exists(dataPath + '/' + dataDir + "/report.json"):
            os.remove(dataPath + '/' + dataDir + "/report.json")
        with open(jsonFile, "w") as f:
            json.dump(processInfo, f, indent=2)

